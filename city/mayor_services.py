from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from city.registry import (
    SVC_AGENT_NADI,
    SVC_AUDIT,
    SVC_CITY_NADI,
    SVC_CONTRACTS,
    SVC_COUNCIL,
    SVC_EVENT_BUS,
    SVC_EXECUTOR,
    SVC_FEDERATION,
    SVC_IMMUNE,
    SVC_ISSUES,
    SVC_KNOWLEDGE_GRAPH,
    SVC_LEARNING,
    SVC_MOLTBOOK_BRIDGE,
    SVC_MOLTBOOK_CLIENT,
    SVC_PRAHLAD,
    SVC_REFLECTION,
    SVC_SANKALPA,
)

if TYPE_CHECKING:
    from city.mayor import Mayor


LEGACY_SERVICE_FIELDS: dict[str, str] = {
    "_contracts": SVC_CONTRACTS,
    "_issues": SVC_ISSUES,
    "_sankalpa": SVC_SANKALPA,
    "_audit": SVC_AUDIT,
    "_reflection": SVC_REFLECTION,
    "_executor": SVC_EXECUTOR,
    "_council": SVC_COUNCIL,
    "_federation": SVC_FEDERATION,
    "_moltbook_bridge": SVC_MOLTBOOK_BRIDGE,
    "_moltbook_client": SVC_MOLTBOOK_CLIENT,
    "_city_nadi": SVC_CITY_NADI,
    "_knowledge_graph": SVC_KNOWLEDGE_GRAPH,
    "_event_bus": SVC_EVENT_BUS,
    "_learning": SVC_LEARNING,
    "_agent_nadi": SVC_AGENT_NADI,
    "_immune": SVC_IMMUNE,
    "_prahlad": SVC_PRAHLAD,
}


@dataclass(frozen=True)
class MayorServiceBridge:
    """Owns Mayor legacy-field to registry compatibility choreography."""

    def sync_legacy_services(self, mayor: Mayor) -> None:
        for field_name, service_name in LEGACY_SERVICE_FIELDS.items():
            value = getattr(mayor, field_name, None)
            if value is not None and not mayor._registry.has(service_name):
                mayor._registry.register(service_name, value)