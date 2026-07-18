from __future__ import annotations

import base64
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from city.federation_v1 import (
    FederationV1Admission,
    FederationV1Origin,
    OriginDelegationLedger,
    TargetAdmissionLedger,
    V1Reject,
    ValidatedFederationV1KeyRegistry,
    build_admission_receipt,
    build_carrier,
    canonical_bytes,
    parse_canonical,
    validate_envelope,
)

FIXTURES = Path(__file__).parent / "fixtures" / "federation_v1"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_bytes())
KEYS = json.loads((FIXTURES / "keys" / "test_keys.json").read_bytes())
REQUEST = parse_canonical((FIXTURES / "messages" / "delegate_task.json").read_bytes())


def private(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(KEYS[label]["private_seed_hex"]))


def payload() -> dict:
    return {
        key: value
        for key, value in REQUEST["payload"].items()
        if key not in {"request_digest", "idempotency_key"}
    }


def registry(label: str) -> ValidatedFederationV1KeyRegistry:
    provenance = FIXTURES / "provenance"
    return ValidatedFederationV1KeyRegistry.from_provenance(
        [json.loads((provenance / f"{label}_root_enrollment.json").read_bytes())],
        [json.loads((provenance / f"{label}_signing_key_certificate.json").read_bytes())],
        now="2026-07-18T11:00:00Z",
    )


def combined_registry() -> ValidatedFederationV1KeyRegistry:
    provenance = FIXTURES / "provenance"
    return ValidatedFederationV1KeyRegistry.from_provenance(
        [
            json.loads((provenance / "origin_root_enrollment.json").read_bytes()),
            json.loads((provenance / "target_root_enrollment.json").read_bytes()),
        ],
        [
            json.loads((provenance / "origin_signing_key_certificate.json").read_bytes()),
            json.loads((provenance / "target_signing_key_certificate.json").read_bytes()),
        ],
        now="2026-07-18T11:00:00Z",
    )


def services(tmp_path: Path):
    origin_registry, target_registry = registry("origin"), registry("target")
    origin = FederationV1Origin(
        ledger=OriginDelegationLedger(tmp_path / "origin.json"),
        node_id=MANIFEST["positive"]["request"]["origin_node_id"],
        signing_key=private("origin_signing_key"),
        signer_key_b64=KEYS["origin_signing_key"]["public_key_b64"],
        key_id=MANIFEST["positive"]["request"]["origin_key_id"],
        enabled=True,
    )
    target = FederationV1Admission(
        ledger=TargetAdmissionLedger(tmp_path / "target.json"),
        node_id=MANIFEST["positive"]["request"]["target_node_id"],
        signing_key=private("target_signing_key"),
        signer_key_b64=KEYS["target_signing_key"]["public_key_b64"],
        key_id=MANIFEST["positive"]["root_enrollment"]["target"]["key_id"],
        registry=origin_registry,
        enabled=True,
    )
    return origin, target, origin_registry, target_registry


def resign(envelope: dict, key: Ed25519PrivateKey) -> bytes:
    body = {
        key_name: value
        for key_name, value in envelope.items()
        if key_name not in {"message_hash", "signature"}
    }
    message_hash = hashlib.sha256(canonical_bytes(body)).hexdigest()
    result = {**body, "message_hash": message_hash}
    result["signature"] = base64.b64encode(
        key.sign(b"STEWARD-FEDERATION-DELEGATION-V1\x00" + bytes.fromhex(message_hash))
    ).decode("ascii")
    return canonical_bytes(result)


def test_origin_create_is_idempotent_and_conflict_fails_closed(tmp_path: Path) -> None:
    origin, *_ = services(tmp_path)
    first = origin.create(
        payload=payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    assert (
        origin.create(
            payload=payload(),
            target_node_id=REQUEST["target_node_id"],
            message_id=REQUEST["message_id"],
            issued_at="2026-07-18T11:00:00Z",
            expires_at="2026-07-18T11:05:00Z",
        )
        == first
    )
    changed = copy.deepcopy(payload())
    changed["task_description"] = "conflicting payload"
    with pytest.raises(V1Reject, match="origin_request_conflict"):
        origin.create(
            payload=changed,
            target_node_id=REQUEST["target_node_id"],
            message_id=REQUEST["message_id"],
            issued_at="2026-07-18T11:00:00Z",
            expires_at="2026-07-18T11:05:00Z",
        )
    with pytest.raises(V1Reject, match="origin_request_conflict"):
        origin.create(
            payload=payload(),
            target_node_id=REQUEST["target_node_id"],
            message_id="msg_req_other",
            issued_at="2026-07-18T11:00:00Z",
            expires_at="2026-07-18T11:05:00Z",
        )
    assert (
        origin.ledger.get(REQUEST["payload"]["delegation_id"])["request_wire_bytes_b64"]
        == base64.b64encode(first[0]).decode()
    )
    assert "origin_request_conflict" in origin.ledger.path.read_text()


@pytest.mark.parametrize("mutation", ["wrong_source", "correlation", "causation", "record_target"])
def test_receipt_binding_is_id_based(tmp_path: Path, mutation: str) -> None:
    (
        origin,
        target,
        _,
        _,
    ) = services(tmp_path)
    _, request_carrier = origin.create(
        payload=payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    receipt_carrier = target.handle(request_carrier, now="2026-07-18T11:01:00Z")
    original = parse_canonical(base64.b64decode(receipt_carrier["payload"]["wire_bytes_b64"]))
    if mutation == "wrong_source":
        wrong_wire = build_admission_receipt(
            request=REQUEST,
            target=REQUEST["source_node_id"],
            origin=REQUEST["source_node_id"],
            message_id="rcpt_wrong_source",
            receipt_id="receipt_wrong_source",
            target_work_id="work_wrong",
            status="accepted",
            reason_code=None,
            signing_key=private("origin_signing_key"),
            signer_key_b64=KEYS["origin_signing_key"]["public_key_b64"],
            key_id=MANIFEST["positive"]["request"]["origin_key_id"],
            issued_at="2026-07-18T11:01:00Z",
        )
        wrong_carrier = build_carrier(wrong_wire)
    elif mutation == "record_target":
        record = json.loads(origin.ledger.path.read_text())
        record["delegations"][REQUEST["payload"]["delegation_id"]]["target_node_id"] = REQUEST[
            "source_node_id"
        ]
        origin.ledger.path.write_text(json.dumps(record))
        wrong_carrier = receipt_carrier
    else:
        altered = dict(original)
        altered["correlation_id"] = (
            "del_other" if mutation == "correlation" else altered["correlation_id"]
        )
        altered["causation_message_id"] = (
            "msg_other" if mutation == "causation" else altered["causation_message_id"]
        )
        wrong_carrier = build_carrier(resign(altered, private("target_signing_key")))
    with pytest.raises(V1Reject, match="receipt_correlation_conflict"):
        origin.apply_receipt(
            carrier=wrong_carrier, registry=combined_registry(), now="2026-07-18T11:01:00Z"
        )


def test_provenance_and_registry_state_are_typed_and_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(V1Reject, match="registry_unvalidated"):
        validate_envelope(
            (FIXTURES / "messages" / "delegate_task.json").read_bytes(),
            registry={},
            expected_target=REQUEST["target_node_id"],
            operation="delegate_task",
            now="2026-07-18T11:01:00Z",
        )
    provenance = FIXTURES / "provenance"
    enrollment = json.loads((provenance / "origin_root_enrollment.json").read_bytes())
    certificate = json.loads((provenance / "origin_signing_key_certificate.json").read_bytes())
    broken = copy.deepcopy(certificate)
    broken["key_id"] = "key_" + "0" * 64
    with pytest.raises(V1Reject, match="certificate_key_binding"):
        ValidatedFederationV1KeyRegistry.from_provenance(
            [enrollment], [broken], now="2026-07-18T11:00:00Z"
        )


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ("wrong_node", "certificate_key_binding"),
        ("not_active", "certificate_time_window"),
        ("expired", "certificate_expired"),
    ],
)
def test_provenance_time_and_node_bindings_are_enforced(mutation: str, expected: str) -> None:
    provenance = FIXTURES / "provenance"
    enrollment = json.loads((provenance / "origin_root_enrollment.json").read_bytes())
    certificate = json.loads((provenance / "origin_signing_key_certificate.json").read_bytes())
    if mutation == "wrong_node":
        certificate["node_id"] = "ag_" + "0" * 32
    elif mutation == "not_active":
        certificate["not_before"] = "2027-07-18T00:05:00Z"
        certificate["activation_at"] = certificate["not_before"]
    else:
        certificate["not_after"] = "2026-07-18T10:00:00Z"
    with pytest.raises(V1Reject, match=expected):
        ValidatedFederationV1KeyRegistry.from_provenance(
            [enrollment], [certificate], now="2026-07-18T11:00:00Z"
        )


def test_revoked_key_is_rejected_at_message_validation_time() -> None:
    provenance = FIXTURES / "provenance"
    enrollment = json.loads((provenance / "origin_root_enrollment.json").read_bytes())
    certificate = json.loads((provenance / "origin_signing_key_certificate.json").read_bytes())
    certificate["revocation_ref"] = "operator-revocation-1"
    body = {key: value for key, value in certificate.items() if key != "root_signature"}
    digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
    certificate["root_signature"] = base64.b64encode(
        private("origin_identity_root").sign(
            b"STEWARD-FEDERATION-SIGNING-KEY-AUTH-V1\x00" + bytes.fromhex(digest)
        )
    ).decode()
    registry = ValidatedFederationV1KeyRegistry.from_provenance(
        [enrollment], [certificate], now="2026-07-18T11:00:00Z"
    )
    with pytest.raises(V1Reject, match="key_revoked"):
        registry.lookup(certificate["key_id"], at="2026-07-18T11:00:00Z")
    broken = copy.deepcopy(certificate)
    broken["root_signature"] = base64.b64encode(b"0" * 64).decode()
    with pytest.raises(V1Reject, match="provenance_signature_invalid"):
        ValidatedFederationV1KeyRegistry.from_provenance(
            [enrollment], [broken], now="2026-07-18T11:00:00Z"
        )


def test_corruption_and_independent_instances_are_fail_closed_and_process_safe(
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{bad")
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        TargetAdmissionLedger(corrupt).get("del_any")
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    targets = [
        FederationV1Admission(
            ledger=TargetAdmissionLedger(tmp_path / "target.json"),
            node_id=target.node_id,
            signing_key=private("target_signing_key"),
            signer_key_b64=KEYS["target_signing_key"]["public_key_b64"],
            key_id=target.key_id,
            registry=target.registry,
            enabled=True,
        )
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda service: service.handle(carrier, now="2026-07-18T11:01:00Z"), targets)
        )
    assert results[0] == results[1]
    assert targets[0].ledger.get(REQUEST["payload"]["delegation_id"]) is not None


def test_parallel_distinct_delegations_and_send_updates_do_not_overwrite(tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    first_payload = payload()
    second_payload = copy.deepcopy(first_payload)
    second_payload["delegation_id"] = "del_parallel_0002"
    second_payload["origin_task_id"] = "task_parallel_0002"
    _, first_carrier = origin.create(
        payload=first_payload,
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    _, second_carrier = origin.create(
        payload=second_payload,
        target_node_id=REQUEST["target_node_id"],
        message_id="msg_req_parallel_0002",
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    targets = [
        FederationV1Admission(
            ledger=TargetAdmissionLedger(tmp_path / "target.json"),
            node_id=target.node_id,
            signing_key=private("target_signing_key"),
            signer_key_b64=KEYS["target_signing_key"]["public_key_b64"],
            key_id=target.key_id,
            registry=target.registry,
            enabled=True,
        )
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda pair: pair[0].handle(pair[1], now="2026-07-18T11:01:00Z"),
                zip(targets, (first_carrier, second_carrier)),
            )
        )
    ledger_a = TargetAdmissionLedger(tmp_path / "target.json")
    ledger_b = TargetAdmissionLedger(tmp_path / "target.json")
    ledger_a.mark_receipt_sent(first_payload["delegation_id"])
    ledger_b.mark_receipt_sent(second_payload["delegation_id"])
    assert ledger_a.get(first_payload["delegation_id"])["receipt_send_status"] == "sent"
    assert ledger_b.get(second_payload["delegation_id"])["receipt_send_status"] == "sent"
