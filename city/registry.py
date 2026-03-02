"""
CityServiceRegistry — Lightweight DI for Mayor Services.

String-keyed service registry. Replaces 18 optional kwargs on Mayor
and 15 optional fields on PhaseContext.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

logger = logging.getLogger("AGENT_CITY.REGISTRY")

# Service name constants (prevent typo bugs)
SVC_CONTRACTS = "contracts"
SVC_EXECUTOR = "executor"
SVC_ISSUES = "issues"
SVC_COUNCIL = "council"
SVC_SANKALPA = "sankalpa"
SVC_AUDIT = "audit"
SVC_REFLECTION = "reflection"
SVC_FEDERATION = "federation"
SVC_MOLTBOOK_BRIDGE = "moltbook_bridge"
SVC_MOLTBOOK_CLIENT = "moltbook_client"
SVC_CITY_NADI = "city_nadi"
SVC_KNOWLEDGE_GRAPH = "knowledge_graph"
SVC_EVENT_BUS = "event_bus"
SVC_LEARNING = "learning"
SVC_AGENT_NADI = "agent_nadi"
SVC_IMMUNE = "immune"
SVC_FEDERATION_NADI = "federation_nadi"
SVC_IDENTITY = "identity"
SVC_PRAHLAD = "prahlad"
SVC_DAEMON = "daemon"
SVC_PR_LIFECYCLE = "pr_lifecycle"
SVC_CARTRIDGE_LOADER = "cartridge_loader"
SVC_CARTRIDGE_FACTORY = "cartridge_factory"
SVC_CITY_BUILDER = "city_builder"
SVC_CLAIMS = "claims"
SVC_SPAWNER = "spawner"
SVC_ATTENTION = "attention"
SVC_REACTOR = "reactor"
SVC_IMMIGRATION = "immigration"
SVC_MOLTBOOK_ASSISTANT = "moltbook_assistant"
SVC_PATHOGEN_INDEX = "pathogen_index"
SVC_DISCUSSIONS = "discussions"
SVC_DIAGNOSTICS = "diagnostics"
SVC_BRAIN = "brain"
SVC_BRAIN_MEMORY = "brain_memory"


class CityServiceRegistry:
    """String-keyed service registry.

    Services are registered by name and retrieved by name.
    No type-erased object fields. No kwargs explosion.
    """

    __slots__ = ("_services",)

    def __init__(self) -> None:
        self._services: dict[str, object] = {}

    def register(self, name: str, instance: object) -> None:
        """Register a service. Overwrites if already registered."""
        self._services[name] = instance
        logger.debug("Registered service: %s", name)

    def register_all(self, services: dict[str, object]) -> None:
        """Register multiple services at once."""
        for name, instance in services.items():
            self.register(name, instance)

    def get(self, name: str) -> object | None:
        """Get a service by name. Returns None if not registered."""
        return self._services.get(name)

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._services

    def names(self) -> list[str]:
        """List all registered service names."""
        return list(self._services.keys())

    def stats(self) -> dict:
        """Return registry stats for reflection output."""
        return {
            "registered": len(self._services),
            "services": self.names(),
        }
