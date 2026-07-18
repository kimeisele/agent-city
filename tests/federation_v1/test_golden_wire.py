from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from .reference import (
    CERT_DOMAIN,
    DOMAIN,
    ROOT_DOMAIN,
    Reject,
    canonical,
    envelope_digest,
    key_id,
    load_canonical,
    node_id,
    semantic_request_digest,
    sha256_hex,
    verify,
)

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "federation_v1"
MANIFEST = json.loads((ROOT / "manifest.json").read_bytes())
KEYS = json.loads((ROOT / "keys" / "test_keys.json").read_bytes())


def public(label: str) -> bytes:
    return base64.b64decode(KEYS[label]["public_key_b64"], validate=True)


def classify(raw: bytes) -> str:
    try:
        value = load_canonical(raw)
    except Reject as exc:
        return str(exc)
    if "certificate_version" in value:
        if value["revocation_ref"] is not None:
            return "key_revoked"
        if value["not_after"] < "2026-07-18T11:00:00Z":
            return "certificate_expired"
        return "unclassified"
    expected = envelope_digest(value)
    if expected != value.get("message_hash"):
        return "message_hash_mismatch"
    if "-" in value["signature"] or "_" in value["signature"]:
        return "url_safe_base64_forbidden"
    try:
        signature = base64.b64decode(value["signature"], validate=True)
        signer = base64.b64decode(value["signer_key"], validate=True)
    except (ValueError, TypeError):
        return "invalid_base64"
    if len(signature) != 64 or len(signer) != 32:
        return "invalid_base64"
    if value["target_node_id"] != MANIFEST["positive"]["request"]["target_node_id"]:
        return "wrong_target"
    if value["key_id"] in {
        MANIFEST["positive"]["request"]["origin_key_id"],
        MANIFEST["positive"]["root_enrollment"]["target"]["key_id"],
    } and not verify(signer, DOMAIN, value["message_hash"], value["signature"]):
        return "signature_invalid_wrong_key"
    if value["key_id"] not in {
        MANIFEST["positive"]["request"]["origin_key_id"],
        MANIFEST["positive"]["root_enrollment"]["target"]["key_id"],
    }:
        return "key_not_authorized"
    positive = load_canonical((ROOT / "messages" / "delegate_task.json").read_bytes())
    if value.get("message_id") == positive["message_id"] and raw != (ROOT / "messages" / "delegate_task.json").read_bytes():
        return "message_id_conflict"
    if value.get("payload", {}).get("delegation_id") == positive["payload"]["delegation_id"] and value.get("payload", {}).get("request_digest") != positive["payload"]["request_digest"]:
        return "duplicate_conflict"
    return "unclassified"


def test_fixture_manifest_hashes() -> None:
    for relative, expected in MANIFEST["artifacts"].items():
        assert sha256_hex((ROOT / relative).read_bytes()) == expected


def test_provenance_parity() -> None:
    for label, root_label, signing_label in (
        ("origin", "origin_identity_root", "origin_signing_key"),
        ("target", "target_identity_root", "target_signing_key"),
    ):
        enrollment = load_canonical((ROOT / f"provenance/{label}_root_enrollment.json").read_bytes())
        root_public = public(root_label)
        assert enrollment["node_id"] == node_id(root_public)
        assert verify(
            root_public,
            ROOT_DOMAIN,
            sha256_hex(canonical({k: v for k, v in enrollment.items() if k != "root_signature"})),
            enrollment["root_signature"],
        )
        certificate = load_canonical((ROOT / f"provenance/{label}_signing_key_certificate.json").read_bytes())
        assert certificate["node_id"] == enrollment["node_id"]
        signing_public = base64.b64decode(certificate["signer_key"], validate=True)
        assert certificate["key_id"] == key_id(signing_public)
        assert verify(
            root_public,
            CERT_DOMAIN,
            sha256_hex(canonical({k: v for k, v in certificate.items() if k != "root_signature"})),
            certificate["root_signature"],
        )


def test_delegate_task_matches_steward_fixture_constants() -> None:
    envelope = load_canonical((ROOT / "messages" / "delegate_task.json").read_bytes())
    payload = envelope["payload"]
    assert semantic_request_digest(payload, envelope["source_node_id"], envelope["target_node_id"]) == payload["request_digest"]
    assert payload["idempotency_key"] == "fedv1:" + payload["request_digest"]
    assert envelope_digest(envelope) == envelope["message_hash"]
    assert verify(public("origin_signing_key"), DOMAIN, envelope["message_hash"], envelope["signature"])
    assert envelope["message_hash"] == MANIFEST["positive"]["request"]["message_hash"]
    assert envelope["signature"] == MANIFEST["positive"]["request"]["signature"]
    assert node_id(public("origin_identity_root")) == MANIFEST["positive"]["request"]["origin_node_id"]
    assert key_id(public("origin_signing_key")) == MANIFEST["positive"]["request"]["origin_key_id"]


@pytest.mark.parametrize("case", MANIFEST["negative"])
def test_negative_fixture_rejects_at_declared_boundary(case: dict) -> None:
    assert classify((ROOT / case["path"]).read_bytes()) == case["expected_reject_code"], case["id"]
