"""Append-only JSONL shadow ledger for B1 evidence.

The ledger is opt-in and has no runtime callers.  Writes use an OS lock and
atomic replacement of the complete bounded file; malformed existing content
fails closed and is never truncated or repaired silently.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, parse_canonical

EVENTS = frozenset(
    {
        "review_verdict_received",
        "review_verdict_validated",
        "review_verdict_rejected",
        "review_verdict_stale",
        "merge_readiness_evaluated",
        "merge_readiness_invalidated",
        "council_gate_recorded",
        "merge_completed",
        "external_merge_observed",
    }
)
MAX_LEDGER_BYTES = 8 * 1024 * 1024
LEDGER_SCHEMA = "review-governance-ledger-b1.1"


class LedgerError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _digest_event(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(event)).hexdigest()


class ShadowLedger:
    """Explicitly constructed local ledger; construction performs no writes."""

    def __init__(self, path: str | os.PathLike[str], *, max_bytes: int = MAX_LEDGER_BYTES):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.max_bytes = max_bytes

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_bytes()
        if len(raw) > self.max_bytes:
            raise LedgerError("LEDGER_CORRUPTION")
        if not raw.endswith(b"\n"):
            raise LedgerError("LEDGER_CORRUPTION")
        events: list[dict[str, Any]] = []
        previous = ""
        try:
            for line in raw.splitlines():
                value = parse_canonical(line)
                if not isinstance(value, dict):
                    raise LedgerError("LEDGER_CORRUPTION")
                required = {
                    "schema",
                    "sequence",
                    "event_id",
                    "event_type",
                    "payload",
                    "previous_digest",
                    "event_digest",
                }
                if set(value) != required or value["schema"] != LEDGER_SCHEMA:
                    raise LedgerError("LEDGER_CORRUPTION")
                if value["event_type"] not in EVENTS or value["previous_digest"] != previous:
                    raise LedgerError("LEDGER_CORRUPTION")
                if value["sequence"] != len(events) + 1 or not isinstance(value["payload"], dict):
                    raise LedgerError("LEDGER_CORRUPTION")
                unsigned = {key: value[key] for key in value if key != "event_digest"}
                if value["event_digest"] != _digest_event(unsigned):
                    raise LedgerError("LEDGER_CORRUPTION")
                previous = value["event_digest"]
                events.append(value)
        except LedgerError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError) as exc:
            raise LedgerError("LEDGER_CORRUPTION") from exc
        return events

    def read(self) -> tuple[dict[str, Any], ...]:
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            try:
                return tuple(self._read_unlocked())
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def append(self, event_type: str, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event_type not in EVENTS or not event_id or not isinstance(payload, dict):
            raise LedgerError("INVALID_EVENT")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                events = self._read_unlocked()
                if any(item["event_id"] == event_id for item in events):
                    raise LedgerError("DUPLICATE_EVENT_ID")
                previous = events[-1]["event_digest"] if events else ""
                unsigned = {
                    "schema": LEDGER_SCHEMA,
                    "sequence": len(events) + 1,
                    "event_id": event_id,
                    "event_type": event_type,
                    "payload": payload,
                    "previous_digest": previous,
                }
                event = dict(unsigned, event_digest=_digest_event(unsigned))
                encoded = b"".join(canonical_bytes(item) + b"\n" for item in [*events, event])
                if len(encoded) > self.max_bytes:
                    raise LedgerError("LEDGER_SIZE_LIMIT")
                with tempfile.NamedTemporaryFile("wb", dir=self.path.parent, delete=False) as tmp:
                    tmp.write(encoded)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                    temp_name = tmp.name
                os.replace(temp_name, self.path)
                return event
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
