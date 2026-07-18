"""Agent City production boundary for Federation Delegation V1 admission.

Additive V1 code only: legacy federation directives and worker execution are not called.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
from pathlib import Path
from typing import Any, Mapping

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


class V1Reject(ValueError):
    def __init__(self, code: str, phase: str):
        super().__init__(code)
        self.code, self.phase = code, phase


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


def _registry(registry: Mapping[str, Any], key: str) -> tuple[str, bytes, Mapping[str, Any]]:
    entry = registry.get(key)
    if not isinstance(entry, Mapping):
        raise V1Reject("key_not_authorized", "registry")
    public = entry.get("public_key")
    if isinstance(public, str):
        public = _decode(public, 32)
    if not isinstance(public, bytes) or len(public) != 32:
        raise V1Reject("key_not_authorized", "registry")
    return str(entry.get("node_id", "")), public, entry


def validate_envelope(
    raw: bytes, *, registry: Mapping[str, Any], expected_target: str, operation: str, now: str
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
    node, authorized, entry = _registry(registry, value["key_id"])
    if node != value["source_node_id"] or authorized != signer:
        raise V1Reject("key_not_authorized", "registry")
    if entry.get("revoked"):
        raise V1Reject("key_revoked", "registry_status")
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


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"delegations": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"delegations": {}}
    return (
        value
        if isinstance(value, dict) and isinstance(value.get("delegations"), dict)
        else {"delegations": {}}
    )


class TargetAdmissionLedger:
    def __init__(self, path: str | Path):
        self.path, self._lock = Path(path), threading.RLock()

    def get(self, delegation_id: str) -> dict[str, Any] | None:
        with self._lock:
            return _load(self.path)["delegations"].get(delegation_id)

    def mark_receipt_sent(self, delegation_id: str) -> None:
        with self._lock:
            doc = _load(self.path)
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
        with self._lock:
            doc, existing = _load(self.path), None
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
            }
            doc["delegations"][did] = record
            _atomic(self.path, doc)
            return "created", record


class OriginDelegationLedger:
    def __init__(self, path: str | Path):
        self.path, self._lock = Path(path), threading.RLock()

    def get(self, delegation_id: str) -> dict[str, Any] | None:
        with self._lock:
            return _load(self.path)["delegations"].get(delegation_id)

    def mark_request_sent(self, delegation_id: str) -> None:
        with self._lock:
            doc = _load(self.path)
            if delegation_id in doc["delegations"]:
                doc["delegations"][delegation_id]["request_send_status"] = "sent"
                doc["delegations"][delegation_id]["send_state"] = "sent"
                _atomic(self.path, doc)

    def create_request(
        self, *, request_wire: bytes, request_carrier: Mapping[str, Any]
    ) -> dict[str, Any]:
        request = parse_canonical(request_wire)
        did = request["payload"]["delegation_id"]
        with self._lock:
            doc = _load(self.path)
            if did in doc["delegations"]:
                return doc["delegations"][did]
            record = {
                "delegation_id": did,
                "origin_task_id": request["payload"]["origin_task_id"],
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
        with self._lock:
            doc, record = _load(self.path), None
            record = doc["delegations"].get(did)
            if record is None:
                raise V1Reject("unknown_delegation", "origin_correlation")
            if receipt["request_message_id"] != record["request_message_id"]:
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
        self.ledger.create_request(request_wire=wire, request_carrier=carrier)
        return wire, carrier

    def retransmit(self, delegation_id: str) -> dict[str, Any]:
        record = _load(self.ledger.path)["delegations"].get(delegation_id)
        if record is None:
            raise V1Reject("unknown_delegation", "origin_ledger")
        return dict(record["request_carrier"])

    def apply_receipt(
        self, *, carrier: Mapping[str, Any], registry: Mapping[str, Any], now: str
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
        registry: Mapping[str, Any],
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
                "work_" + hashlib.sha256(
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
