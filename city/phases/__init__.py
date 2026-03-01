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

from city.contracts import ContractRegistry
from city.council import CityCouncil
from city.executor import IntentExecutor
from city.federation import FederationRelay
from city.gateway import CityGateway
from city.issues import CityIssueManager
from city.network import CityNetwork
from city.pokedex import Pokedex

logger = logging.getLogger("AGENT_CITY.PHASES")


@dataclass
class PhaseContext:
    """Shared state for all MURALI phases.

    Core infrastructure (required):
    - pokedex, gateway, network

    Optional governance wiring (Layer 3-6):
    - contracts, issues, sankalpa, audit, reflection, executor, council, federation
    """

    pokedex: Pokedex
    gateway: CityGateway
    network: CityNetwork
    heartbeat_count: int
    offline_mode: bool
    state_path: Path
    active_agents: set[str] = field(default_factory=set)
    gateway_queue: list[dict] = field(default_factory=list)

    # Layer 3 governance (all optional)
    contracts: ContractRegistry | None = None
    issues: CityIssueManager | None = None
    sankalpa: object = None  # SankalpaOrchestrator (steward-protocol)
    audit: object = None  # AuditKernel (steward-protocol)
    reflection: object = None  # BasicReflection (steward-protocol)

    # Layer 4 action delegation
    executor: IntentExecutor | None = None

    # Layer 5 democratic governance
    council: CityCouncil | None = None

    # Layer 6 federation
    federation: FederationRelay | None = None

    # Layer 6 Moltbook bridge (m/agent-city submolt communication)
    moltbook_bridge: object = None  # MoltbookBridge (city.moltbook_bridge)

    # Layer 7 Moltbook inbox (DM pipeline)
    moltbook_client: object = None  # MoltbookClient (steward-protocol)

    # Nadi messaging (replaces gateway_queue for structured messaging)
    city_nadi: object = None  # CityNadi (city.nadi_hub)

    # Cognition layer (steward-protocol KnowledgeGraph + EventBus)
    knowledge_graph: object = None  # UnifiedKnowledgeGraph
    event_bus: object = None  # EventBus (Narada)

    # Hebbian learning (cross-session memory)
    learning: object = None  # CityLearning (city.learning)

    # Internal
    last_audit_time: float = 0.0
    recent_events: list = field(default_factory=list)
