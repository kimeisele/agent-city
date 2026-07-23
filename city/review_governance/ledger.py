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
import uuid
from pathlib import Path
from typing import Any, Callable

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
        "merge_attempt_reserved",
        "merge_attempt_succeeded",
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
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise LedgerError("INVALID_MAX_BYTES")
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

    def find_event(self, event_id: str) -> dict[str, Any] | None:
        return next((event for event in self.read() if event["event_id"] == event_id), None)

    def find_event_by_payload(
        self, event_type: str, field: str, value: Any
    ) -> dict[str, Any] | None:
        return next(
            (
                event
                for event in self.read()
                if event["event_type"] == event_type and event["payload"].get(field) == value
            ),
            None,
        )

    def readiness_lineage(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evaluation_id: str,
    ) -> tuple[str | None, bool, str | None]:
        """Resolve latest readiness and later invalidation deterministically."""
        events = self.read()
        evaluations: list[dict[str, Any]] = []
        invalidated = False
        ledger_head = events[-1]["event_digest"] if events else None
        for event in events:
            payload = event["payload"]
            if event["event_type"] in {
                "merge_readiness_evaluated",
                "merge_readiness_invalidated",
                "review_verdict_stale",
                "review_verdict_rejected",
                "council_gate_recorded",
            } and (
                "repository" not in payload
                or "pull_request_number" not in payload
                or "reviewed_head_sha" not in payload
            ):
                raise LedgerError("LEDGER_CORRUPTION")
            if (
                payload.get("repository") != repository
                or payload.get("pull_request_number") != pull_request_number
            ):
                continue
            if payload.get("reviewed_head_sha") != reviewed_head_sha:
                continue
            if event["event_type"] == "merge_readiness_evaluated":
                evaluations.append(event)
            elif event["event_type"] in {
                "merge_readiness_invalidated",
                "review_verdict_stale",
                "review_verdict_rejected",
            }:
                if payload.get("evaluation_id") == evaluation_id or not payload.get(
                    "evaluation_id"
                ):
                    invalidated = True
            elif (
                event["event_type"] == "council_gate_recorded"
                and payload.get("state") != "approved"
            ):
                invalidated = True
        latest = evaluations[-1]["payload"].get("evaluation_id") if evaluations else None
        return latest, invalidated, ledger_head

    def latest_readiness_record(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evaluation_id: str,
    ) -> dict[str, Any]:
        """Return the exact latest evaluation payload for an evaluation lineage.

        The lookup is deliberately performed against the validated append-only
        history.  A missing or duplicated evaluation is not a usable identity
        source and therefore fails closed.
        """
        events = self.read()
        matches = [
            event
            for event in events
            if event["event_type"] == "merge_readiness_evaluated"
            and event["payload"].get("evaluation_id") == evaluation_id
            and event["payload"].get("repository") == repository
            and event["payload"].get("pull_request_number") == pull_request_number
            and event["payload"].get("reviewed_head_sha") == reviewed_head_sha
        ]
        if len(matches) != 1:
            raise LedgerError("LEDGER_CORRUPTION" if len(matches) > 1 else "READINESS_NOT_FOUND")
        return dict(matches[0]["payload"])

    def reserve_merge_attempt(
        self,
        *,
        evaluation_id: str,
        payload_factory: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Atomically compare and append one reservation for an evaluation.

        Discovery and the semantic uniqueness check happen under the same
        exclusive lock as the append.  This prevents two workers from each
        observing an empty ledger and reserving the same evaluation.
        """
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise LedgerError("INVALID_EVENT")
        if not callable(payload_factory):
            raise LedgerError("INVALID_EVENT")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                events = self._read_unlocked()
                reservations = [
                    event
                    for event in events
                    if event["event_type"] == "merge_attempt_reserved"
                    and event["payload"].get("evaluation_id") == evaluation_id
                ]
                if len(reservations) > 1:
                    raise LedgerError("MERGE_ATTEMPT_CONFLICT")
                completions = [
                    event
                    for event in events
                    if event["event_type"] == "merge_completed"
                    and event["payload"].get("evaluation_id") == evaluation_id
                ]
                if len(completions) > 1:
                    raise LedgerError("MERGE_ATTEMPT_CONFLICT")
                if reservations or completions:
                    return reservations[0] if reservations else completions[0]
                nonce = uuid.uuid4().hex
                payload = payload_factory(nonce)
                if not isinstance(payload, dict) or payload.get("evaluation_id") != evaluation_id:
                    raise LedgerError("INVALID_EVENT")
                event_id = payload.get("attempt_id")
                if not isinstance(event_id, str) or not event_id:
                    raise LedgerError("INVALID_EVENT")
                if any(item["event_id"] == event_id for item in events):
                    raise LedgerError("DUPLICATE_EVENT_ID")
                previous = events[-1]["event_digest"] if events else ""
                unsigned = {
                    "schema": LEDGER_SCHEMA,
                    "sequence": len(events) + 1,
                    "event_id": event_id,
                    "event_type": "merge_attempt_reserved",
                    "payload": payload,
                    "previous_digest": previous,
                }
                event = dict(unsigned, event_digest=_digest_event(unsigned))
                encoded = b"".join(canonical_bytes(item) + b"\n" for item in [*events, event])
                if len(encoded) > self.max_bytes:
                    raise LedgerError("LEDGER_SIZE_LIMIT")
                temp_name: str | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        "wb", dir=self.path.parent, delete=False
                    ) as tmp:
                        temp_name = tmp.name
                        tmp.write(encoded)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    os.replace(temp_name, self.path)
                    temp_name = None
                    try:
                        directory_fd = os.open(self.path.parent, os.O_RDONLY)
                        try:
                            os.fsync(directory_fd)
                        finally:
                            os.close(directory_fd)
                    except OSError:
                        pass
                finally:
                    if temp_name is not None:
                        try:
                            os.unlink(temp_name)
                        except FileNotFoundError:
                            pass
                return event
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
                temp_name: str | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        "wb", dir=self.path.parent, delete=False
                    ) as tmp:
                        temp_name = tmp.name
                        tmp.write(encoded)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    os.replace(temp_name, self.path)
                    temp_name = None
                    try:
                        directory_fd = os.open(self.path.parent, os.O_RDONLY)
                        try:
                            os.fsync(directory_fd)
                        finally:
                            os.close(directory_fd)
                    except OSError:
                        # Some platforms do not permit directory fsync; the
                        # file fsync and atomic replace still remain in force.
                        pass
                finally:
                    if temp_name is not None:
                        try:
                            os.unlink(temp_name)
                        except FileNotFoundError:
                            pass
                return event
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
