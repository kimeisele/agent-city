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

from city.contracts import ContractRegistry
from city.council import CityCouncil
from city.executor import IntentExecutor
from city.federation import FederationRelay
from city.gateway import CityGateway
from city.issues import CityIssueManager
from city.network import CityNetwork
from city.phases import PhaseContext
from city.pokedex import Pokedex
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

    # Layer 3 governance wiring (all optional for backward compatibility)
    _contracts: ContractRegistry | None = None
    _issues: CityIssueManager | None = None
    _sankalpa: object = None  # SankalpaOrchestrator (steward-protocol)
    _audit: object = None  # AuditKernel (steward-protocol)
    _reflection: object = None  # BasicReflection (steward-protocol)

    # Layer 4 action delegation (optional for backward compatibility)
    _executor: IntentExecutor | None = None

    # Layer 5 democratic governance (optional for backward compatibility)
    _council: CityCouncil | None = None

    # Layer 6 federation (optional for backward compatibility)
    _federation: FederationRelay | None = None

    # Layer 7 Moltbook inbox (optional for backward compatibility)
    _moltbook_client: object = None  # MoltbookClient (steward-protocol)

    # Internal state
    _last_audit_time: float = field(default=0.0)
    _recent_events: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()
        self._wire_event_handlers()

    # ── PhaseContext Builder ──────────────────────────────────────────

    def _build_ctx(self) -> PhaseContext:
        """Build PhaseContext from current Mayor state."""
        return PhaseContext(
            pokedex=self._pokedex,
            gateway=self._gateway,
            network=self._network,
            heartbeat_count=self._heartbeat_count,
            offline_mode=self._offline_mode,
            state_path=self._state_path,
            active_agents=self._active_agents,
            gateway_queue=self._gateway_queue,
            contracts=self._contracts,
            issues=self._issues,
            sankalpa=self._sankalpa,
            audit=self._audit,
            reflection=self._reflection,
            executor=self._executor,
            council=self._council,
            federation=self._federation,
            moltbook_client=self._moltbook_client,
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
            self._heartbeat_count, dept_name,
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

    # ── Reflection Recording ──────────────────────────────────────────

    def _record_execution(self, department: str, duration_ms: float) -> None:
        """Record a heartbeat execution via Reflection protocol."""
        if self._reflection is None:
            return

        from vibe_core.protocols.reflection import ExecutionRecord

        record = ExecutionRecord(
            command=f"mayor.heartbeat.{department}",
            success=True,
            duration_ms=duration_ms,
        )
        self._reflection.record_execution(record)

    # ── Event Handlers ────────────────────────────────────────────────

    def _wire_event_handlers(self) -> None:
        """Subscribe to AnantaShesha events via CityNetwork's anchor."""
        try:
            from vibe_core.ouroboros.ananta_shesha import get_system_anchor
            anchor = get_system_anchor()
            for event_type in ("AGENT_REGISTERED", "AGENT_UNREGISTERED",
                               "AGENT_MESSAGE", "AGENT_BROADCAST"):
                anchor.add_handler(event_type, self._on_city_event)
        except Exception as e:
            logger.warning("Event handler wiring failed: %s", e)

    def _on_city_event(self, event: object) -> None:
        """Handle city events from AnantaShesha. Buffers for MOKSHA reflection."""
        self._recent_events.append({
            "type": event.event_type,
            "data": event.data,
            "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
        })
        _mayor_cfg = get_config().get("mayor", {})
        if len(self._recent_events) > _mayor_cfg.get("event_buffer_max", 200):
            self._recent_events = self._recent_events[-_mayor_cfg.get("event_buffer_trim", 100):]

    # ── External Interface ────────────────────────────────────────────

    def enqueue(
        self, source: str, text: str,
        *, conversation_id: str = "", from_agent: str = "",
    ) -> None:
        """Add an item to the gateway queue for KARMA processing.

        Args:
            source: Origin identifier (e.g. 'dm', 'feed', agent name).
            text: Message content.
            conversation_id: Moltbook DM conversation ID for response routing.
            from_agent: Sender's Moltbook username.
        """
        self._gateway_queue.append({
            "source": source,
            "text": text,
            "conversation_id": conversation_id,
            "from_agent": from_agent,
        })

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
