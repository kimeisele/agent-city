from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .hardening import (
    FIXTURE_NOW,
    build_certificate,
    build_enrollment,
    build_request,
    rfc3339,
    validate_fixture,
    validate_provenance,
)
from .reference import canonical, key_id, load_canonical, node_id

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "federation_v1"
MANIFEST = json.loads((ROOT / "manifest.json").read_bytes())
KEYS = json.loads((ROOT / "keys" / "test_keys.json").read_bytes())


def _private(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(KEYS[label]["private_seed_hex"]))


def _public(label: str) -> bytes:
    return base64.b64decode(KEYS[label]["public_key_b64"], validate=True)


def _raw(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def test_agent_city_independently_regenerates_every_positive_artifact() -> None:
    identities = {}
    for label, root_label, signing_label in (("origin", "origin_identity_root", "origin_signing_key"), ("target", "target_identity_root", "target_signing_key")):
        enrollment, enrollment_input, enrollment_digest = build_enrollment(label, _private(root_label))
        assert canonical(enrollment) == _raw(f"provenance/{label}_root_enrollment.json")
        assert enrollment_input.hex().encode() == _raw(f"provenance/{label}_root_enrollment.signature_input.hex")
        root_public = _public(root_label)
        node = node_id(root_public)
        signing_public = _public(signing_label)
        certificate, certificate_input, certificate_digest = build_certificate(_private(root_label), signing_public, node)
        assert canonical(certificate) == _raw(f"provenance/{label}_signing_key_certificate.json")
        assert certificate_input.hex().encode() == _raw(f"provenance/{label}_signing_key_certificate.signature_input.hex")
        assert validate_provenance(canonical(enrollment), root_public) is None
        assert validate_provenance(canonical(certificate), root_public) is None
        assert enrollment["identity_root_public_key"] == KEYS[root_label]["public_key_b64"]
        assert enrollment["node_id"] == node == certificate["node_id"]
        assert certificate["identity_root_public_key"] == enrollment["identity_root_public_key"]
        assert certificate["key_id"] == key_id(signing_public) == MANIFEST["positive"]["root_enrollment"][label]["key_id"]
        assert rfc3339(certificate["activation_at"]) <= rfc3339(FIXTURE_NOW) <= rfc3339(certificate["not_after"])
        assert certificate["registry_epoch"] == certificate["certificate_epoch"] == certificate["activation_epoch"] == 1
        identities[label] = {"node": node, "key": certificate["key_id"], "enrollment_digest": enrollment_digest, "certificate_digest": certificate_digest}

    request, signature_input, request_digest, message_hash = build_request(
        identities["origin"]["node"], identities["target"]["node"], _private("origin_signing_key"), KEYS["origin_signing_key"]["public_key_b64"], identities["origin"]["key"]
    )
    assert canonical(request) == _raw("messages/delegate_task.json")
    assert signature_input.hex().encode() == _raw("messages/delegate_task.signature_input.hex")
    assert request_digest == MANIFEST["positive"]["request"]["request_digest"]
    assert request["payload"]["idempotency_key"] == "fedv1:" + request_digest
    assert message_hash == MANIFEST["positive"]["request"]["message_hash"]
    assert request["signature"] == MANIFEST["positive"]["request"]["signature"]


def test_agent_city_provenance_invariants_use_rfc3339_parser() -> None:
    for label, root_label in (("origin", "origin_identity_root"), ("target", "target_identity_root")):
        enrollment = load_canonical(_raw(f"provenance/{label}_root_enrollment.json"))
        certificate = load_canonical(_raw(f"provenance/{label}_signing_key_certificate.json"))
        assert set(enrollment) == {"enrollment_version", "identity_root_public_key", "node_id", "not_before", "provenance_digest", "registry_epoch", "root_signature"}
        assert set(certificate) == {"activation_at", "activation_epoch", "certificate_epoch", "certificate_version", "identity_root_public_key", "key_id", "node_id", "not_after", "not_before", "registry_epoch", "revocation_ref", "rotation_kind", "signer_key", "root_signature"}
        assert enrollment["identity_root_public_key"] == certificate["identity_root_public_key"]
        assert enrollment["node_id"] == certificate["node_id"] == node_id(_public(root_label))
        assert certificate["key_id"] == key_id(base64.b64decode(certificate["signer_key"], validate=True))
        assert certificate["rotation_kind"] == "regular" and certificate["revocation_ref"] is None
        assert rfc3339(enrollment["not_before"]) <= rfc3339(certificate["activation_at"]) == rfc3339(certificate["not_before"])
        assert rfc3339(certificate["not_before"]) <= rfc3339(FIXTURE_NOW) <= rfc3339(certificate["not_after"])


def test_agent_city_negative_fixtures_share_first_general_failure() -> None:
    positive = _raw("messages/delegate_task.json")
    request = load_canonical(positive)
    authorized = {MANIFEST["positive"]["request"]["origin_key_id"], MANIFEST["positive"]["root_enrollment"]["target"]["key_id"]}
    observed = []
    for case in MANIFEST["negative"]:
        raw = _raw(case["path"])
        result = validate_fixture(raw, root_public=_public("origin_identity_root"), target=MANIFEST["positive"]["request"]["target_node_id"], authorized_key_ids=authorized, existing_bytes=positive, existing_request_digest=request["payload"]["request_digest"])
        assert result is not None, case["id"]
        code, phase = result
        observed.append((case["id"], code, phase))
        assert code == case["expected_reject_code"], case["id"]
        assert phase == case["validation_phase"], case["id"]
    assert len(observed) == 17
