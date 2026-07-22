"""B1 canonicalization boundary.

SFDJ-1 is reused through the already tested pure Federation helper.  Parsing
is performed here first so duplicate JSON keys are rejected before the helper
ever receives an object.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from city.federation_v1 import canonical_bytes as _sfdj_canonical_bytes

B1_DOMAIN = b"REVIEW-VERDICT-B1.1\x00"


class CanonicalError(ValueError):
    """Raised when input cannot be represented by the B1 canonical profile."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalError("DUPLICATE_KEY")
        result[key] = value
    return result


def parse_json(raw: bytes | str) -> Any:
    """Parse JSON with duplicate-key and non-finite-number rejection."""

    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes):
        raise CanonicalError("INVALID_TYPE")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate,
            parse_constant=lambda _: (_ for _ in ()).throw(CanonicalError("INVALID_NUMBER")),
        )
    except CanonicalError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalError("INVALID_JSON") from exc


def canonical_bytes(value: Any) -> bytes:
    """Return the exact SFDJ-1 bytes through the neutral adapter boundary."""

    try:
        return _sfdj_canonical_bytes(value)
    except Exception as exc:  # translate the implementation's private error type
        raise CanonicalError("NON_CANONICAL") from exc


def parse_canonical(raw: bytes | str) -> Any:
    value = parse_json(raw)
    encoded = canonical_bytes(value)
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
    if encoded != raw_bytes:
        raise CanonicalError("NON_CANONICAL")
    return value


def sha256_prefixed(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def verdict_signature_input(unsigned: dict[str, Any]) -> bytes:
    return B1_DOMAIN + hashlib.sha256(canonical_bytes(unsigned)).digest()
