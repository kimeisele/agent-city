"""
NADI HUB — Structured Messaging for Agent City.

Replaces the ad-hoc gateway_queue: list[dict] with proper Nadi channels.
Each queue item becomes a NadiMessage with typed operations, priority,
TTL, and correlation IDs.

Uses LocalNadi (PRANA type) from steward-protocol. Graceful NullNadi
fallback if unavailable.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("AGENT_CITY.NADI")

# Guna mode → Nadi priority mapping
_MODE_TO_PRIORITY = {
    "SATTVA": 2,  # NadiPriority.SATTVA
    "RAJAS": 1,  # NadiPriority.RAJAS
    "TAMAS": 0,  # NadiPriority.TAMAS
}


def _create_nadi(endpoint_id: str):
    """Create a LocalNadi or NullNadi fallback."""
    try:
        from vibe_core.mahamantra.substrate.state.nadi import (
            LocalNadi,
            NadiType,
        )

        return LocalNadi(endpoint_id, NadiType.PRANA)
    except Exception as e:
        logger.debug("LocalNadi unavailable, using NullNadi: %s", e)
        try:
            from vibe_core.mahamantra.substrate.state.nadi import NullNadi

            return NullNadi(endpoint_id)
        except Exception:
            return None


@dataclass
class CityNadi:
    """Structured message queue for agent-city gateway.

    Wraps LocalNadi with city-specific enqueue/drain semantics.
    Priority-sorted drain: SUDDHA > SATTVA > RAJAS > TAMAS.
    TTL-filtered: expired messages skipped automatically.
    """

    _nadi: object = field(default=None)
    _endpoint_id: str = "city_gateway"

    def __post_init__(self) -> None:
        if self._nadi is None:
            self._nadi = _create_nadi(self._endpoint_id)

    @property
    def available(self) -> bool:
        """True if a real Nadi is available (not None/NullNadi)."""
        if self._nadi is None:
            return False
        return hasattr(self._nadi, "_inbox")

    def enqueue(
        self,
        source: str,
        text: str,
        *,
        priority: int | None = None,
        conversation_id: str = "",
        from_agent: str = "",
        post_id: str = "",
        code_signals: list | None = None,
        discussion_number: int = 0,
        discussion_title: str = "",
        direct_agent: str = "",
        agent_name: str = "",
        extra_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Enqueue a message for KARMA processing.

        Args:
            source: Origin identifier (dm, feed, submolt, gateway, discussion).
            text: Message content.
            priority: NadiPriority value (0-3). Auto-derived from guna if None.
            conversation_id: Moltbook DM conversation ID for response routing.
            from_agent: Sender's username.
            post_id: Moltbook post ID (for submolt signals).
            code_signals: Detected code signals from submolt scanning.
            discussion_number: GitHub Discussion number (for discussion routing).
            discussion_title: Discussion thread title.
            direct_agent: @mentioned agent name for direct routing.
            extra_payload: Arbitrary passthrough metadata preserved on drain.

        Returns True if enqueued, False if Nadi unavailable.
        """
        if self._nadi is None:
            return False

        try:
            from vibe_core.mahamantra.substrate.state.nadi import (
                NadiMessage,
                NadiOp,
                NadiPriority,
                NadiType,
            )

            # Map source to priority if not explicitly set
            if priority is None:
                if source == "dm":
                    priority = NadiPriority.SUDDHA  # DMs are critical (user requests)
                elif source == "submolt" and code_signals:
                    priority = NadiPriority.SATTVA  # Code signals are important
                else:
                    priority = NadiPriority.RAJAS  # Default: normal

            payload: dict[str, object] = {
                "text": text,
                "source": source,
            }
            if conversation_id:
                payload["conversation_id"] = conversation_id
            if from_agent:
                payload["from_agent"] = from_agent
            if post_id:
                payload["post_id"] = post_id
            if code_signals:
                payload["code_signals"] = code_signals
            if discussion_number:
                payload["discussion_number"] = discussion_number
            if discussion_title:
                payload["discussion_title"] = discussion_title
            if direct_agent:
                payload["direct_agent"] = direct_agent
            if agent_name:
                payload["agent_name"] = agent_name
            if extra_payload:
                for key, value in extra_payload.items():
                    if key not in payload:
                        payload[key] = value

            msg = NadiMessage(
                source=source,
                target=self._endpoint_id,
                nadi_type=NadiType.PRANA,
                operation=NadiOp.PROCESS,
                payload=payload,
                priority=NadiPriority(priority),
                correlation_id=conversation_id or None,
            )

            # Direct inbox delivery (local queue pattern)
            self._nadi._deliver(msg)
            return True

        except Exception as e:
            logger.warning("Nadi enqueue failed: %s", e)
            return False

    def drain(self) -> list[dict]:
        """Drain all pending messages, sorted by priority (highest first).

        Returns list of dicts compatible with the old gateway_queue format:
        [{source, text, conversation_id, from_agent, ...}]

        Expired messages (TTL exceeded) are automatically filtered.
        """
        if self._nadi is None:
            return []

        try:
            messages = self._nadi.receive_all()

            # Filter expired messages
            messages = [m for m in messages if not m.is_expired]

            # Sort by priority (highest first: SUDDHA=3 > SATTVA=2 > RAJAS=1 > TAMAS=0)
            messages.sort(key=lambda m: m.priority, reverse=True)

            # Convert to dict format (backward compatible with old gateway_queue)
            result = []
            for msg in messages:
                item = dict(msg.payload)
                item.setdefault("source", msg.source)
                item.setdefault("text", "")
                item.setdefault("conversation_id", "")
                item.setdefault("from_agent", "")
                result.append(item)
            return result

        except Exception as e:
            logger.warning("Nadi drain failed: %s", e)
            return []

    def pending_count(self) -> int:
        """Number of messages waiting to be processed."""
        if self._nadi is None:
            return 0
        try:
            stats = self._nadi.get_stats()
            return stats.messages_pending
        except Exception:
            return 0

    def stats(self) -> dict:
        """Nadi statistics for reflection."""
        if self._nadi is None:
            return {}
        try:
            s = self._nadi.get_stats()
            return {
                "endpoint": s.endpoint_id,
                "connections": s.connections,
                "sent": s.messages_sent,
                "received": s.messages_received,
                "pending": s.messages_pending,
            }
        except Exception:
            return {}
