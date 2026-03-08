"""
MURALI Phase Modules — Extracted from Mayor.
Each phase = pure function taking PhaseContext, returning results.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.brain import BrainProtocol

from city.gateway import CityGateway
from city.network import CityNetwork
from city.pokedex import Pokedex
from city.registry import (
    SVC_AGENT_NADI,
    SVC_AUDIT,
    SVC_BRAIN,
    SVC_BRAIN_MEMORY,
    SVC_CITY_NADI,
    SVC_CAMPAIGNS,
    SVC_CONTRACTS,
    SVC_CONVERSATION_TRACKER,
    SVC_COUNCIL,
    SVC_EVENT_BUS,
    SVC_EXECUTOR,
    SVC_FEDERATION,
    SVC_FEDERATION_NADI,
    SVC_IDENTITY,
    SVC_IMMIGRATION,
    SVC_IMMUNE,
    SVC_ISSUES,
    SVC_KNOWLEDGE_GRAPH,
    SVC_LEARNING,
    SVC_DISCUSSIONS,
    SVC_MOLTBOOK_ASSISTANT,
    SVC_THREAD_STATE,
    SVC_MOLTBOOK_BRIDGE,
    SVC_MOLTBOOK_CLIENT,
    SVC_REFLECTION,
    SVC_SANKALPA,
    CityServiceRegistry,
)

logger = logging.getLogger("AGENT_CITY.PHASES")


@dataclass
class PhaseContext:
    """Shared state for all MURALI phases.

    Core infrastructure (required):
    - pokedex, gateway, network

    Optional services via registry (Layer 3-7):
    - Access via properties: ctx.contracts, ctx.sankalpa, ctx.immune, etc.
    """

    pokedex: Pokedex
    gateway: CityGateway
    network: CityNetwork
    heartbeat_count: int
    offline_mode: bool
    state_path: Path
    active_agents: set[str] = field(default_factory=set)
    gateway_queue: list[dict] = field(default_factory=list)

    # Service registry (replaces 15 optional fields)
    registry: CityServiceRegistry = field(default_factory=CityServiceRegistry)

    # Legacy kwargs (accepted for backward compat, migrated to registry)
    _legacy_services: dict = field(default_factory=dict, repr=False)

    # Internal state (not services)
    last_audit_time: float = 0.0
    recent_events: list = field(default_factory=list)
    all_specs: dict[str, dict] = field(default_factory=dict)
    all_inventories: dict[str, list[dict]] = field(default_factory=dict)
    responded_threads: set[int] = field(default_factory=set)
    responded_threads_agents: set[str] = field(default_factory=set)

    def __init__(
        self,
        pokedex,
        gateway,
        network,
        heartbeat_count,
        offline_mode,
        state_path,
        active_agents=None,
        gateway_queue=None,
        registry=None,
        last_audit_time=0.0,
        recent_events=None,
        all_specs=None,
        all_inventories=None,
        responded_threads=None,
        responded_threads_agents=None,
        **kwargs,
    ):
        self.pokedex = pokedex
        self.gateway = gateway
        self.network = network
        self.heartbeat_count = heartbeat_count
        self.offline_mode = offline_mode
        self.state_path = state_path
        self.active_agents = active_agents if active_agents is not None else set()
        self.gateway_queue = gateway_queue if gateway_queue is not None else []
        self.registry = registry if registry is not None else CityServiceRegistry()
        self._legacy_services = {}
        self.last_audit_time = last_audit_time
        self.recent_events = recent_events if recent_events is not None else []
        self.all_specs = all_specs if all_specs is not None else {}
        self.all_inventories = all_inventories if all_inventories is not None else {}
        self.responded_threads = responded_threads if responded_threads is not None else set()
        self.responded_threads_agents = (
            responded_threads_agents if responded_threads_agents is not None else set()
        )

        # Migrate legacy kwargs into registry
        _LEGACY_NAMES = {
            "contracts": SVC_CONTRACTS,
            "issues": SVC_ISSUES,
            "sankalpa": SVC_SANKALPA,
            "campaigns": SVC_CAMPAIGNS,
            "audit": SVC_AUDIT,
            "reflection": SVC_REFLECTION,
            "executor": SVC_EXECUTOR,
            "council": SVC_COUNCIL,
            "federation": SVC_FEDERATION,
            "moltbook_bridge": SVC_MOLTBOOK_BRIDGE,
            "moltbook_client": SVC_MOLTBOOK_CLIENT,
            "city_nadi": SVC_CITY_NADI,
            "knowledge_graph": SVC_KNOWLEDGE_GRAPH,
            "event_bus": SVC_EVENT_BUS,
            "learning": SVC_LEARNING,
            "agent_nadi": SVC_AGENT_NADI,
            "immune": SVC_IMMUNE,
            "identity": SVC_IDENTITY,
        }
        for kwarg_name, svc_name in _LEGACY_NAMES.items():
            val = kwargs.pop(kwarg_name, None)
            if val is not None and not self.registry.has(svc_name):
                self.registry.register(svc_name, val)

        if kwargs:
            logger.warning("PhaseContext: unknown kwargs ignored: %s", list(kwargs.keys()))

    # ── Service Properties (backward-compatible accessors) ─────────

    @property
    def contracts(self) -> object | None:
        return self.registry.get(SVC_CONTRACTS)

    @property
    def issues(self) -> object | None:
        return self.registry.get(SVC_ISSUES)

    @property
    def sankalpa(self) -> object | None:
        return self.registry.get(SVC_SANKALPA)

    @property
    def campaigns(self) -> object | None:
        return self.registry.get(SVC_CAMPAIGNS)

    @property
    def audit(self) -> object | None:
        return self.registry.get(SVC_AUDIT)

    @property
    def reflection(self) -> object | None:
        return self.registry.get(SVC_REFLECTION)

    @property
    def executor(self) -> object | None:
        return self.registry.get(SVC_EXECUTOR)

    @property
    def council(self) -> object | None:
        return self.registry.get(SVC_COUNCIL)

    @property
    def federation(self) -> object | None:
        return self.registry.get(SVC_FEDERATION)

    @property
    def moltbook_bridge(self) -> object | None:
        return self.registry.get(SVC_MOLTBOOK_BRIDGE)

    @property
    def moltbook_client(self) -> object | None:
        return self.registry.get(SVC_MOLTBOOK_CLIENT)

    @property
    def city_nadi(self) -> object | None:
        return self.registry.get(SVC_CITY_NADI)

    @property
    def knowledge_graph(self) -> object | None:
        return self.registry.get(SVC_KNOWLEDGE_GRAPH)

    @property
    def event_bus(self) -> object | None:
        return self.registry.get(SVC_EVENT_BUS)

    @property
    def learning(self) -> object | None:
        return self.registry.get(SVC_LEARNING)

    @property
    def agent_nadi(self) -> object | None:
        return self.registry.get(SVC_AGENT_NADI)

    @property
    def immune(self) -> object | None:
        return self.registry.get(SVC_IMMUNE)

    @property
    def federation_nadi(self) -> object | None:
        return self.registry.get(SVC_FEDERATION_NADI)

    @property
    def identity(self) -> object | None:
        return self.registry.get(SVC_IDENTITY)

    @property
    def immigration(self) -> object | None:
        return self.registry.get(SVC_IMMIGRATION)

    @property
    def discussions(self) -> object | None:
        return self.registry.get(SVC_DISCUSSIONS)

    @property
    def moltbook_assistant(self) -> object | None:
        return self.registry.get(SVC_MOLTBOOK_ASSISTANT)

    @property
    def brain(self) -> BrainProtocol | None:
        return self.registry.get(SVC_BRAIN)  # type: ignore[return-value]

    @property
    def brain_memory(self) -> object | None:
        return self.registry.get(SVC_BRAIN_MEMORY)

    @property
    def thread_state(self) -> object | None:
        return self.registry.get(SVC_THREAD_STATE)

    @property
    def conversation_tracker(self) -> object | None:
        return self.registry.get(SVC_CONVERSATION_TRACKER)
