"""
MAYOR AGENT — The Autonomous City Operator
=============================================

Thin dispatcher. Delegates to city/phases/{genesis,dharma,karma,moksha}.py.
Owns: heartbeat loop, state persistence, event handling, external interface.

MURALI Departments:
  0 GENESIS: Census (discover agents from Moltbook feed)
  1 DHARMA:  Governance (cell homeostasis, zone health, contracts, sankalpa missions)
  2 KARMA:   Operations (process gateway queue, sankalpa intents)
  3 MOKSHA:  Reflection (audit, reflection analysis, stats, chain verification)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from vibe_core.mahamantra.protocols import QUARTERS

from city.gateway import CityGateway
from city.network import CityNetwork
from city.phases import PhaseContext
from city.pokedex import Pokedex
from city.registry import (
    SVC_AGENT_NADI,
    SVC_AUDIT,
    SVC_BRAIN,
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
    CityServiceRegistry,
)
from config import get_config

logger = logging.getLogger("AGENT_CITY.MAYOR")

# MURALI departments — SSOT from steward-protocol QUARTERS (4)
GENESIS = 0
DHARMA = 1
KARMA = 2
MOKSHA = 3

DEPARTMENT_NAMES = {
    GENESIS: "GENESIS",
    DHARMA: "DHARMA",
    KARMA: "KARMA",
    MOKSHA: "MOKSHA",
}


class HeartbeatResult(TypedDict):
    """Result of a single heartbeat cycle."""

    heartbeat: int
    department: str
    department_idx: int
    timestamp: float
    discovered: list[str]
    governance_actions: list[str]
    operations: list[str]
    reflection: dict


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
    _heartbeat_count: int = 0
    _offline_mode: bool = False
    _active_agents: set[str] = field(default_factory=set)
    _gateway_queue: list[dict] = field(default_factory=list)

    # Service registry (preferred wiring path)
    _registry: CityServiceRegistry = field(default_factory=CityServiceRegistry)

    # Legacy service fields (backward compat — prefer _registry)
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

    # Internal state
    _last_audit_time: float = field(default=0.0)
    _recent_events: list = field(default_factory=list)

    # Legacy field → registry name mapping
    _LEGACY_FIELD_MAP: dict[str, str] = field(default_factory=dict, repr=False, init=False)

    def __post_init__(self) -> None:
        # Migrate legacy kwargs into registry (backward compat)
        _field_to_svc = {
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
        for field_name, svc_name in _field_to_svc.items():
            val = getattr(self, field_name, None)
            if val is not None and not self._registry.has(svc_name):
                self._registry.register(svc_name, val)

        # Brain in a Jar — LLM cognition organ (lazy provider init)
        if not self._registry.has(SVC_BRAIN):
            from city.brain import CityBrain
            self._registry.register(SVC_BRAIN, CityBrain())

        # Brain Memory — persistent bounded FIFO for brain thoughts
        from city.registry import SVC_BRAIN_MEMORY

        if not self._registry.has(SVC_BRAIN_MEMORY):
            from city.brain_memory import BrainMemory

            brain_mem = BrainMemory(path=self._state_path.parent / "brain_memory.json")
            brain_mem.load()
            self._registry.register(SVC_BRAIN_MEMORY, brain_mem)

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()
        self._wire_event_handlers()

    # ── PhaseContext Builder ──────────────────────────────────────────

    def _build_ctx(self) -> PhaseContext:
        """Build PhaseContext from current Mayor state."""
        # Sync any post-init field mutations into registry
        _field_to_svc = {
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
        for field_name, svc_name in _field_to_svc.items():
            val = getattr(self, field_name, None)
            if val is not None and not self._registry.has(svc_name):
                self._registry.register(svc_name, val)

        return PhaseContext(
            pokedex=self._pokedex,
            gateway=self._gateway,
            network=self._network,
            heartbeat_count=self._heartbeat_count,
            offline_mode=self._offline_mode,
            state_path=self._state_path,
            active_agents=self._active_agents,
            gateway_queue=self._gateway_queue,
            registry=self._registry,
            last_audit_time=self._last_audit_time,
            recent_events=self._recent_events,
        )

    def _sync_from_ctx(self, ctx: PhaseContext) -> None:
        """Sync mutable state back from PhaseContext after phase execution."""
        self._last_audit_time = ctx.last_audit_time

    # ── Heartbeat Loop ────────────────────────────────────────────────

    def heartbeat(self) -> HeartbeatResult:
        """Execute one heartbeat cycle.

        Routes to the correct MURALI department based on heartbeat_count % 4.
        """
        start_time = time.time()

        # Advance VenuOrchestrator — drives MURALI phase rotation
        try:
            from vibe_core.mahamantra import mahamantra

            mahamantra.venu.step()
        except Exception as e:
            logger.warning("VenuOrchestrator step failed: %s", e)

        department = self._heartbeat_count % QUARTERS
        dept_name = DEPARTMENT_NAMES[department]

        logger.info(
            "Mayor heartbeat #%d — department %s",
            self._heartbeat_count,
            dept_name,
        )

        result: HeartbeatResult = {
            "heartbeat": self._heartbeat_count,
            "department": dept_name,
            "department_idx": department,
            "timestamp": start_time,
            "discovered": [],
            "governance_actions": [],
            "operations": [],
            "reflection": {},
        }

        ctx = self._build_ctx()

        # Cognition: emit phase transition event
        if self._registry.get(SVC_EVENT_BUS) is not None:
            from city.cognition import emit_event

            emit_event(
                "PHASE_TRANSITION",
                "mayor",
                f"heartbeat #{self._heartbeat_count} → {dept_name}",
                {"heartbeat": self._heartbeat_count, "department": dept_name},
            )

        if department == GENESIS:
            from city.phases import genesis

            result["discovered"] = genesis.execute(ctx)
        elif department == DHARMA:
            from city.phases import dharma

            result["governance_actions"] = dharma.execute(ctx)
        elif department == KARMA:
            from city.phases import karma

            result["operations"] = karma.execute(ctx)
        elif department == MOKSHA:
            from city.phases import moksha

            result["reflection"] = moksha.execute(ctx)

            # Autonomous Introspection — The city checks itself for bleeding
            # Triggered during MOKSHA, every 10 cycles (40 heartbeats) to prevent fatigue
            # Skipped offline: diagnostics invoke ruff/subprocess which isn't available
            if self._heartbeat_count % 40 == 3 and not self._offline_mode:
                if self._immune is not None and hasattr(self._immune, "run_self_diagnostics"):
                    logger.info("MOKSHA Phase: Triggering Autonomous Immune Diagnostics.")
                    heals = self._immune.run_self_diagnostics()
                    result["reflection"]["immune_heals"] = len(heals)

        self._sync_from_ctx(ctx)

        # Record execution for reflection (every heartbeat)
        duration_ms = (time.time() - start_time) * 1000
        self._record_execution(dept_name, duration_ms)

        self._heartbeat_count += 1
        self._save_state()
        return result

    def run_cycle(self, cycles: int = 4) -> list[HeartbeatResult]:
        """Run multiple heartbeat cycles (default: 1 full MURALI rotation)."""
        results = []
        for _ in range(cycles):
            results.append(self.heartbeat())
        return results

    # ── Async CI/CD Arsenal Integration ───────────────────────────────

    def process_github_webhook(
        self, payload: bytes, signature_header: str, secret: str, github_token: str
    ) -> dict:
        """Process an asynchronous GitHub webhook from the CI/CD Arsenal.

        If a workflow failed, fetches the JSON report artifact and injects
        the extracted tracebacks directly into the Immune System.
        """
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

    # ── Reflection Recording ──────────────────────────────────────────

    def _record_execution(self, department: str, duration_ms: float) -> None:
        """Record a heartbeat execution via Reflection protocol."""
        reflection = self._registry.get(SVC_REFLECTION)
        if reflection is None:
            return

        from vibe_core.protocols.reflection import ExecutionRecord

        record = ExecutionRecord(
            command=f"mayor.heartbeat.{department}",
            success=True,
            duration_ms=duration_ms,
        )
        reflection.record_execution(record)

    # ── Event Handlers ────────────────────────────────────────────────

    def _wire_event_handlers(self) -> None:
        """Subscribe to AnantaShesha events via CityNetwork's anchor."""
        try:
            from vibe_core.ouroboros.ananta_shesha import get_system_anchor

            anchor = get_system_anchor()
            for event_type in (
                "AGENT_REGISTERED",
                "AGENT_UNREGISTERED",
                "AGENT_MESSAGE",
                "AGENT_BROADCAST",
            ):
                anchor.add_handler(event_type, self._on_city_event)
        except Exception as e:
            logger.warning("Event handler wiring failed: %s", e)

    def _on_city_event(self, event: object) -> None:
        """Handle city events from AnantaShesha. Buffers for MOKSHA reflection."""
        self._recent_events.append(
            {
                "type": event.event_type,
                "data": event.data,
                "timestamp": event.timestamp.isoformat()
                if hasattr(event.timestamp, "isoformat")
                else str(event.timestamp),
            }
        )
        _mayor_cfg = get_config().get("mayor", {})
        if len(self._recent_events) > _mayor_cfg.get("event_buffer_max", 200):
            self._recent_events = self._recent_events[-_mayor_cfg.get("event_buffer_trim", 100) :]

    # ── External Interface ────────────────────────────────────────────

    def enqueue(
        self,
        source: str,
        text: str,
        *,
        conversation_id: str = "",
        from_agent: str = "",
    ) -> None:
        """Add an item to the gateway queue for KARMA processing.

        Args:
            source: Origin identifier (e.g. 'dm', 'feed', agent name).
            text: Message content.
            conversation_id: Moltbook DM conversation ID for response routing.
            from_agent: Sender's Moltbook username.
        """
        self._gateway_queue.append(
            {
                "source": source,
                "text": text,
                "conversation_id": conversation_id,
                "from_agent": from_agent,
            }
        )

    def mark_active(self, name: str) -> None:
        """Mark an agent as active for the current metabolism cycle."""
        self._active_agents.add(name)

    # ── State Persistence ─────────────────────────────────────────────

    def _load_state(self) -> None:
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                self._heartbeat_count = data.get("heartbeat_count", 0)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_state(self) -> None:
        state: MayorState = {
            "heartbeat_count": self._heartbeat_count,
            "last_heartbeat": time.time(),
            "discovered_agents": [a["name"] for a in self._pokedex.list_all()],
            "archived_agents": [a["name"] for a in self._pokedex.list_by_status("archived")],
            "total_governance_actions": 0,
            "total_operations": 0,
        }
        self._state_path.write_text(json.dumps(state, indent=2))
