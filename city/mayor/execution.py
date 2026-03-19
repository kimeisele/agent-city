from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from vibe_core.mahamantra.protocols import QUARTERS

from city.registry import SVC_EVENT_BUS

if TYPE_CHECKING:
    from .kernel import Mayor
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.MAYOR.EXECUTION")

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


@dataclass(frozen=True)
class MayorExecutionBridge:
    """Owns MURALI phase routing and execution semantics for Mayor."""

    def run_heartbeat(self, mayor: Mayor) -> HeartbeatResult:
        """Execute one heartbeat = FULL MURALI cycle.

        GENESIS → DHARMA → KARMA → MOKSHA in sequence. Causal order:
        perceive → evaluate → act → persist. Not one phase per cycle.
        """
        start_time = time.time()
        self._advance_venu()

        logger.info("Mayor heartbeat #%d — full MURALI cycle", mayor._heartbeat_count)

        result: HeartbeatResult = {
            "heartbeat": mayor._heartbeat_count,
            "department": "MURALI",
            "department_idx": 0,
            "timestamp": start_time,
            "discovered": [],
            "governance_actions": [],
            "operations": [],
            "reflection": {},
        }

        ctx = mayor._build_ctx()

        # MURALI: all 4 phases in causal order
        for dept_idx in range(QUARTERS):
            dept_name = DEPARTMENT_NAMES[dept_idx]
            self._emit_phase_transition(mayor, dept_name)
            self._dispatch_phase(mayor, ctx, dept_idx, result)
            mayor._sync_from_ctx(ctx)
            # Re-build ctx to carry state from previous phase
            ctx = mayor._build_ctx()

        return result

    def _advance_venu(self) -> None:
        try:
            from vibe_core.mahamantra import mahamantra

            mahamantra.venu.step()
        except Exception as exc:
            logger.warning("VenuOrchestrator step failed: %s", exc)

    def _emit_phase_transition(self, mayor: Mayor, dept_name: str) -> None:
        if mayor._registry.get(SVC_EVENT_BUS) is None:
            return
        from city.cognition import emit_event

        emit_event(
            "PHASE_TRANSITION",
            "mayor",
            f"heartbeat #{mayor._heartbeat_count} → {dept_name}",
            {"heartbeat": mayor._heartbeat_count, "department": dept_name},
        )

    def _dispatch_phase(
        self,
        mayor: Mayor,
        ctx: PhaseContext,
        department: int,
        result: HeartbeatResult,
    ) -> None:
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
            self._run_moksha_diagnostics_if_due(mayor, result)

    def _run_moksha_diagnostics_if_due(
        self,
        mayor: Mayor,
        result: HeartbeatResult,
    ) -> None:
        if mayor._heartbeat_count % 40 != 3 or mayor._offline_mode:
            return
        immune = mayor._immune
        if immune is None or not hasattr(immune, "run_self_diagnostics"):
            return
        logger.info("MOKSHA Phase: Triggering Autonomous Immune Diagnostics.")
        heals = immune.run_self_diagnostics()
        result["reflection"]["immune_heals"] = len(heals)