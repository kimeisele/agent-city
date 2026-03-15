"""
FEDERATION NADI — Inter-Repo Message Bridge.

File-based Nadi channel for steward-protocol ↔ agent-city communication.
Uses existing federation transport (git commit + CI workflow).

Outbox: data/federation/nadi_outbox.json — agent-city writes, steward-protocol reads
Inbox:  data/federation/nadi_inbox.json  — steward-protocol writes, agent-city reads

Message format: NadiMessage-compatible JSON with priority, TTL, operations.
Preserves Nadi semantics: 144 buffer, 24s TTL, 4 priority levels.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.FEDERATION_NADI")

# Nadi constants (derived from seed.py via steward-protocol)
NADI_BUFFER_SIZE = 144
NADI_TTL_S = 24.0
NADI_FEDERATION_TTL_S = 3600.0  # 1 hour — must survive ≥4 heartbeat cycles (4×15min)

# Priority levels (Guna-based, matching NadiPriority)
TAMAS = 0
RAJAS = 1
SATTVA = 2
SUDDHA = 3


@dataclass
class FederationMessage:
    """Cross-repo Nadi message. JSON-serializable."""

    source: str  # Sender endpoint (e.g., "karma", "moksha", "genesis")
    target: str  # Receiver endpoint (e.g., "steward-protocol", "agent-city")
    operation: str  # NadiOp value (e.g., "process", "send", "commit")
    payload: dict  # Message data
    priority: int = RAJAS
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    ttl_s: float = NADI_FEDERATION_TTL_S

    @property
    def is_expired(self) -> bool:
        return time.time() > self.timestamp + self.ttl_s

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "operation": self.operation,
            "payload": self.payload,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "ttl_s": self.ttl_s,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FederationMessage:
        return cls(
            source=data.get("source", "unknown"),
            target=data.get("target", ""),
            operation=data.get("operation", "process"),
            payload=data.get("payload", {}),
            priority=data.get("priority", RAJAS),
            correlation_id=data.get("correlation_id", ""),
            timestamp=data.get("timestamp", time.time()),
            ttl_s=data.get("ttl_s", NADI_FEDERATION_TTL_S),
        )


@dataclass
class FederationNadi:
    """File-based Nadi bridge for inter-repo communication.

    MOKSHA writes to outbox. GENESIS reads from inbox.
    Federation transport (CI workflow git commit) handles delivery.
    """

    _federation_dir: Path = field(default=Path("data/federation"))
    _default_target: str = field(default="steward-protocol")
    _outbox: list[FederationMessage] = field(default_factory=list)
    _processed_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._federation_dir.mkdir(parents=True, exist_ok=True)

    @property
    def outbox_path(self) -> Path:
        return self._federation_dir / "nadi_outbox.json"

    @property
    def inbox_path(self) -> Path:
        return self._federation_dir / "nadi_inbox.json"

    # ── Write (MOKSHA) ──────────────────────────────────────────────

    def emit(
        self,
        source: str,
        operation: str,
        payload: dict,
        *,
        target: str = "",
        priority: int = RAJAS,
        correlation_id: str = "",
    ) -> bool:
        """Queue a message for the outbox (written on flush)."""
        msg = FederationMessage(
            source=source,
            target=target or self._default_target,
            operation=operation,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
        )
        self._outbox.append(msg)
        return True

    def flush(self) -> int:
        """Write pending outbox messages to disk. Returns count written.

        Merges with existing outbox, caps at NADI_BUFFER_SIZE, filters expired.
        """
        if not self._outbox:
            return 0

        existing = self._read_file(self.outbox_path)
        all_msgs = existing + [m.to_dict() for m in self._outbox]

        # Filter expired and cap buffer
        now = time.time()
        live = [
            m
            for m in all_msgs
            if now <= m.get("timestamp", 0) + m.get("ttl_s", NADI_FEDERATION_TTL_S)
        ]
        # Sort by priority descending, then timestamp ascending
        live.sort(key=lambda m: (-m.get("priority", 1), m.get("timestamp", 0)))
        capped = live[:NADI_BUFFER_SIZE]

        self._write_file(self.outbox_path, capped)
        count = len(self._outbox)
        self._outbox.clear()
        logger.info("FederationNadi: flushed %d messages to outbox (%d total)", count, len(capped))
        return count

    # ── Read (GENESIS) ──────────────────────────────────────────────

    def receive(self) -> list[FederationMessage]:
        """Read new messages from inbox. Deduplicates by timestamp+source.

        Returns list of FederationMessage, priority-sorted (highest first).
        """
        raw = self._read_file(self.inbox_path)

        messages: list[FederationMessage] = []
        for data in raw:
            msg = FederationMessage.from_dict(data)
            if msg.is_expired:
                continue
            # Dedup by source+timestamp
            msg_id = f"{msg.source}:{msg.timestamp}"
            if msg_id in self._processed_ids:
                continue
            self._processed_ids.add(msg_id)
            messages.append(msg)

        # Sort by priority (highest first)
        messages.sort(key=lambda m: -m.priority)

        # Cap processed_ids to prevent unbounded growth
        if len(self._processed_ids) > 5000:
            excess = len(self._processed_ids) - 2500
            for _ in range(excess):
                self._processed_ids.pop()

        if messages:
            logger.info("FederationNadi: received %d new messages from inbox", len(messages))
        return messages

    def clear_inbox(self) -> None:
        """Clear processed messages from inbox file (cleanup)."""
        if self.inbox_path.exists():
            raw = self._read_file(self.inbox_path)
            now = time.time()
            live = [
                m
                for m in raw
                if now <= m.get("timestamp", 0) + m.get("ttl_s", NADI_FEDERATION_TTL_S)
            ]
            self._write_file(self.inbox_path, live)

    # ── Stats ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        outbox_count = len(self._read_file(self.outbox_path))
        inbox_count = len(self._read_file(self.inbox_path))
        return {
            "outbox_pending": len(self._outbox),
            "outbox_on_disk": outbox_count,
            "inbox_on_disk": inbox_count,
            "processed": len(self._processed_ids),
        }

    # ── File I/O ────────────────────────────────────────────────────

    def _read_file(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_file(self, path: Path, messages: list[dict]) -> None:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(messages, indent=2, default=str))
        temp.replace(path)
