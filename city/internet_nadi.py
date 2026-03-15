"""
INTERNET NADI — Agent-Internet ↔ Agent-City Message Bridge.

File-based Nadi channel for agent-internet to push external content
(web research, API responses, scraped data) into the city membrane.

Reuses FederationMessage wire format for consistency.
Transport: git + CI workflow (same as federation_nadi).

Outbox: data/internet/nadi_outbox.json — city → agent-internet (requests)
Inbox:  data/internet/nadi_inbox.json  — agent-internet → city (results)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from city.federation_nadi import (
    NADI_BUFFER_SIZE,
    NADI_FEDERATION_TTL_S,
    RAJAS,
    SATTVA,
    FederationMessage,
)

logger = logging.getLogger("AGENT_CITY.INTERNET_NADI")


@dataclass
class InternetNadi:
    """File-based Nadi bridge for agent-internet communication.

    GENESIS reads inbox (agent-internet → city: research results, web data).
    MOKSHA writes outbox (city → agent-internet: research requests, queries).

    Messages are routed through IngressSurface.AGENT_INTERNET membrane.
    """

    _internet_dir: Path = field(default=Path("data/internet"))
    _default_target: str = field(default="agent-internet")
    _outbox: list[FederationMessage] = field(default_factory=list)
    _processed_ids: dict[str, None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._internet_dir.mkdir(parents=True, exist_ok=True)

    @property
    def outbox_path(self) -> Path:
        return self._internet_dir / "nadi_outbox.json"

    @property
    def inbox_path(self) -> Path:
        return self._internet_dir / "nadi_inbox.json"

    # ── Write (MOKSHA → agent-internet) ──────────────────────────

    def request(
        self,
        operation: str,
        payload: dict,
        *,
        source: str = "moksha",
        priority: int = RAJAS,
        correlation_id: str = "",
    ) -> bool:
        """Queue a request for agent-internet (written on flush).

        Operations:
        - "web_research": Request web research on a topic
        - "api_check":    Request API health/response check
        - "scrape":       Request structured data extraction
        - "health_probe": Request endpoint health probing
        """
        msg = FederationMessage(
            source=source,
            target=self._default_target,
            operation=operation,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
        )
        self._outbox.append(msg)
        return True

    def flush(self) -> int:
        """Write pending outbox messages to disk. Returns count written."""
        if not self._outbox:
            return 0

        existing = self._read_file(self.outbox_path)
        all_msgs = existing + [m.to_dict() for m in self._outbox]

        now = time.time()
        live = [
            m for m in all_msgs
            if now <= m.get("timestamp", 0) + m.get("ttl_s", NADI_FEDERATION_TTL_S)
        ]
        live.sort(key=lambda m: (-m.get("priority", 1), m.get("timestamp", 0)))
        capped = live[:NADI_BUFFER_SIZE]

        self._write_file(self.outbox_path, capped)
        count = len(self._outbox)
        self._outbox.clear()
        logger.info("InternetNadi: flushed %d requests to outbox (%d total)", count, len(capped))
        return count

    # ── Read (agent-internet → city) ─────────────────────────────

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
            msg_id = f"{msg.source}:{msg.timestamp}"
            if msg_id in self._processed_ids:
                continue
            self._processed_ids[msg_id] = None
            messages.append(msg)

        messages.sort(key=lambda m: -m.priority)

        # FIFO eviction
        _MAX_PROCESSED = 5000
        while len(self._processed_ids) > _MAX_PROCESSED:
            oldest_key = next(iter(self._processed_ids))
            del self._processed_ids[oldest_key]

        if messages:
            logger.info("InternetNadi: received %d messages from agent-internet", len(messages))
        return messages

    # ── Steward Observation ──────────────────────────────────────

    def emit_health_snapshot(
        self,
        snapshot: dict,
        *,
        source: str = "moksha",
    ) -> bool:
        """Emit city health snapshot for steward observation.

        The steward agent reads these to detect anomalies (brain dead,
        suspicious patterns, API failures) and can send optimization
        directives back through federation_nadi.
        """
        return self.request(
            "health_snapshot",
            snapshot,
            source=source,
            priority=SATTVA,
        )

    # ── Stats ────────────────────────────────────────────────────

    def stats(self) -> dict:
        outbox_count = len(self._read_file(self.outbox_path))
        inbox_count = len(self._read_file(self.inbox_path))
        return {
            "outbox_pending": len(self._outbox),
            "outbox_on_disk": outbox_count,
            "inbox_on_disk": inbox_count,
            "processed": len(self._processed_ids),
        }

    # ── File I/O ─────────────────────────────────────────────────

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
