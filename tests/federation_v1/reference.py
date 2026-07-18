"""Independent Agent City SFDJ-1 verifier for federation-v1-golden-01.

This is test-only code and intentionally does not import Steward implementation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import unicodedata
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DOMAIN = b"STEWARD-FEDERATION-DELEGATION-V1\x00"
ROOT_DOMAIN = b"STEWARD-FEDERATION-ROOT-ENROLLMENT-V1\x00"
CERT_DOMAIN = b"STEWARD-FEDERATION-SIGNING-KEY-AUTH-V1\x00"
NODE_RE = re.compile(r"ag_[0-9a-f]{32}\Z")
KEY_RE = re.compile(r"key_[0-9a-f]{64}\Z")


class Reject(ValueError):
    pass


def _quote(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise Reject("rejected_noncanonical")
    value.encode("utf-8")
    # json.dumps handles quote/backslash and non-ASCII; expand short control escapes
    # because SFDJ-1 uses lowercase \u00xx for every control code point.
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return text.replace("\\b", "\\u0008").replace("\\t", "\\u0009").replace(
        "\\n", "\\u000a"
    ).replace("\\f", "\\u000c").replace("\\r", "\\u000d")


def _emit(value: Any, depth: int = 0) -> str:
    if depth > 16:
        raise Reject("max_depth")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if not -(2**63) <= value <= 2**63 - 1:
            raise Reject("integer_range")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Reject("float_forbidden")
        raise Reject("float_forbidden")
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, list):
        if len(value) > 1024:
            raise Reject("array_limit")
        return "[" + ",".join(_emit(item, depth + 1) for item in value) + "]"
    if isinstance(value, dict):
        if len(value) > 1024:
            raise Reject("object_limit")
        keys = list(value)
        if any(not isinstance(key, str) for key in keys):
            raise Reject("object_key_type")
        if any(unicodedata.normalize("NFC", key) != key for key in keys):
            raise Reject("rejected_noncanonical")
        keys.sort(key=lambda key: key.encode("utf-8"))
        return "{" + ",".join(
            _quote(key) + ":" + _emit(value[key], depth + 1) for key in keys
        ) + "}"
    raise Reject("unsupported_type")


def canonical(value: Any) -> bytes:
    raw = _emit(value).encode("utf-8")
    if len(raw) > 256 * 1024:
        raise Reject("envelope_limit")
    return raw


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise Reject("duplicate_json_key")
        obj[key] = value
    return obj


def load_canonical(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Reject("bom_forbidden")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except Reject:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Reject("invalid_json") from exc
    if canonical(value) != raw:
        raise Reject("rejected_noncanonical")
    if not isinstance(value, dict):
        raise Reject("envelope_object_required")
    return value


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def node_id(public_key: bytes) -> str:
    return "ag_" + sha256_hex(public_key.hex().encode("ascii"))[:32]


def key_id(public_key: bytes) -> str:
    return "key_" + sha256_hex(public_key)


def verify(public_key: bytes, domain: bytes, digest: str, signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        if len(signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, domain + bytes.fromhex(digest)
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def envelope_digest(envelope: dict[str, Any]) -> str:
    return sha256_hex(canonical({
        key: value for key, value in envelope.items()
        if key not in {"message_hash", "signature"}
    }))


def semantic_request_digest(payload: dict[str, Any], source: str, target: str) -> str:
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
    semantic = {
        "contract_version": "federation-delegation-v1",
        "operation": "delegate_task",
        "source_node_id": source,
        "target_node_id": target,
        "payload": {field: payload[field] for field in fields},
    }
    return sha256_hex(canonical(semantic))
