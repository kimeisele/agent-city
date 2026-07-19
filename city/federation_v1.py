"""Agent City production boundary for Federation Delegation V1 admission.

Additive V1 code only: legacy federation directives and worker execution are not called.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DOMAIN = b"STEWARD-FEDERATION-DELEGATION-V1\x00"
CONTRACT = "federation-delegation-v1"
REQUEST_CARRIER = "federation_v1.delegate_task"
RECEIPT_CARRIER = "federation_v1.delegation_receipt"
FEATURE_GATE_DEFAULT = False
MAX_WIRE = 256 * 1024
MAX_B64 = 349528
NODE_RE = re.compile(r"^ag_[0-9a-f]{32}$")
KEY_RE = re.compile(r"^key_[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
REQUEST_KEYS = {
    "contract_version",
    "message_id",
    "request_message_id",
    "source_node_id",
    "target_node_id",
    "operation",
    "correlation_id",
    "payload",
    "issued_at",
    "expires_at",
    "message_hash",
    "signature",
    "signer_key",
    "key_id",
}
RECEIPT_KEYS = REQUEST_KEYS | {"causation_message_id"}
DOMAIN_ROOT_ENROLLMENT = "STEWARD-FEDERATION-ROOT-ENROLLMENT-V1"
DOMAIN_SIGNING_KEY_AUTH = "STEWARD-FEDERATION-SIGNING-KEY-AUTH-V1"
ASSIGNMENT_ATTESTATION_DOMAIN = b"STEWARD-FEDERATION-ASSIGNMENT-ATTESTATION-V1\x00"
ASSIGNMENT_SOURCE_DOMAIN = b"STEWARD-FEDERATION-ASSIGNMENT-SOURCE-V1\x00"
ASSIGNMENT_CANDIDATE_DOMAIN = b"STEWARD-FEDERATION-ASSIGNMENT-CANDIDATE-V1\x00"
ASSIGNMENT_AUTHORITY_DOMAIN = b"STEWARD-FEDERATION-ASSIGNMENT-AUTHORITY-V1\x00"
ENROLLMENT_KEYS = {
    "enrollment_version",
    "identity_root_public_key",
    "node_id",
    "not_before",
    "provenance_digest",
    "registry_epoch",
    "root_signature",
}
CERTIFICATE_KEYS = {
    "activation_at",
    "activation_epoch",
    "certificate_epoch",
    "certificate_version",
    "identity_root_public_key",
    "key_id",
    "node_id",
    "not_after",
    "not_before",
    "registry_epoch",
    "revocation_ref",
    "rotation_kind",
    "signer_key",
    "root_signature",
}
_REGISTRY_TOKEN = object()
TARGET_RECORD_KEYS = {
    "delegation_id",
    "request_message_id",
    "request_message_hash",
    "origin_node_id",
    "target_node_id",
    "request_digest",
    "idempotency_key",
    "request_wire_bytes_b64",
    "request_carrier",
    "state",
    "reason_code",
    "target_work_id",
    "receipt_message_id",
    "receipt_id",
    "receipt_content_digest",
    "receipt_message_hash",
    "receipt_signature",
    "receipt_wire_bytes_b64",
    "receipt_send_status",
}
ASSIGNMENT_RECORD_FIELDS = {
    "assignment_state",
    "assignment_epoch",
    "assigned_candidate_id",
    "observed_candidate_snapshot",
    "worker_snapshot_digest",
    "assignment_authority_digest",
    "assigned_at",
    "assignment_attestation_id",
    "assignment_content_digest",
    "assignment_message_hash",
    "assignment_signature",
    "assignment_wire_bytes_b64",
}
ASSIGNMENT_NULL_FIELDS = {
    "assignment_epoch",
    "assigned_candidate_id",
    "observed_candidate_snapshot",
    "worker_snapshot_digest",
    "assignment_authority_digest",
    "assigned_at",
    "assignment_attestation_id",
    "assignment_content_digest",
    "assignment_message_hash",
    "assignment_signature",
    "assignment_wire_bytes_b64",
}
ASSIGNMENT_ASSIGNED_FIELDS = ASSIGNMENT_NULL_FIELDS
ASSIGNMENT_ATTESTATION_KEYS = {
    "assignment_attestation_id",
    "assignment_attestation_version",
    "assignment_authority_digest",
    "assignment_content_digest",
    "assignment_epoch",
    "assignment_message_hash",
    "assignment_signature",
    "assignment_state",
    "delegation_id",
    "key_id",
    "observed_at",
    "origin_node_id",
    "signer_key",
    "target_node_id",
    "target_work_id",
    "worker_snapshot_digest",
}
ORIGIN_RECORD_KEYS = {
    "delegation_id",
    "origin_task_id",
    "origin_node_id",
    "request_message_id",
    "correlation_id",
    "target_node_id",
    "request_digest",
    "idempotency_key",
    "request_message_hash",
    "request_wire_bytes_b64",
    "request_carrier",
    "request_send_status",
    "send_state",
    "target_work_id",
}


class V1Reject(ValueError):
    def __init__(self, code: str, phase: str):
        super().__init__(code)
        self.code, self.phase = code, phase


@dataclass(frozen=True)
class ValidatedFederationV1Key:
    key_id: str
    node_id: str
    public_key: bytes
    not_before: str
    not_after: str
    registry_epoch: int
    certificate_epoch: int
    activation_epoch: int
    revoked: bool = False


class ValidatedFederationV1KeyRegistry:
    """Immutable provenance-validated key snapshot required by V1 validation."""

    def __init__(
        self,
        records: Mapping[str, ValidatedFederationV1Key],
        _token: object | None = None,
    ):
        if _token is not _REGISTRY_TOKEN:
            raise V1Reject("registry_unvalidated", "registry")
        if (
            not isinstance(records, Mapping)
            or not records
            or not all(
                isinstance(key, str) and isinstance(value, ValidatedFederationV1Key)
                for key, value in records.items()
            )
        ):
            raise V1Reject("registry_unvalidated", "registry")
        self._records = dict(records)

    @classmethod
    def from_provenance(
        cls,
        enrollments: Iterable[Mapping[str, Any]],
        certificates: Iterable[Mapping[str, Any]],
        *,
        now: str,
    ) -> "ValidatedFederationV1KeyRegistry":
        current = _time(now)
        roots: dict[str, tuple[bytes, Mapping[str, Any]]] = {}
        for enrollment in enrollments:
            if not isinstance(enrollment, Mapping) or set(enrollment) != ENROLLMENT_KEYS:
                raise V1Reject("provenance_schema", "provenance")
            try:
                root = _decode(enrollment["identity_root_public_key"], 32)
                node_id = str(enrollment["node_id"])
                not_before = _time(enrollment["not_before"])
                epoch = enrollment["registry_epoch"]
                provenance_digest = enrollment["provenance_digest"]
                signature = _decode(enrollment["root_signature"], 64)
            except (KeyError, TypeError):
                raise V1Reject("provenance_schema", "provenance")
            if (
                enrollment["enrollment_version"] != "federation-root-enrollment-v1"
                or not NODE_RE.fullmatch(node_id)
                or not isinstance(epoch, int)
                or epoch < 1
                or not HASH_RE.fullmatch(str(provenance_digest))
            ):
                raise V1Reject("provenance_schema", "provenance")
            if not_before > current or node_id != _derive_node_id(root):
                raise V1Reject("node_id_mismatch", "provenance")
            body = {key: value for key, value in enrollment.items() if key != "root_signature"}
            _verify_root_signature(root, DOMAIN_ROOT_ENROLLMENT, body, signature)
            if node_id in roots and roots[node_id][0] != root:
                raise V1Reject("provenance_conflict", "provenance")
            roots[node_id] = (root, enrollment)
        records: dict[str, ValidatedFederationV1Key] = {}
        for certificate in certificates:
            if not isinstance(certificate, Mapping) or set(certificate) != CERTIFICATE_KEYS:
                raise V1Reject("provenance_schema", "provenance")
            try:
                root = _decode(certificate["identity_root_public_key"], 32)
                signer = _decode(certificate["signer_key"], 32)
                signature = _decode(certificate["root_signature"], 64)
                node_id = str(certificate["node_id"])
                key_id = str(certificate["key_id"])
                not_before = _time(certificate["not_before"])
                not_after = _time(certificate["not_after"])
                activation_at = _time(certificate["activation_at"])
                registry_epoch = certificate["registry_epoch"]
                certificate_epoch = certificate["certificate_epoch"]
                activation_epoch = certificate["activation_epoch"]
            except (KeyError, TypeError):
                raise V1Reject("provenance_schema", "provenance")
            root_node = _derive_node_id(root)
            if (
                certificate["certificate_version"] != "federation-signing-key-auth-v1"
                or certificate["rotation_kind"] not in {"regular", "emergency"}
                or node_id != root_node
                or not NODE_RE.fullmatch(node_id)
                or key_id != _derive_key_id(signer)
            ):
                raise V1Reject("certificate_key_binding", "provenance")
            if node_id not in roots or roots[node_id][0] != root:
                raise V1Reject("root_key_binding", "provenance")
            if any(
                not isinstance(epoch, int) or epoch < 1
                for epoch in (registry_epoch, certificate_epoch, activation_epoch)
            ):
                raise V1Reject("provenance_epoch", "provenance")
            if (
                registry_epoch != roots[node_id][1]["registry_epoch"]
                or activation_epoch < certificate_epoch
                or activation_at != not_before
                or not_after <= not_before
            ):
                raise V1Reject("certificate_time_window", "provenance")
            if not (not_before <= current < not_after) or activation_at > current:
                raise V1Reject("certificate_expired", "registry_time")
            body = {key: value for key, value in certificate.items() if key != "root_signature"}
            _verify_root_signature(root, DOMAIN_SIGNING_KEY_AUTH, body, signature)
            if key_id in records:
                raise V1Reject("provenance_conflict", "provenance")
            records[key_id] = ValidatedFederationV1Key(
                key_id=key_id,
                node_id=node_id,
                public_key=signer,
                not_before=certificate["not_before"],
                not_after=certificate["not_after"],
                registry_epoch=registry_epoch,
                certificate_epoch=certificate_epoch,
                activation_epoch=activation_epoch,
                revoked=certificate["revocation_ref"] is not None,
            )
        return cls(records, _REGISTRY_TOKEN)

    def lookup(self, key_id: str, *, at: str) -> ValidatedFederationV1Key:
        record = self._records.get(key_id)
        if record is None:
            raise V1Reject("key_not_authorized", "registry")
        moment = _time(at)
        if record.revoked:
            raise V1Reject("key_revoked", "registry_status")
        if not _time(record.not_before) <= moment < _time(record.not_after):
            raise V1Reject("certificate_expired", "registry_time")
        return record


def _quote(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise V1Reject("rejected_noncanonical", "sfdj_nfc")
    value.encode("utf-8")
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        .replace("\\b", "\\u0008")
        .replace("\\t", "\\u0009")
        .replace("\\n", "\\u000a")
        .replace("\\f", "\\u000c")
        .replace("\\r", "\\u000d")
    )


def _emit(value: Any, depth: int = 0) -> str:
    if depth > 16:
        raise V1Reject("max_depth", "sfdj_schema")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value <= 2**63 - 1:
            raise V1Reject("integer_range", "sfdj_number")
        return str(value)
    if isinstance(value, float):
        raise V1Reject("float_forbidden", "sfdj_number")
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, list):
        if len(value) > 1024:
            raise V1Reject("array_limit", "sfdj_schema")
        return "[" + ",".join(_emit(item, depth + 1) for item in value) + "]"
    if isinstance(value, dict):
        if len(value) > 1024:
            raise V1Reject("object_limit", "sfdj_schema")
        keys = []
        for key in value:
            if not isinstance(key, str) or unicodedata.normalize("NFC", key) != key:
                raise V1Reject("rejected_noncanonical", "sfdj_nfc")
            if len(key.encode("utf-8")) > 256:
                raise V1Reject("object_key_limit", "sfdj_schema")
            keys.append(key)
        keys.sort(key=lambda item: item.encode("utf-8"))
        return (
            "{" + ",".join(_quote(key) + ":" + _emit(value[key], depth + 1) for key in keys) + "}"
        )
    raise V1Reject("unsupported_type", "sfdj_schema")


def canonical_bytes(value: Any) -> bytes:
    raw = _emit(value).encode("utf-8")
    if len(raw) > MAX_WIRE:
        raise V1Reject("envelope_limit", "sfdj_size")
    return raw


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V1Reject("duplicate_json_key", "parse")
        result[key] = value
    return result


def parse_canonical(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise V1Reject("bom_forbidden", "parse")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                V1Reject("float_forbidden", "sfdj_number")
            ),
        )
    except V1Reject:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V1Reject("invalid_json", "parse") from exc
    if canonical_bytes(value) != raw:
        raise V1Reject("rejected_noncanonical", "sfdj_key_order")
    if not isinstance(value, dict):
        raise V1Reject("envelope_object_required", "sfdj_schema")
    return value


def _time(value: str) -> dt.datetime:
    if not isinstance(value, str) or not TIME_RE.fullmatch(value):
        raise V1Reject("timestamp_invalid", "timestamp")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    except ValueError as exc:
        raise V1Reject("timestamp_invalid", "timestamp") from exc


def _expires(value: str) -> str:
    return (_time(value) + dt.timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode(value: object, expected: int) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) % 4
        or len(value) > MAX_B64
        or "-" in value
        or "_" in value
        or any(ch.isspace() for ch in value)
    ):
        raise V1Reject("invalid_base64", "base64")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise V1Reject("invalid_base64", "base64") from exc
    if len(raw) != expected or base64.b64encode(raw).decode("ascii") != value:
        raise V1Reject("invalid_base64", "base64")
    return raw


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _derive_node_id(public_key: bytes) -> str:
    return "ag_" + hashlib.sha256(public_key.hex().encode("ascii")).hexdigest()[:32]


def _derive_key_id(public_key: bytes) -> str:
    return "key_" + hashlib.sha256(public_key).hexdigest()


def _verify_root_signature(
    public_key: bytes, domain: str, body: Mapping[str, Any], signature: bytes
) -> None:
    digest = _digest(body)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, domain.encode("utf-8") + b"\x00" + bytes.fromhex(digest)
        )
    except (InvalidSignature, ValueError) as exc:
        raise V1Reject("provenance_signature_invalid", "signature") from exc


def _sig_input(digest: str) -> bytes:
    return DOMAIN + bytes.fromhex(digest)


def request_digest(payload: Mapping[str, Any], source: str, target: str) -> str:
    fields = (
        "delegation_id",
        "origin_task_id",
        "capability",
        "intent",
        "task_description",
        "target_repo",
        "authority",
        "expected_outcome",
        "verification_contract",
        "deadline",
    )
    return _digest(
        {
            "contract_version": CONTRACT,
            "operation": "delegate_task",
            "source_node_id": source,
            "target_node_id": target,
            "payload": {field: payload[field] for field in fields},
        }
    )


def build_request(
    *,
    payload: Mapping[str, Any],
    source: str,
    target: str,
    message_id: str,
    signing_key: Ed25519PrivateKey,
    signer_key_b64: str,
    key_id: str,
    issued_at: str,
    expires_at: str,
) -> bytes:
    body_payload = dict(payload)
    digest = request_digest(body_payload, source, target)
    body_payload.update({"request_digest": digest, "idempotency_key": "fedv1:" + digest})
    envelope = {
        "contract_version": CONTRACT,
        "message_id": message_id,
        "request_message_id": message_id,
        "source_node_id": source,
        "target_node_id": target,
        "operation": "delegate_task",
        "correlation_id": body_payload["delegation_id"],
        "payload": body_payload,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "signer_key": signer_key_b64,
        "key_id": key_id,
    }
    message = _digest(envelope)
    envelope.update(
        {"message_hash": message, "signature": _b64(signing_key.sign(_sig_input(message)))}
    )
    return canonical_bytes(envelope)


def build_admission_receipt(
    *,
    request: Mapping[str, Any],
    target: str,
    origin: str,
    message_id: str,
    receipt_id: str,
    target_work_id: str | None,
    status: str,
    reason_code: str | None,
    signing_key: Ed25519PrivateKey,
    signer_key_b64: str,
    key_id: str,
    issued_at: str,
) -> bytes:
    if status == "accepted" and not target_work_id:
        raise ValueError("accepted requires work id")
    if status == "rejected" and target_work_id is not None:
        raise ValueError("rejected forbids work id")
    content = {
        "receipt_id": receipt_id,
        "delegation_id": request["payload"]["delegation_id"],
        "receipt_stage": "admission",
        "issuer_role": "target_node",
        "status": status,
        "target_work_id": target_work_id,
        "reason_code": reason_code,
        "evidence_refs": [],
    }
    payload = {**content, "receipt_content_digest": _digest(content)}
    envelope = {
        "contract_version": CONTRACT,
        "message_id": message_id,
        "request_message_id": request["request_message_id"],
        "causation_message_id": request["message_id"],
        "source_node_id": target,
        "target_node_id": origin,
        "operation": "delegation_receipt",
        "correlation_id": request["correlation_id"],
        "payload": payload,
        "issued_at": issued_at,
        "expires_at": _expires(issued_at),
        "signer_key": signer_key_b64,
        "key_id": key_id,
    }
    message = _digest(envelope)
    envelope.update(
        {"message_hash": message, "signature": _b64(signing_key.sign(_sig_input(message)))}
    )
    return canonical_bytes(envelope)


def _registry(
    registry: ValidatedFederationV1KeyRegistry, key: str, *, at: str
) -> tuple[str, bytes, ValidatedFederationV1Key]:
    if not isinstance(registry, ValidatedFederationV1KeyRegistry):
        raise V1Reject("registry_unvalidated", "registry")
    entry = registry.lookup(key, at=at)
    return entry.node_id, entry.public_key, entry


def validate_envelope(
    raw: bytes,
    *,
    registry: ValidatedFederationV1KeyRegistry,
    expected_target: str,
    operation: str,
    now: str,
) -> dict[str, Any]:
    value = parse_canonical(raw)
    if set(value) != (REQUEST_KEYS if operation == "delegate_task" else RECEIPT_KEYS):
        raise V1Reject("schema_field_set", "schema")
    if value["contract_version"] != CONTRACT or value["operation"] != operation:
        raise V1Reject("unsupported_contract", "schema")
    if not NODE_RE.fullmatch(str(value["source_node_id"])) or not NODE_RE.fullmatch(
        str(value["target_node_id"])
    ):
        raise V1Reject("node_id_invalid", "schema")
    if value["target_node_id"] != expected_target:
        raise V1Reject("wrong_target", "target_match")
    if not ID_RE.fullmatch(str(value["message_id"])) or not ID_RE.fullmatch(
        str(value["request_message_id"])
    ):
        raise V1Reject("id_invalid", "schema")
    if value["request_message_id"] != value["message_id"] and "causation_message_id" not in value:
        raise V1Reject("request_root_invalid", "schema")
    issued, expires, current = _time(value["issued_at"]), _time(value["expires_at"]), _time(now)
    if expires <= issued:
        raise V1Reject("timestamp_window_invalid", "timestamp")
    if not issued <= current < expires:
        raise V1Reject("expired", "registry_time")
    signer, signature = _decode(value["signer_key"], 32), _decode(value["signature"], 64)
    if not KEY_RE.fullmatch(str(value["key_id"])):
        raise V1Reject("key_id_invalid", "schema")
    node, authorized, entry = _registry(registry, value["key_id"], at=value["issued_at"])
    if node != value["source_node_id"] or authorized != signer:
        raise V1Reject("key_not_authorized", "registry")
    expected = _digest(
        {key: item for key, item in value.items() if key not in {"message_hash", "signature"}}
    )
    if value["message_hash"] != expected:
        raise V1Reject("message_hash_mismatch", "message_hash")
    try:
        Ed25519PublicKey.from_public_bytes(signer).verify(
            signature, _sig_input(value["message_hash"])
        )
    except (InvalidSignature, ValueError) as exc:
        raise V1Reject("signature_invalid", "signature") from exc
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise V1Reject("payload_schema", "schema")
    if operation == "delegate_task":
        required = {
            "delegation_id",
            "origin_task_id",
            "capability",
            "intent",
            "task_description",
            "target_repo",
            "authority",
            "expected_outcome",
            "verification_contract",
            "deadline",
            "request_digest",
            "idempotency_key",
        }
        if not required <= set(payload) or set(payload) - required - {
            "display_title",
            "display_description",
        }:
            raise V1Reject("payload_schema", "schema")
        try:
            computed = request_digest(payload, value["source_node_id"], value["target_node_id"])
        except (KeyError, TypeError):
            raise V1Reject("request_digest_mismatch", "request_digest")
        if (
            payload["request_digest"] != computed
            or payload["idempotency_key"] != "fedv1:" + computed
        ):
            raise V1Reject("request_digest_mismatch", "request_digest")
    else:
        required = {
            "receipt_id",
            "delegation_id",
            "receipt_stage",
            "issuer_role",
            "status",
            "target_work_id",
            "reason_code",
            "evidence_refs",
            "receipt_content_digest",
        }
        if (
            set(payload) != required
            or payload["receipt_stage"] != "admission"
            or payload["issuer_role"] != "target_node"
        ):
            raise V1Reject("receipt_schema", "schema")
        if payload["status"] == "accepted" and not payload["target_work_id"]:
            raise V1Reject("receipt_schema", "schema")
        if payload["status"] == "rejected" and payload["target_work_id"] is not None:
            raise V1Reject("receipt_schema", "schema")
        content = {key: item for key, item in payload.items() if key != "receipt_content_digest"}
        if payload["receipt_content_digest"] != _digest(content):
            raise V1Reject("receipt_content_digest_mismatch", "receipt_digest")
    return value


def build_carrier(raw: bytes) -> dict[str, Any]:
    inner = parse_canonical(raw)
    operation = (
        REQUEST_CARRIER
        if inner["operation"] == "delegate_task"
        else RECEIPT_CARRIER
        if inner["operation"] == "delegation_receipt"
        else None
    )
    if operation is None:
        raise V1Reject("unsupported_contract", "carrier_operation")
    return {
        "operation": operation,
        "source": inner["source_node_id"],
        "target": inner["target_node_id"],
        "payload": {"wire_version": CONTRACT, "wire_bytes_b64": _b64(raw)},
    }


def carrier_inner(carrier: Mapping[str, Any], expected_target: str) -> tuple[dict[str, Any], bytes]:
    if (
        set(carrier) != {"operation", "source", "target", "payload"}
        or not isinstance(carrier.get("payload"), Mapping)
        or set(carrier["payload"]) != {"wire_version", "wire_bytes_b64"}
    ):
        raise V1Reject("carrier_schema", "carrier")
    if (
        carrier["target"] != expected_target
        or not NODE_RE.fullmatch(str(carrier["source"]))
        or not NODE_RE.fullmatch(str(carrier["target"]))
    ):
        raise V1Reject("wrong_target", "carrier_target")
    if carrier["payload"]["wire_version"] != CONTRACT:
        raise V1Reject("unsupported_contract", "carrier_schema")
    encoded = carrier["payload"]["wire_bytes_b64"]
    if not isinstance(encoded, str) or len(encoded) > MAX_B64:
        raise V1Reject("invalid_base64", "carrier")
    try:
        raw = _decode(encoded, len(base64.b64decode(encoded, validate=True)))
    except (ValueError, TypeError) as exc:
        raise V1Reject("invalid_base64", "carrier") from exc
    inner = parse_canonical(raw)
    expected_operation = (
        REQUEST_CARRIER
        if inner.get("operation") == "delegate_task"
        else RECEIPT_CARRIER
        if inner.get("operation") == "delegation_receipt"
        else None
    )
    if carrier["source"] != inner.get("source_node_id") or carrier["target"] != inner.get(
        "target_node_id"
    ):
        raise V1Reject("carrier_identity_mismatch", "carrier_binding")
    if carrier["operation"] != expected_operation:
        raise V1Reject("carrier_operation_mismatch", "carrier_binding")
    return inner, raw


@contextlib.contextmanager
def _process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _load(path: Path, required_record_keys: set[str]) -> dict[str, Any]:
    if not path.exists():
        return {"delegations": {}, "findings": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V1Reject("ledger_corrupt", "ledger") from exc
    if (
        not isinstance(value, dict)
        or set(value) - {"delegations", "findings"}
        or not isinstance(value.get("delegations"), dict)
    ):
        raise V1Reject("ledger_corrupt", "ledger")
    findings = value.setdefault("findings", [])
    if not isinstance(findings, list):
        raise V1Reject("ledger_corrupt", "ledger")
    for delegation_id, record in value["delegations"].items():
        if (
            not isinstance(delegation_id, str)
            or not isinstance(record, dict)
            or not required_record_keys <= set(record)
            or record.get("delegation_id") != delegation_id
        ):
            raise V1Reject("ledger_corrupt", "ledger")
        if required_record_keys is TARGET_RECORD_KEYS:
            if record.get("state") not in {"ACCEPTED", "REJECTED"} or record.get(
                "receipt_send_status"
            ) not in {"pending", "sent"}:
                raise V1Reject("ledger_corrupt", "ledger")
            _validate_assignment_record(record)
        elif record.get("request_send_status") not in {"created", "sent"} or record.get(
            "send_state"
        ) not in {"created", "sent", "admission_received", "admission_rejected"}:
            raise V1Reject("ledger_corrupt", "ledger")
    if any(
        not isinstance(item, dict) or not isinstance(item.get("code"), str) for item in findings
    ):
        raise V1Reject("ledger_corrupt", "ledger")
    return value


def _validate_assignment_record(record: Mapping[str, Any]) -> None:
    """Validate optional Slice-02 fields without breaking Slice-01A records."""
    present = set(record) & ASSIGNMENT_RECORD_FIELDS
    if not present:
        return
    state = record.get("assignment_state")
    if state not in {"ACCEPTED", "ASSIGNED", None}:
        raise V1Reject("ledger_corrupt", "ledger")
    if record.get("state") == "REJECTED":
        if state not in {None, "ACCEPTED"} or any(
            record.get(key) is not None for key in ASSIGNMENT_NULL_FIELDS
        ):
            raise V1Reject("ledger_corrupt", "ledger")
        return
    if state == "ASSIGNED":
        if not ASSIGNMENT_ASSIGNED_FIELDS <= set(record):
            raise V1Reject("ledger_corrupt", "ledger")
        if record.get("assignment_epoch") != 1:
            raise V1Reject("ledger_corrupt", "ledger")
        if not isinstance(record.get("observed_candidate_snapshot"), dict):
            raise V1Reject("ledger_corrupt", "ledger")
        string_fields = ASSIGNMENT_NULL_FIELDS - {"observed_candidate_snapshot", "assignment_epoch"}
        if not all(isinstance(record.get(key), str) and record.get(key) for key in string_fields):
            raise V1Reject("ledger_corrupt", "ledger")
        _validate_assignment_attestation_record(record)
    elif any(record.get(key) is not None for key in ASSIGNMENT_NULL_FIELDS):
        raise V1Reject("ledger_corrupt", "ledger")


def _validate_assignment_attestation_record(record: Mapping[str, Any]) -> None:
    try:
        encoded = record["assignment_wire_bytes_b64"]
        decoded = base64.b64decode(encoded, validate=True)
        raw = _decode(encoded, len(decoded))
        attestation = parse_canonical(raw)
    except (KeyError, TypeError, ValueError, V1Reject) as exc:
        raise V1Reject("ledger_corrupt", "assignment_attestation") from exc
    if set(attestation) != ASSIGNMENT_ATTESTATION_KEYS:
        raise V1Reject("ledger_corrupt", "assignment_attestation")
    if any(
        attestation.get(field) != record.get(field)
        for field in (
            "assignment_attestation_id",
            "assignment_authority_digest",
            "assignment_content_digest",
            "assignment_epoch",
            "assignment_message_hash",
            "assignment_signature",
            "assignment_state",
            "delegation_id",
            "origin_node_id",
            "target_node_id",
            "target_work_id",
            "worker_snapshot_digest",
        )
    ):
        raise V1Reject("ledger_corrupt", "assignment_attestation")
    if attestation["observed_at"] != record.get("assigned_at"):
        raise V1Reject("ledger_corrupt", "assignment_attestation")
    if attestation["assignment_attestation_version"] != "federation-assignment-attestation-v1":
        raise V1Reject("ledger_corrupt", "assignment_attestation")
    content = {
        key: value
        for key, value in attestation.items()
        if key
        not in {
            "assignment_attestation_id",
            "assignment_content_digest",
            "assignment_message_hash",
            "assignment_signature",
            "key_id",
            "signer_key",
        }
    }
    if attestation["assignment_content_digest"] != _digest(content):
        raise V1Reject("ledger_corrupt", "assignment_attestation")
    message_body = {
        key: value
        for key, value in attestation.items()
        if key not in {"assignment_message_hash", "assignment_signature"}
    }
    if attestation["assignment_message_hash"] != _digest(message_body):
        raise V1Reject("ledger_corrupt", "assignment_attestation")
    try:
        signer_public_key = _decode(attestation["signer_key"], 32)
        if not KEY_RE.fullmatch(attestation["key_id"]):
            raise V1Reject("ledger_corrupt", "assignment_attestation")
        if _derive_key_id(signer_public_key) != attestation["key_id"]:
            raise V1Reject("ledger_corrupt", "assignment_attestation")
        Ed25519PublicKey.from_public_bytes(signer_public_key).verify(
            _decode(attestation["assignment_signature"], 64),
            ASSIGNMENT_ATTESTATION_DOMAIN + bytes.fromhex(attestation["assignment_message_hash"]),
        )
    except (InvalidSignature, ValueError, V1Reject) as exc:
        raise V1Reject("ledger_corrupt", "assignment_attestation") from exc


def _assignment_defaults(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a record view with non-persisting defaults for old Slice-01A rows."""
    view = dict(record)
    if "assignment_state" not in view:
        view["assignment_state"] = "ACCEPTED" if view.get("state") == "ACCEPTED" else None
    for key in ASSIGNMENT_NULL_FIELDS:
        view.setdefault(key, None)
    return view


class FederationV1CandidateSnapshotAdapter:
    """Read-only, deterministic candidate observation for Slice 02."""

    _SOURCE_FIELDS = {
        "candidate_id",
        "cartridge_id",
        "capabilities",
        "capability_tier",
        "domain",
        "capability_protocol",
        "guardian",
        "active",
    }

    def __init__(self, source: Callable[[], Iterable[Mapping[str, Any]] | Mapping[str, Any]]):
        self._source = source

    def _read(self) -> tuple[list[dict[str, Any]], str]:
        raw = self._source()
        values = list(raw.values()) if isinstance(raw, Mapping) else list(raw)
        normalized: list[dict[str, Any]] = []
        for value in values:
            if not isinstance(value, Mapping) or not set(value) <= self._SOURCE_FIELDS:
                raise V1Reject("candidate_snapshot_schema", "candidate_snapshot")
            candidate_id = value.get("candidate_id")
            cartridge_id = value.get("cartridge_id")
            capabilities = value.get("capabilities", [])
            if (
                not isinstance(candidate_id, str)
                or not ID_RE.fullmatch(candidate_id)
                or not isinstance(cartridge_id, str)
                or not ID_RE.fullmatch(cartridge_id)
                or not isinstance(capabilities, list)
                or not all(isinstance(item, str) for item in capabilities)
                or len(set(capabilities)) != len(capabilities)
                or not isinstance(value.get("active", True), bool)
            ):
                raise V1Reject("candidate_snapshot_schema", "candidate_snapshot")
            normalized.append(
                {
                    "candidate_id": candidate_id,
                    "cartridge_id": cartridge_id,
                    "capabilities": sorted(capabilities),
                    "capability_protocol": str(value.get("capability_protocol", "")),
                    "capability_tier": str(value.get("capability_tier", "observer")),
                    "domain": str(value.get("domain", "")),
                    "guardian": str(value.get("guardian", "")),
                    "active": value.get("active", True),
                }
            )
        normalized.sort(key=lambda item: (item["candidate_id"], item["cartridge_id"]))
        source_generation = "obs_" + hashlib.sha256(
            ASSIGNMENT_SOURCE_DOMAIN + canonical_bytes(normalized)
        ).hexdigest()
        return normalized, source_generation

    def observe(self, *, observed_at: str) -> dict[str, Any]:
        _time(observed_at)
        source_view, source_generation = self._read()
        candidates = [
            item
            for item in source_view
            if item["active"] and "fix_repository" in item["capabilities"]
        ]
        selected = candidates[0] if candidates else None
        snapshot = None
        if selected is not None:
            snapshot = {
                key: value
                for key, value in selected.items()
                if key != "active"
            }
            snapshot.update(
                {
                    "observed_at": observed_at,
                    "snapshot_schema": "federation-assignment-candidate-v1",
                    "source_generation": source_generation,
                }
            )
        return {
            "source_generation": source_generation,
            "candidate": snapshot,
        }


def _candidate_fingerprint(snapshot: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {key: value for key, value in snapshot.items() if key != "observed_at"}


def _assignment_authority_input(
    *,
    record: Mapping[str, Any],
    candidate: Mapping[str, Any],
    target_node_id: str,
    epoch: int,
    worker_snapshot_digest: str,
) -> dict[str, Any]:
    authority = record.get("assignment_authority")
    if not isinstance(authority, Mapping) or set(authority) != {
        "authority",
        "capability",
        "target_repo",
    }:
        raise V1Reject("assignment_authority_unavailable", "assignment_authority")
    return {
        "assignment_policy": "federation-delegation-assignment-v1",
        "assignment_epoch": epoch,
        "authority": authority["authority"],
        "candidate_id": candidate["candidate_id"],
        "capability": authority["capability"],
        "delegation_id": record["delegation_id"],
        "target_node_id": target_node_id,
        "target_work_id": record["target_work_id"],
        "worker_snapshot_digest": worker_snapshot_digest,
    }


def _assignment_authority_allows(record: Mapping[str, Any]) -> bool:
    authority = record.get("assignment_authority")
    if not isinstance(authority, Mapping) or set(authority) != {
        "authority",
        "capability",
        "target_repo",
    }:
        return False
    policy = authority["authority"]
    return (
        authority["capability"] == "fix_repository"
        and authority["target_repo"] == "agent-city"
        and isinstance(policy, Mapping)
        and policy.get("repo_scope") == "agent-city"
        and isinstance(policy.get("allowed_actions"), list)
        and set(policy["allowed_actions"]) <= {"branch", "commit", "read", "test"}
        and isinstance(policy.get("denied_actions"), list)
        and "merge" in policy["denied_actions"]
    )


def build_assignment_attestation(
    *,
    record: Mapping[str, Any],
    target_node_id: str,
    signing_key: Ed25519PrivateKey,
    signer_key_b64: str,
    key_id: str,
    candidate: Mapping[str, Any],
    worker_snapshot_digest: str,
    assignment_authority_digest: str,
    observed_at: str,
    assignment_epoch: int = 1,
) -> tuple[bytes, str]:
    if assignment_epoch != 1:
        raise V1Reject("assignment_epoch_conflict", "assignment")
    content = {
        "assignment_attestation_version": "federation-assignment-attestation-v1",
        "assignment_authority_digest": assignment_authority_digest,
        "assignment_epoch": assignment_epoch,
        "assignment_state": "ASSIGNED",
        "delegation_id": record["delegation_id"],
        "observed_at": observed_at,
        "origin_node_id": record["origin_node_id"],
        "target_node_id": target_node_id,
        "target_work_id": record["target_work_id"],
        "worker_snapshot_digest": worker_snapshot_digest,
    }
    content_digest = _digest(content)
    attestation_id = f"assignment_{record['delegation_id']}"
    envelope = {
        **content,
        "assignment_attestation_id": attestation_id,
        "assignment_content_digest": content_digest,
        "signer_key": signer_key_b64,
        "key_id": key_id,
    }
    message_hash = _digest(envelope)
    envelope.update(
        {
            "assignment_message_hash": message_hash,
            "assignment_signature": _b64(
                signing_key.sign(ASSIGNMENT_ATTESTATION_DOMAIN + bytes.fromhex(message_hash))
            ),
        }
    )
    return canonical_bytes(envelope), content_digest


class TargetAdmissionLedger:
    def __init__(self, path: str | Path):
        self.path, self._lock = Path(path), threading.RLock()

    def get(self, delegation_id: str) -> dict[str, Any] | None:
        with self._lock, _process_lock(self.path):
            record = _load(self.path, TARGET_RECORD_KEYS)["delegations"].get(delegation_id)
            return _assignment_defaults(record) if record is not None else None

    def record_finding(self, code: str, delegation_id: str | None = None) -> None:
        with self._lock, _process_lock(self.path):
            document = _load(self.path, TARGET_RECORD_KEYS)
            document["findings"].append({"code": code, "delegation_id": delegation_id})
            _atomic(self.path, document)

    def mark_receipt_sent(self, delegation_id: str) -> None:
        with self._lock, _process_lock(self.path):
            doc = _load(self.path, TARGET_RECORD_KEYS)
            if delegation_id in doc["delegations"]:
                doc["delegations"][delegation_id]["receipt_send_status"] = "sent"
                _atomic(self.path, doc)

    def commit(
        self,
        *,
        request: Mapping[str, Any],
        request_wire: bytes,
        request_carrier: Mapping[str, Any],
        receipt: Mapping[str, Any],
        receipt_wire: bytes,
        state: str,
        reason: str | None,
    ) -> tuple[str, dict[str, Any]]:
        did, digest = request["payload"]["delegation_id"], request["payload"]["request_digest"]
        with self._lock, _process_lock(self.path):
            doc, existing = _load(self.path, TARGET_RECORD_KEYS), None
            existing = doc["delegations"].get(did)
            if existing:
                if existing["request_digest"] != digest:
                    return "duplicate_conflict", existing
                if existing["request_message_id"] == request["message_id"] and existing[
                    "request_wire_bytes_b64"
                ] != _b64(request_wire):
                    return "message_id_conflict", existing
                return "duplicate", existing
            record = {
                "delegation_id": did,
                "request_message_id": request["request_message_id"],
                "request_message_hash": request["message_hash"],
                "origin_node_id": request["source_node_id"],
                "target_node_id": request["target_node_id"],
                "request_digest": digest,
                "idempotency_key": request["payload"]["idempotency_key"],
                "request_wire_bytes_b64": _b64(request_wire),
                "request_carrier": dict(request_carrier),
                "state": state,
                "reason_code": reason,
                "target_work_id": receipt["payload"].get("target_work_id"),
                "receipt_message_id": receipt["message_id"],
                "receipt_id": receipt["payload"]["receipt_id"],
                "receipt_content_digest": receipt["payload"]["receipt_content_digest"],
                "receipt_message_hash": receipt["message_hash"],
                "receipt_signature": receipt["signature"],
                "receipt_wire_bytes_b64": _b64(receipt_wire),
                "receipt_send_status": "pending",
                "assignment_authority": {
                    "authority": request["payload"]["authority"],
                    "capability": request["payload"]["capability"],
                    "target_repo": request["payload"]["target_repo"],
                },
                "assignment_state": "ACCEPTED" if state == "ACCEPTED" else None,
                **{key: None for key in ASSIGNMENT_NULL_FIELDS},
            }
            doc["delegations"][did] = record
            _atomic(self.path, doc)
            return "created", record

    def assign_candidate(
        self,
        delegation_id: str,
        *,
        target_node_id: str,
        signing_key: Ed25519PrivateKey,
        signer_key_b64: str,
        key_id: str,
        candidate_source: FederationV1CandidateSnapshotAdapter
        | Callable[[], Iterable[Mapping[str, Any]] | Mapping[str, Any]],
        observed_at: str,
    ) -> dict[str, Any]:
        """Atomically bind one observed candidate and local signed evidence."""
        adapter = (
            candidate_source
            if isinstance(candidate_source, FederationV1CandidateSnapshotAdapter)
            else FederationV1CandidateSnapshotAdapter(candidate_source)
        )
        first = self.get(delegation_id)
        if first is None:
            raise V1Reject("unknown_delegation", "assignment")
        if first.get("state") != "ACCEPTED":
            raise V1Reject("assignment_not_allowed", "assignment")
        if first.get("target_work_id") is None:
            raise V1Reject("assignment_work_id_missing", "assignment")
        if not _assignment_authority_allows(first):
            self.record_finding("assignment_authority_denied", delegation_id)
            raise V1Reject("authority_denied", "assignment_authority")

        first_observation = adapter.observe(observed_at=observed_at)
        second_observation = adapter.observe(observed_at=observed_at)
        first_candidate = first_observation.get("candidate")
        second_candidate = second_observation.get("candidate")
        if (
            first_observation["source_generation"] != second_observation["source_generation"]
            or _candidate_fingerprint(first_candidate) != _candidate_fingerprint(second_candidate)
        ):
            self.record_finding("candidate_snapshot_stale", delegation_id)
            raise V1Reject("candidate_snapshot_stale", "candidate_snapshot")
        if first_candidate is None:
            self.record_finding("assignment_unavailable", delegation_id)
            raise V1Reject("assignment_unavailable", "candidate_snapshot")

        worker_snapshot_digest = hashlib.sha256(
            ASSIGNMENT_CANDIDATE_DOMAIN + canonical_bytes(first_candidate)
        ).hexdigest()
        authority_input = _assignment_authority_input(
            record=first,
            candidate=first_candidate,
            target_node_id=target_node_id,
            epoch=1,
            worker_snapshot_digest=worker_snapshot_digest,
        )
        assignment_authority_digest = hashlib.sha256(
            ASSIGNMENT_AUTHORITY_DOMAIN + canonical_bytes(authority_input)
        ).hexdigest()
        attestation_wire, assignment_content_digest = build_assignment_attestation(
            record=first,
            target_node_id=target_node_id,
            signing_key=signing_key,
            signer_key_b64=signer_key_b64,
            key_id=key_id,
            candidate=first_candidate,
            worker_snapshot_digest=worker_snapshot_digest,
            assignment_authority_digest=assignment_authority_digest,
            observed_at=observed_at,
        )
        attestation = parse_canonical(attestation_wire)
        with self._lock, _process_lock(self.path):
            document = _load(self.path, TARGET_RECORD_KEYS)
            record = document["delegations"].get(delegation_id)
            if record is None:
                raise V1Reject("unknown_delegation", "assignment")
            current = _assignment_defaults(record)
            if current.get("assignment_state") == "ASSIGNED":
                if (
                    current.get("worker_snapshot_digest") != worker_snapshot_digest
                    or current.get("assignment_authority_digest") != assignment_authority_digest
                    or current.get("assignment_wire_bytes_b64") != _b64(attestation_wire)
                ):
                    raise V1Reject("assignment_conflict", "assignment")
                return current
            if current.get("state") != "ACCEPTED":
                raise V1Reject("assignment_not_allowed", "assignment")
            current.update(
                {
                    "assignment_state": "ASSIGNED",
                    "assignment_epoch": 1,
                    "assigned_candidate_id": first_candidate["candidate_id"],
                    "observed_candidate_snapshot": first_candidate,
                    "worker_snapshot_digest": worker_snapshot_digest,
                    "assignment_authority_digest": assignment_authority_digest,
                    "assigned_at": observed_at,
                    "assignment_attestation_id": attestation["assignment_attestation_id"],
                    "assignment_content_digest": assignment_content_digest,
                    "assignment_message_hash": attestation["assignment_message_hash"],
                    "assignment_signature": attestation["assignment_signature"],
                    "assignment_wire_bytes_b64": _b64(attestation_wire),
                }
            )
            document["delegations"][delegation_id] = current
            _atomic(self.path, document)
            return _assignment_defaults(current)


class OriginDelegationLedger:
    def __init__(self, path: str | Path):
        self.path, self._lock = Path(path), threading.RLock()

    def get(self, delegation_id: str) -> dict[str, Any] | None:
        with self._lock, _process_lock(self.path):
            return _load(self.path, ORIGIN_RECORD_KEYS)["delegations"].get(delegation_id)

    def record_finding(self, code: str, delegation_id: str | None = None) -> None:
        with self._lock, _process_lock(self.path):
            document = _load(self.path, ORIGIN_RECORD_KEYS)
            document["findings"].append({"code": code, "delegation_id": delegation_id})
            _atomic(self.path, document)

    def mark_request_sent(self, delegation_id: str) -> None:
        with self._lock, _process_lock(self.path):
            doc = _load(self.path, ORIGIN_RECORD_KEYS)
            if delegation_id in doc["delegations"]:
                doc["delegations"][delegation_id]["request_send_status"] = "sent"
                doc["delegations"][delegation_id]["send_state"] = "sent"
                _atomic(self.path, doc)

    def create_request(
        self, *, request_wire: bytes, request_carrier: Mapping[str, Any]
    ) -> dict[str, Any]:
        request = parse_canonical(request_wire)
        did = request["payload"]["delegation_id"]
        with self._lock, _process_lock(self.path):
            doc = _load(self.path, ORIGIN_RECORD_KEYS)
            if did in doc["delegations"]:
                return doc["delegations"][did]
            record = {
                "delegation_id": did,
                "origin_task_id": request["payload"]["origin_task_id"],
                "origin_node_id": request["source_node_id"],
                "request_message_id": request["request_message_id"],
                "correlation_id": request["correlation_id"],
                "target_node_id": request["target_node_id"],
                "request_digest": request["payload"]["request_digest"],
                "idempotency_key": request["payload"]["idempotency_key"],
                "request_message_hash": request["message_hash"],
                "request_wire_bytes_b64": _b64(request_wire),
                "request_carrier": dict(request_carrier),
                "request_send_status": "created",
                "send_state": "created",
                "target_work_id": None,
            }
            doc["delegations"][did] = record
            _atomic(self.path, doc)
            return record

    def apply_receipt(
        self, *, receipt: Mapping[str, Any], receipt_wire: bytes, receipt_carrier: Mapping[str, Any]
    ) -> dict[str, Any]:
        did = receipt["payload"]["delegation_id"]
        with self._lock, _process_lock(self.path):
            doc, record = _load(self.path, ORIGIN_RECORD_KEYS), None
            record = doc["delegations"].get(did)
            if record is None:
                raise V1Reject("unknown_delegation", "origin_correlation")
            if (
                receipt["source_node_id"] != record["target_node_id"]
                or receipt["target_node_id"] != record["origin_node_id"]
                or receipt["payload"]["delegation_id"] != record["delegation_id"]
                or receipt["correlation_id"] != record["delegation_id"]
                or receipt["request_message_id"] != record["request_message_id"]
                or receipt.get("causation_message_id") != record["request_message_id"]
            ):
                doc["findings"].append(
                    {"code": "receipt_correlation_conflict", "delegation_id": did}
                )
                _atomic(self.path, doc)
                raise V1Reject("receipt_correlation_conflict", "origin_correlation")
            work = receipt["payload"].get("target_work_id")
            if (
                receipt["payload"]["status"] == "accepted"
                and record.get("target_work_id") is not None
                and record["target_work_id"] != work
            ):
                raise V1Reject("receipt_ledger_conflict", "origin_correlation")
            if record.get("admission_receipt_id") is not None:
                if (
                    record["admission_receipt_id"] != receipt["payload"]["receipt_id"]
                    or record["admission_receipt_content_digest"]
                    != receipt["payload"]["receipt_content_digest"]
                ):
                    raise V1Reject("receipt_id_conflict", "origin_correlation")
                if record["admission_receipt_wire_bytes_b64"] != _b64(receipt_wire):
                    raise V1Reject("receipt_id_conflict", "origin_correlation")
                return record
            if receipt["payload"]["status"] == "accepted":
                if record["target_work_id"] is None:
                    record["target_work_id"] = work
                elif record["target_work_id"] != work:
                    raise V1Reject("receipt_ledger_conflict", "origin_correlation")
                record["send_state"] = "admission_received"
            else:
                if work is not None:
                    raise V1Reject("receipt_schema", "origin_correlation")
                record["send_state"] = "admission_rejected"
            record.update(
                {
                    "admission_receipt_message_id": receipt["message_id"],
                    "admission_receipt_id": receipt["payload"]["receipt_id"],
                    "admission_receipt_content_digest": receipt["payload"][
                        "receipt_content_digest"
                    ],
                    "admission_receipt_message_hash": receipt["message_hash"],
                    "admission_receipt_signature": receipt["signature"],
                    "admission_receipt_wire_bytes_b64": _b64(receipt_wire),
                    "admission_receipt_carrier": dict(receipt_carrier),
                }
            )
            doc["delegations"][did] = record
            _atomic(self.path, doc)
            return record


class FederationV1Origin:
    def __init__(
        self,
        *,
        ledger: OriginDelegationLedger,
        node_id: str,
        signing_key: Ed25519PrivateKey,
        signer_key_b64: str,
        key_id: str,
        enabled: bool = FEATURE_GATE_DEFAULT,
    ):
        (
            self.ledger,
            self.node_id,
            self.signing_key,
            self.signer_key_b64,
            self.key_id,
            self.enabled,
        ) = ledger, node_id, signing_key, signer_key_b64, key_id, enabled

    def create(
        self,
        *,
        payload: Mapping[str, Any],
        target_node_id: str,
        message_id: str,
        issued_at: str,
        expires_at: str,
    ) -> tuple[bytes, dict[str, Any]]:
        if not self.enabled:
            raise V1Reject("feature_disabled", "feature_gate")
        delegation_id = str(payload.get("delegation_id", ""))
        existing = self.ledger.get(delegation_id)
        if existing is not None:
            expected_payload = dict(payload)
            expected_digest = request_digest(expected_payload, self.node_id, target_node_id)
            expected_payload["request_digest"] = expected_digest
            expected_payload["idempotency_key"] = "fedv1:" + expected_digest
            stored_wire = base64.b64decode(existing["request_wire_bytes_b64"])
            stored = parse_canonical(stored_wire)
            same_request = (
                existing["request_digest"] == expected_digest
                and stored.get("source_node_id") == self.node_id
                and stored.get("target_node_id") == target_node_id
                and stored.get("message_id") == message_id
                and stored.get("request_message_id") == message_id
                and stored.get("issued_at") == issued_at
                and stored.get("expires_at") == expires_at
                and stored.get("signer_key") == self.signer_key_b64
                and stored.get("key_id") == self.key_id
                and stored.get("payload") == expected_payload
            )
            if same_request:
                return stored_wire, dict(existing["request_carrier"])
            self.ledger.record_finding("origin_request_conflict", delegation_id)
            raise V1Reject("origin_request_conflict", "origin_ledger")
        wire = build_request(
            payload=payload,
            source=self.node_id,
            target=target_node_id,
            message_id=message_id,
            signing_key=self.signing_key,
            signer_key_b64=self.signer_key_b64,
            key_id=self.key_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        carrier = build_carrier(wire)
        stored_record = self.ledger.create_request(request_wire=wire, request_carrier=carrier)
        stored_wire = base64.b64decode(stored_record["request_wire_bytes_b64"])
        stored_carrier = dict(stored_record["request_carrier"])
        if stored_wire != wire or stored_carrier != carrier:
            self.ledger.record_finding("origin_request_conflict", delegation_id)
            raise V1Reject("origin_request_conflict", "origin_ledger")
        return stored_wire, stored_carrier

    def retransmit(self, delegation_id: str) -> dict[str, Any]:
        record = self.ledger.get(delegation_id)
        if record is None:
            raise V1Reject("unknown_delegation", "origin_ledger")
        return dict(record["request_carrier"])

    def apply_receipt(
        self, *, carrier: Mapping[str, Any], registry: ValidatedFederationV1KeyRegistry, now: str
    ) -> dict[str, Any]:
        if not self.enabled:
            raise V1Reject("feature_disabled", "feature_gate")
        _, raw = carrier_inner(carrier, self.node_id)
        receipt = validate_envelope(
            raw,
            registry=registry,
            expected_target=self.node_id,
            operation="delegation_receipt",
            now=now,
        )
        return self.ledger.apply_receipt(receipt=receipt, receipt_wire=raw, receipt_carrier=carrier)


class FederationV1Admission:
    def __init__(
        self,
        *,
        ledger: TargetAdmissionLedger,
        node_id: str,
        signing_key: Ed25519PrivateKey,
        signer_key_b64: str,
        key_id: str,
        registry: ValidatedFederationV1KeyRegistry,
        enabled: bool = FEATURE_GATE_DEFAULT,
    ):
        (
            self.ledger,
            self.node_id,
            self.signing_key,
            self.signer_key_b64,
            self.key_id,
            self.registry,
            self.enabled,
        ) = ledger, node_id, signing_key, signer_key_b64, key_id, registry, enabled

    @staticmethod
    def _policy_allows(payload: Mapping[str, Any]) -> bool:
        authority = payload.get("authority")
        return (
            payload.get("capability") == "fix_repository"
            and payload.get("target_repo") == "agent-city"
            and isinstance(authority, Mapping)
            and authority.get("repo_scope") == "agent-city"
            and isinstance(authority.get("allowed_actions"), list)
            and set(authority["allowed_actions"]) <= {"branch", "commit", "read", "test"}
            and isinstance(authority.get("denied_actions"), list)
            and "merge" in authority["denied_actions"]
        )

    def handle(
        self,
        carrier: Mapping[str, Any],
        *,
        now: str,
        origin_authorized: bool = True,
        capability_available: bool = True,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            _, raw = carrier_inner(carrier, self.node_id)
            request = validate_envelope(
                raw,
                registry=self.registry,
                expected_target=self.node_id,
                operation="delegate_task",
                now=now,
            )
        except V1Reject:
            return None
        existing = self.ledger.get(request["payload"]["delegation_id"])
        if existing:
            if existing["request_digest"] != request["payload"]["request_digest"]:
                return None
            if existing["request_message_id"] == request["message_id"] and existing[
                "request_wire_bytes_b64"
            ] != _b64(raw):
                return None
            return build_carrier(base64.b64decode(existing["receipt_wire_bytes_b64"]))
        if not origin_authorized:
            status, reason, work = "rejected", "authority_denied", None
        elif not self._policy_allows(request["payload"]):
            status, reason, work = "rejected", "authority_denied", None
        elif not capability_available:
            status, reason, work = "rejected", "capability_unavailable", None
        else:
            status, reason, work = (
                "accepted",
                None,
                "work_"
                + hashlib.sha256(
                    (request["payload"]["delegation_id"] + self.node_id).encode()
                ).hexdigest()[:32],
            )
        receipt_wire = build_admission_receipt(
            request=request,
            target=self.node_id,
            origin=request["source_node_id"],
            message_id=f"rcpt_{request['message_id']}",
            receipt_id=f"receipt_{request['payload']['delegation_id']}",
            target_work_id=work,
            status=status,
            reason_code=reason,
            signing_key=self.signing_key,
            signer_key_b64=self.signer_key_b64,
            key_id=self.key_id,
            issued_at=now,
        )
        receipt = parse_canonical(receipt_wire)
        result, _ = self.ledger.commit(
            request=request,
            request_wire=raw,
            request_carrier=carrier,
            receipt=receipt,
            receipt_wire=receipt_wire,
            state="ACCEPTED" if status == "accepted" else "REJECTED",
            reason=reason,
        )
        return (
            build_carrier(receipt_wire)
            if result == "created"
            else (
                build_carrier(
                    base64.b64decode(
                        self.ledger.get(request["payload"]["delegation_id"])[
                            "receipt_wire_bytes_b64"
                        ]
                    )
                )
                if result == "duplicate"
                else None
            )
        )

    def assign_candidate(
        self,
        delegation_id: str,
        *,
        candidate_source: FederationV1CandidateSnapshotAdapter
        | Callable[[], Iterable[Mapping[str, Any]] | Mapping[str, Any]],
        observed_at: str,
    ) -> dict[str, Any]:
        """Create one target-local ASSIGNED record; never emits a Federation receipt."""
        if not self.enabled:
            raise V1Reject("feature_disabled", "feature_gate")
        return self.ledger.assign_candidate(
            delegation_id,
            target_node_id=self.node_id,
            signing_key=self.signing_key,
            signer_key_b64=self.signer_key_b64,
            key_id=self.key_id,
            candidate_source=candidate_source,
            observed_at=observed_at,
        )
