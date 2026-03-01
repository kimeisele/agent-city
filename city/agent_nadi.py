"""
AgentNadiManager — Per-Agent Messaging (Lightweight).

Uses Nadi concepts (NadiPriority, NadiOp, TTL) but NOT one LocalNadi
per agent. LocalNadi inherits GADBase (MantraHeartbeat, acharya.verify_link)
which is too heavy to instantiate per-agent — causes accumulation hangs.

Instead: single dict of deques as per-agent inboxes. Same API, same priority
sorting, same TTL filtering. Zero GADBase overhead.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.AGENT_NADI")

# Nadi constants (match steward-protocol nadi.py)
_BUFFER_SIZE = 144  # NADI_BUFFER_SIZE
_TTL_S = 24.0  # NADI_TIMEOUT_MS / 1000

# Priority levels (match NadiPriority)
TAMAS = 0
RAJAS = 1
SATTVA = 2
SUDDHA = 3


@dataclass
class _AgentMessage:
    """Lightweight message struct (no GADBase, no NadiMessage overhead)."""
    source: str
    target: str
    text: str
    from_agent: str
    priority: int = RAJAS
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    ttl_s: float = _TTL_S

    @property
    def is_expired(self) -> bool:
        if self.ttl_s <= 0:
            return False
        return time.time() > self.timestamp + self.ttl_s


@dataclass
class AgentNadiManager:
    """Manages per-agent inboxes for inter-agent messaging.

    Lightweight: uses deques, not LocalNadi instances.
    Same Nadi semantics (priority, TTL, operations).
    """

    _inboxes: dict[str, deque] = field(default_factory=dict)
    _stats_sent: int = 0
    _stats_received: int = 0

    @property
    def available(self) -> bool:
        return True

    def register(self, name: str) -> bool:
        """Create an inbox for an agent.

        Returns True if created, False if already exists.
        """
        if name in self._inboxes:
            return False
        self._inboxes[name] = deque(maxlen=_BUFFER_SIZE)
        logger.debug("Agent inbox created: %s", name)
        return True

    def unregister(self, name: str) -> bool:
        """Remove an agent's inbox."""
        if name not in self._inboxes:
            return False
        del self._inboxes[name]
        return True

    def send(
        self,
        from_name: str,
        to_name: str,
        text: str,
        *,
        priority: int | None = None,
        correlation_id: str = "",
    ) -> bool:
        """Send a message from one agent to another.

        Returns True if delivered, False if either agent missing.
        """
        if from_name not in self._inboxes or to_name not in self._inboxes:
            return False

        msg = _AgentMessage(
            source=from_name,
            target=to_name,
            text=text,
            from_agent=from_name,
            priority=priority if priority is not None else RAJAS,
            correlation_id=correlation_id,
        )
        self._inboxes[to_name].append(msg)
        self._stats_sent += 1
        self._stats_received += 1
        return True

    def broadcast(self, from_name: str, text: str) -> int:
        """Broadcast a message from one agent to all others.

        Returns number of recipients reached.
        """
        if from_name not in self._inboxes:
            return 0

        count = 0
        for name, inbox in self._inboxes.items():
            if name == from_name:
                continue
            msg = _AgentMessage(
                source=from_name,
                target=name,
                text=text,
                from_agent=from_name,
            )
            inbox.append(msg)
            count += 1

        self._stats_sent += count
        self._stats_received += count
        return count

    def drain(self, name: str) -> list[dict]:
        """Drain all pending messages for an agent.

        Returns list of dicts sorted by priority (highest first).
        TTL-filtered (expired messages dropped).
        """
        if name not in self._inboxes:
            return []

        inbox = self._inboxes[name]
        items = []
        while inbox:
            msg = inbox.popleft()
            if msg.is_expired:
                continue
            items.append({
                "source": msg.source,
                "text": msg.text,
                "from_agent": msg.from_agent,
                "priority": msg.priority,
                "correlation_id": msg.correlation_id,
            })

        # Sort by priority descending
        items.sort(key=lambda x: x["priority"], reverse=True)
        return items

    def agent_count(self) -> int:
        """Number of registered agent inboxes."""
        return len(self._inboxes)

    def stats(self) -> dict:
        """Aggregate messaging stats."""
        total_pending = sum(len(q) for q in self._inboxes.values())
        return {
            "agents": len(self._inboxes),
            "total_sent": self._stats_sent,
            "total_received": self._stats_received,
            "total_pending": total_pending,
        }
