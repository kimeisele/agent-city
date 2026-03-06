"""
MAYOR AGENT — The Autonomous City Operator
=============================================

Thin dispatcher. Delegates to city/phases/{genesis,dharma,karma,moksha}.py.
Owns: heartbeat loop, event handling, external interface.

MURALI Departments:
  0 GENESIS: Census (discover agents from Moltbook feed)
  1 DHARMA:  Governance (cell homeostasis, zone health, contracts, sankalpa missions)
  2 KARMA:   Operations (process gateway queue, sankalpa intents)
  3 MOKSHA:  Reflection (audit, reflection analysis, stats, chain verification)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from city.gateway import CityGateway
from city.membrane import IngressSurface, enqueue_ingress
from city.network import CityNetwork
from city.phases import PhaseContext
from city.pokedex import Pokedex
from city.registry import CityServiceRegistry

from .boot import MayorBootBridge
from .context import MayorContextBridge
from .execution import (
    HeartbeatResult,
    MayorExecutionBridge,
)
from .lifecycle import MayorLifecycleBridge
from .observation import MayorObservationBridge
from .services import MayorServiceBridge

logger = logging.getLogger("AGENT_CITY.MAYOR")


class MayorState(TypedDict):
    """Persistent state for the Mayor agent."""

    heartbeat_count: int
    last_heartbeat: float
    discovered_agents: list[str]
    archived_agents: list[str]
    total_governance_actions: int
    total_operations: int


@dataclass
class Mayor:
    """The autonomous city operator.

    Runs MURALI 4-phase cycles. Each heartbeat advances one department.
    4 heartbeats = 1 full MURALI rotation.

    Layer 3 governance (all optional, backward-compatible):
    - _contracts: Quality contract registry (DHARMA phase)
    - _issues: Issue manager with smart lifecycle (DHARMA phase)
    - _sankalpa: Mission orchestrator (KARMA phase)
    - _audit: Audit kernel (MOKSHA phase)
    - _reflection: Execution analysis (MOKSHA phase, every heartbeat)
    """

    _pokedex: Pokedex
    _gateway: CityGateway
    _network: CityNetwork
    _state_path: Path = field(default=Path("data/mayor_state.json"))
    _boot: MayorBootBridge | None = None
    _context: MayorContextBridge | None = None
    _service_bridge: MayorServiceBridge | None = None
    _execution: MayorExecutionBridge | None = None
    _lifecycle: MayorLifecycleBridge | None = None
    _observation: MayorObservationBridge | None = None
    _heartbeat_count: int = 0
    _total_governance_actions: int = 0
    _total_operations: int = 0
    _offline_mode: bool = False
    _active_agents: set[str] = field(default_factory=set)
    _gateway_queue: list[dict] = field(default_factory=list)

    _registry: CityServiceRegistry = field(default_factory=CityServiceRegistry)

    _contracts: object = None
    _issues: object = None
    _sankalpa: object = None
    _audit: object = None
    _reflection: object = None
    _executor: object = None
    _council: object = None
    _federation: object = None
    _moltbook_bridge: object = None
    _moltbook_client: object = None
    _city_nadi: object = None
    _knowledge_graph: object = None
    _event_bus: object = None
    _learning: object = None
    _agent_nadi: object = None
    _immune: object = None
    _prahlad: object = None

    _last_audit_time: float = field(default=0.0)
    _recent_events: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self._service_bridge is None:
            self._service_bridge = MayorServiceBridge()
        self._service_bridge.sync_legacy_services(self)
        if self._boot is None:
            self._boot = MayorBootBridge()
        self._boot.bootstrap(self)

    def _build_ctx(self) -> PhaseContext:
        """Build PhaseContext from current Mayor state."""
        return self._context.build_phase_context(self)

    def _sync_from_ctx(self, ctx: PhaseContext) -> None:
        """Sync mutable state back from PhaseContext after phase execution."""
        self._context.sync_from_phase_context(self, ctx)

    def heartbeat(self) -> HeartbeatResult:
        """Execute one heartbeat cycle.

        Routes to the correct MURALI department based on heartbeat_count % 4.
        """
        start_time = time.time()
        result = self._execution.run_heartbeat(self)
        duration_ms = (time.time() - start_time) * 1000
        self._record_execution(result["department"], duration_ms)
        self._total_governance_actions += len(result["governance_actions"])
        self._total_operations += len(result["operations"])

        self._heartbeat_count += 1
        self._save_state()
        return result

    def run_cycle(self, cycles: int = 4) -> list[HeartbeatResult]:
        """Run multiple heartbeat cycles (default: 1 full MURALI rotation)."""
        results = []
        for _ in range(cycles):
            results.append(self.heartbeat())
        return results

    def process_github_webhook(
        self, payload: bytes, signature_header: str, secret: str, github_token: str
    ) -> dict:
        """Process an asynchronous GitHub webhook from the CI/CD Arsenal."""
        result = self._gateway.ingest_github_webhook(payload, signature_header, secret)

        if result.get("status") == "success" and result.get("event") == "workflow_run_failed":
            if self._immune is not None and hasattr(self._gateway, "fetch_github_artifact"):
                logger.info("Mayor: Routing failed Arsenal workflow to Immune System.")
                pathogens = self._gateway.fetch_github_artifact(
                    repo_name=result["repo_name"],
                    run_id=result["run_id"],
                    github_token=github_token,
                )
                if pathogens:
                    heals = self._immune.scan_and_heal(pathogens)
                    result["immune_heals"] = len(heals)
                    logger.info("Mayor: Immune System completed %d healing attempts.", len(heals))

        return result

    def _record_execution(self, department: str, duration_ms: float) -> None:
        self._observation.record_execution(self, department, duration_ms)

    def _wire_event_handlers(self) -> None:
        self._observation.wire_event_handlers(self)

    def _on_city_event(self, event: object) -> None:
        self._observation.on_city_event(self, event)

    def enqueue(
        self,
        source: str,
        text: str,
        *,
        conversation_id: str = "",
        from_agent: str = "",
    ) -> None:
        """Add an item to the gateway queue for KARMA processing."""
        enqueue_ingress(
            self,
            IngressSurface.LOCAL,
            {
                "source": source,
                "text": text,
                "conversation_id": conversation_id,
                "from_agent": from_agent,
            },
        )

    def mark_active(self, name: str) -> None:
        """Mark an agent as active for the current metabolism cycle."""
        self._active_agents.add(name)

    def _load_state(self) -> None:
        self._lifecycle.restore_mayor(self)

    def _save_state(self) -> None:
        self._lifecycle.persist_mayor(self)