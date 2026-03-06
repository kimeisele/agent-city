from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from city.registry import SVC_REFLECTION
from config import get_config

if TYPE_CHECKING:
    from city.mayor import Mayor

logger = logging.getLogger("AGENT_CITY.MAYOR.OBSERVATION")


@dataclass(frozen=True)
class MayorObservationBridge:
    """Owns Mayor reflection recording and city-event observation semantics."""

    def record_execution(self, mayor: Mayor, department: str, duration_ms: float) -> None:
        """Record a heartbeat execution via Reflection protocol."""
        reflection = mayor._registry.get(SVC_REFLECTION)
        if reflection is None:
            return

        from vibe_core.protocols.reflection import ExecutionRecord

        record = ExecutionRecord(
            command=f"mayor.heartbeat.{department}",
            success=True,
            duration_ms=duration_ms,
        )
        reflection.record_execution(record)

    def wire_event_handlers(self, mayor: Mayor) -> None:
        """Subscribe Mayor to AnantaShesha city events."""
        try:
            from vibe_core.ouroboros.ananta_shesha import get_system_anchor

            anchor = get_system_anchor()
            for event_type in (
                "AGENT_REGISTERED",
                "AGENT_UNREGISTERED",
                "AGENT_MESSAGE",
                "AGENT_BROADCAST",
            ):
                anchor.add_handler(event_type, mayor._on_city_event)
        except Exception as exc:
            logger.warning("Event handler wiring failed: %s", exc)

    def on_city_event(self, mayor: Mayor, event: object) -> None:
        """Buffer a city event for later reflection/MOKSHA reporting."""
        mayor._recent_events.append(
            {
                "type": event.event_type,
                "data": event.data,
                "timestamp": event.timestamp.isoformat()
                if hasattr(event.timestamp, "isoformat")
                else str(event.timestamp),
            }
        )
        self._trim_recent_events(mayor)

    def _trim_recent_events(self, mayor: Mayor) -> None:
        cfg = get_config().get("mayor", {})
        max_events = cfg.get("event_buffer_max", 200)
        trim_to = cfg.get("event_buffer_trim", 100)
        if len(mayor._recent_events) > max_events:
            mayor._recent_events = mayor._recent_events[-trim_to:]