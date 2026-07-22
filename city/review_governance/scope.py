"""Canonical changed-file scope projection and digest."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Iterable, Mapping

from .canonical import canonical_bytes

SCOPE_DIGEST_PREFIX = "sha256:"
SCOPE_FIELDS = frozenset({"path", "change_type", "previous_path", "base_blob_sha", "head_blob_sha"})
CHANGE_TYPES = frozenset({"added", "modified", "deleted", "renamed", "copied"})
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ScopeError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _path(value: Any, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ScopeError("INVALID_SCOPE")
    if unicodedata.normalize("NFC", value) != value:
        raise ScopeError("INVALID_SCOPE")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ScopeError("INVALID_SCOPE")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ScopeError("INVALID_SCOPE")
    return value


def _sha(value: Any, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ScopeError("INVALID_SCOPE")
    return value


def normalize_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, Mapping) or set(entry) != SCOPE_FIELDS:
        raise ScopeError("INVALID_SCOPE")
    change_type = entry["change_type"]
    if not isinstance(change_type, str) or change_type not in CHANGE_TYPES:
        raise ScopeError("INVALID_SCOPE")
    path = _path(entry["path"])
    previous = _path(entry["previous_path"], allow_none=True)
    base_sha = _sha(entry["base_blob_sha"], allow_none=True)
    head_sha = _sha(entry["head_blob_sha"], allow_none=True)
    if change_type == "added" and (
        previous is not None or base_sha is not None or head_sha is None
    ):
        raise ScopeError("INVALID_SCOPE")
    if change_type == "modified" and (
        previous is not None or base_sha is None or head_sha is None or base_sha == head_sha
    ):
        raise ScopeError("INVALID_SCOPE")
    if change_type == "deleted" and (
        previous is not None or base_sha is None or head_sha is not None
    ):
        raise ScopeError("INVALID_SCOPE")
    if change_type in {"renamed", "copied"} and (
        previous is None or base_sha is None or head_sha is None or previous == path
    ):
        raise ScopeError("INVALID_SCOPE")
    return {
        "path": path,
        "change_type": change_type,
        "previous_path": previous,
        "base_blob_sha": base_sha,
        "head_blob_sha": head_sha,
    }


def canonical_scope(entries: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized = [normalize_entry(entry) for entry in entries]
    if len(normalized) > 2048:
        raise ScopeError("INVALID_SCOPE")
    identities = [(item["previous_path"], item["path"], item["change_type"]) for item in normalized]
    if len(identities) != len(set(identities)):
        raise ScopeError("INVALID_SCOPE")
    final_paths = [item["path"] for item in normalized]
    if len(final_paths) != len(set(final_paths)):
        raise ScopeError("INVALID_SCOPE")
    source_paths = [
        item["previous_path"] for item in normalized if item["change_type"] in {"renamed", "copied"}
    ]
    if len(source_paths) != len(set(source_paths)):
        raise ScopeError("INVALID_SCOPE")
    normalized.sort(key=lambda item: (item["path"], item["previous_path"] or ""))
    return tuple(normalized)


def scope_digest(entries: Iterable[Mapping[str, Any]]) -> str:
    projection = {"schema": "review-scope-b1.1", "entries": list(canonical_scope(entries))}
    return SCOPE_DIGEST_PREFIX + hashlib.sha256(canonical_bytes(projection)).hexdigest()
