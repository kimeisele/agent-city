from __future__ import annotations

import base64
import json
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
    parse_canonical,
)

FIXTURES = Path(__file__).parent / "fixtures" / "federation_v1"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_bytes())
KEYS = json.loads((FIXTURES / "keys" / "test_keys.json").read_bytes())
REQUEST = parse_canonical((FIXTURES / "messages" / "delegate_task.json").read_bytes())


def private(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(KEYS[label]["private_seed_hex"]))


def semantic_payload() -> dict:
    return {
        key: value
        for key, value in REQUEST["payload"].items()
        if key not in {"request_digest", "idempotency_key"}
    }


def registries() -> tuple[ValidatedFederationV1KeyRegistry, ValidatedFederationV1KeyRegistry]:
    provenance = FIXTURES / "provenance"
    origin = ValidatedFederationV1KeyRegistry.from_provenance(
        [json.loads((provenance / "origin_root_enrollment.json").read_bytes())],
        [json.loads((provenance / "origin_signing_key_certificate.json").read_bytes())],
        now="2026-07-18T11:00:00Z",
    )
    target = ValidatedFederationV1KeyRegistry.from_provenance(
        [json.loads((provenance / "target_root_enrollment.json").read_bytes())],
        [json.loads((provenance / "target_signing_key_certificate.json").read_bytes())],
        now="2026-07-18T11:00:00Z",
    )
    return origin, target


def services(tmp_path: Path):
    origin_registry, target_registry = registries()
    origin_ledger = OriginDelegationLedger(tmp_path / "origin.json")
    target_ledger = TargetAdmissionLedger(tmp_path / "target.json")
    origin = FederationV1Origin(
        ledger=origin_ledger,
        node_id=MANIFEST["positive"]["request"]["origin_node_id"],
        signing_key=private("origin_signing_key"),
        signer_key_b64=KEYS["origin_signing_key"]["public_key_b64"],
        key_id=MANIFEST["positive"]["request"]["origin_key_id"],
        enabled=True,
    )
    target = FederationV1Admission(
        ledger=target_ledger,
        node_id=MANIFEST["positive"]["request"]["target_node_id"],
        signing_key=private("target_signing_key"),
        signer_key_b64=KEYS["target_signing_key"]["public_key_b64"],
        key_id=MANIFEST["positive"]["root_enrollment"]["target"]["key_id"],
        registry=origin_registry,
        enabled=True,
    )
    return origin, target, origin_registry, target_registry, origin_ledger, target_ledger


def test_admission_only_cross_repo_boundary_and_full_persistence(tmp_path: Path) -> None:
    origin, target, _, target_registry, origin_ledger, target_ledger = services(tmp_path)
    request_wire, request_carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    assert request_wire == (FIXTURES / "messages" / "delegate_task.json").read_bytes()
    receipt_carrier = target.handle(request_carrier, now="2026-07-18T11:01:00Z")
    assert receipt_carrier is not None
    receipt_record = target_ledger.get(REQUEST["payload"]["delegation_id"])
    assert receipt_record is not None
    for field in (
        "target_work_id",
        "receipt_message_id",
        "receipt_id",
        "receipt_content_digest",
        "receipt_message_hash",
        "receipt_signature",
        "receipt_wire_bytes_b64",
        "receipt_send_status",
    ):
        assert field in receipt_record
    assert receipt_record["state"] == "ACCEPTED"
    target_ledger.mark_receipt_sent(REQUEST["payload"]["delegation_id"])
    assert target_ledger.get(REQUEST["payload"]["delegation_id"])["receipt_send_status"] == "sent"
    applied = origin.apply_receipt(
        carrier=receipt_carrier, registry=target_registry, now="2026-07-18T11:01:00Z"
    )
    assert applied["target_work_id"] == receipt_record["target_work_id"]
    assert (
        origin_ledger.get(REQUEST["payload"]["delegation_id"])["request_wire_bytes_b64"]
        == base64.b64encode(request_wire).decode()
    )
    assert origin.retransmit(REQUEST["payload"]["delegation_id"]) == request_carrier


def test_feature_gate_is_fail_closed_by_default(tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    origin.enabled = False
    target.enabled = False
    with pytest.raises(V1Reject, match="feature_disabled"):
        origin.create(
            payload=semantic_payload(),
            target_node_id=REQUEST["target_node_id"],
            message_id=REQUEST["message_id"],
            issued_at="2026-07-18T11:00:00Z",
            expires_at="2026-07-18T11:05:00Z",
        )
    assert target.handle({}, now="2026-07-18T11:01:00Z") is None


def test_crash_after_admission_commit_retransmits_identical_receipt(tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    first = target.handle(carrier, now="2026-07-18T11:01:00Z")
    second = target.handle(carrier, now="2026-07-18T11:01:00Z")
    assert first == second
    assert target.ledger.get(REQUEST["payload"]["delegation_id"])["target_work_id"]


def test_rejected_admission_is_durable_and_idempotent(tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    first = target.handle(carrier, now="2026-07-18T11:01:00Z", origin_authorized=False)
    second = target.handle(carrier, now="2026-07-18T11:01:00Z", origin_authorized=False)
    assert first == second
    record = target.ledger.get(REQUEST["payload"]["delegation_id"])
    assert record["state"] == "REJECTED" and record["target_work_id"] is None
    assert record["reason_code"] == "authority_denied"


def test_crash_before_admission_commit_leaves_no_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )

    def crash_before_commit(**_: object) -> tuple[str, dict]:
        raise RuntimeError("simulated crash before admission commit")

    monkeypatch.setattr(target.ledger, "commit", crash_before_commit)
    with pytest.raises(RuntimeError, match="before admission commit"):
        target.handle(carrier, now="2026-07-18T11:01:00Z")
    assert target.ledger.get(REQUEST["payload"]["delegation_id"]) is None


@pytest.mark.parametrize(
    "field, value",
    [
        ("source", "ag_" + "1" * 32),
        ("target", "ag_" + "2" * 32),
        ("operation", "federation_v1.wrong"),
    ],
)
def test_carrier_mutation_is_quarantined_without_response(
    tmp_path: Path, field: str, value: str
) -> None:
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    mutated = dict(carrier)
    mutated[field] = value
    assert target.handle(mutated, now="2026-07-18T11:01:00Z") is None
    assert target.ledger.get(REQUEST["payload"]["delegation_id"]) is None


@pytest.mark.parametrize(
    "kind",
    ["unknown_top_level", "unknown_payload", "wrong_version", "invalid_b64", "wildcard_target"],
)
def test_closed_carrier_shape_mutations_are_quarantined(tmp_path: Path, kind: str) -> None:
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    mutated = dict(carrier)
    if kind == "unknown_top_level":
        mutated["extra"] = "forbidden"
    elif kind == "unknown_payload":
        mutated["payload"] = {**carrier["payload"], "extra": "forbidden"}
    elif kind == "wrong_version":
        mutated["payload"] = {**carrier["payload"], "wire_version": "legacy"}
    elif kind == "invalid_b64":
        mutated["payload"] = {**carrier["payload"], "wire_bytes_b64": "!!!="}
    else:
        mutated["target"] = "ag_" + "0" * 32
    assert target.handle(mutated, now="2026-07-18T11:01:00Z") is None
    assert target.ledger.get(REQUEST["payload"]["delegation_id"]) is None


def test_first_set_target_work_id_and_conflict(tmp_path: Path) -> None:
    origin, target, _, target_registry, _, _ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    receipt_carrier = target.handle(carrier, now="2026-07-18T11:01:00Z")
    origin.apply_receipt(
        carrier=receipt_carrier, registry=target_registry, now="2026-07-18T11:01:00Z"
    )
    conflict_wire = build_admission_receipt(
        request=REQUEST,
        target=REQUEST["target_node_id"],
        origin=REQUEST["source_node_id"],
        message_id="rcpt_conflict_0001",
        receipt_id="receipt_conflict_0001",
        target_work_id="work_other",
        status="accepted",
        reason_code=None,
        signing_key=private("target_signing_key"),
        signer_key_b64=KEYS["target_signing_key"]["public_key_b64"],
        key_id=MANIFEST["positive"]["root_enrollment"]["target"]["key_id"],
        issued_at="2026-07-18T11:01:00Z",
    )
    with pytest.raises(V1Reject) as exc:
        origin.apply_receipt(
            carrier=build_carrier(conflict_wire),
            registry=target_registry,
            now="2026-07-18T11:01:00Z",
        )
    assert exc.value.code == "receipt_ledger_conflict"


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in MANIFEST["negative"]
        if case["id"] not in {"expired_certificate", "revoked_certificate"}
    ],
    ids=lambda case: case["id"],
)
def test_all_negative_request_boundaries_are_quarantined(case: dict, tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    if case["id"] in {"same_delegation_different_digest", "same_message_id_different_bytes"}:
        _, positive_carrier = origin.create(
            payload=semantic_payload(),
            target_node_id=REQUEST["target_node_id"],
            message_id=REQUEST["message_id"],
            issued_at="2026-07-18T11:00:00Z",
            expires_at="2026-07-18T11:05:00Z",
        )
        assert target.handle(positive_carrier, now="2026-07-18T11:01:00Z") is not None
    raw = (FIXTURES / case["path"]).read_bytes()
    carrier = {
        "operation": "federation_v1.delegate_task",
        "source": REQUEST["source_node_id"],
        "target": REQUEST["target_node_id"],
        "payload": {
            "wire_version": "federation-delegation-v1",
            "wire_bytes_b64": base64.b64encode(raw).decode("ascii"),
        },
    }
    assert target.handle(carrier, now="2026-07-18T11:01:00Z") is None
    if case["id"] in {"same_delegation_different_digest", "same_message_id_different_bytes"}:
        assert target.ledger.get(REQUEST["payload"]["delegation_id"]) is not None
    else:
        assert target.ledger.get(REQUEST["payload"]["delegation_id"]) is None
