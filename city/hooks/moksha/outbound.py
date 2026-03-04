"""
MOKSHA Hook: Outbound — Federation report, Moltbook posts, Discussions report/pulse, Wiki.

Extracted from moksha.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.OUTBOUND")


class FederationReportHook(BasePhaseHook):
    """Federation Nadi emit + legacy federation report."""

    @property
    def name(self) -> str:
        return "federation_report"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 60

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        stats = reflection.get("city_stats", {})
        chain_valid = reflection.get("chain_valid", False)

        # Layer 6: Federation Nadi — emit city state + flush outbox
        if ctx.federation_nadi is not None:
            nadi_payload = {
                "heartbeat": ctx.heartbeat_count,
                "population": stats.get("total", 0),
                "alive": stats.get("active", 0) + stats.get("citizen", 0),
                "chain_valid": chain_valid,
                "pr_results": reflection.get("pr_results", []),
                "mission_results": reflection.get("mission_results_terminal", []),
            }
            ctx.federation_nadi.emit(
                source="moksha",
                operation="city_report",
                payload=nadi_payload,
                priority=2,  # SATTVA
            )
            flushed = ctx.federation_nadi.flush()
            if flushed:
                reflection["federation_nadi_flushed"] = flushed

        # Layer 6: Federation report
        if ctx.federation is not None:
            report = _build_city_report(ctx, reflection)
            sent = ctx.federation.send_report(report)
            reflection["federation_report_sent"] = sent


class MoltbookOutboundHook(BasePhaseHook):
    """Post mission results + city update to Moltbook."""

    @property
    def name(self) -> str:
        return "moltbook_outbound"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 65

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_bridge is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # 8H: Brain-synthesized insight replaces raw mission dumps on Moltbook.
        # Strict gate: no terminal missions → no Brain call → no prana burn.
        mission_results = reflection.get("mission_results_terminal", [])
        if mission_results:
            insight_posted = self._post_insight_or_fallback(
                ctx, reflection, mission_results, operations,
            )
            reflection["mission_insight_posted"] = insight_posted

        # Smart Heartbeat: skip city update when nothing happened
        delta = _count_rotation_delta(reflection)
        if delta > 0:
            post_data = _build_post_data(ctx, reflection)
            posted = ctx.moltbook_bridge.post_city_update(post_data)
            reflection["moltbook_update_posted"] = posted
        else:
            operations.append("moltbook_outbound_skipped:no_delta")

        # Moltbook Assistant: reflect on engagement metrics
        if ctx.moltbook_assistant is not None:
            reflection["moltbook_assistant"] = ctx.moltbook_assistant.on_moksha()

    @staticmethod
    def _post_insight_or_fallback(
        ctx: PhaseContext,
        reflection: dict,
        mission_results: list[dict],
        operations: list[str],
    ) -> bool:
        """Generate Brain insight from missions and post to Moltbook.

        Falls back to raw post_mission_results() if Brain is unavailable.
        Bills BRAIN_CALL_COST from SystemTreasury (city-level, not agent).
        """
        brain = ctx.brain
        if brain is not None and hasattr(brain, "generate_insight"):
            try:
                from city.brain_context import build_context_snapshot
                snapshot = build_context_snapshot(ctx)
            except Exception:
                snapshot = None

            thought = brain.generate_insight(reflection, snapshot=snapshot)
            if thought is not None:
                # 8H: Record insight cost against treasury (city service, no agent to debit)
                try:
                    from city.brain_cell import BRAIN_CALL_COST
                    from city.pokedex import SYSTEM_TREASURY
                    if ctx.pokedex is not None:
                        ctx.pokedex._bank.transfer(
                            SYSTEM_TREASURY, "BURN", BRAIN_CALL_COST,
                            "moksha_insight", "service",
                        )
                except Exception:
                    pass  # cost recording is best-effort

                posted = ctx.moltbook_bridge.post_agent_insight(
                    thought, mission_count=len(mission_results),
                )
                if posted:
                    operations.append(
                        f"moltbook_insight:{len(mission_results)}_missions"
                    )
                    return True

        # Fallback: raw mission dump (Brain offline or insight failed)
        results_posted = ctx.moltbook_bridge.post_mission_results(mission_results)
        reflection["mission_results_posted"] = results_posted
        return False


class DiscussionsOutboundHook(BasePhaseHook):
    """Post city report, cross-post mission results, delta-gated pulse to Discussions."""

    @property
    def name(self) -> str:
        return "discussions_outbound"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 70

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.discussions is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # 12C: GAD-000 — pipe operations into reflection for city report transparency
        reflection["operations_log"] = list(operations)
        # Also include brain operations from KARMA (stored on ctx by brain_health)
        brain_ops = getattr(ctx, "_brain_operations", [])
        if brain_ops:
            reflection["brain_operations"] = list(brain_ops)

        if not ctx.offline_mode:
            # Smart Heartbeat: only post when something actually happened
            delta = _count_rotation_delta(reflection)

            if delta > 0:
                report_posted = ctx.discussions.post_city_report(
                    ctx.heartbeat_count,
                    reflection,
                )
                reflection["discussions_report_posted"] = report_posted

                mission_results = reflection.get("mission_results_terminal", [])
                if mission_results:
                    crossposted = ctx.discussions.cross_post_mission_results(mission_results)
                    reflection["discussions_crossposted"] = crossposted

                # Pulse to welcome thread
                pulse_stats = reflection.get("city_stats", {})
                pulsed = ctx.discussions.post_pulse(ctx.heartbeat_count, pulse_stats)
                reflection["discussions_pulse_posted"] = pulsed
                reflection["discussions_pulse_delta"] = delta
            else:
                operations.append("disc_outbound_skipped:no_delta")

        reflection["discussions"] = ctx.discussions.stats()


class WikiSyncHook(BasePhaseHook):
    """Sync agent wiki pages."""

    @property
    def name(self) -> str:
        return "wiki_sync"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 75

    def should_run(self, ctx: PhaseContext) -> bool:
        from city.registry import SVC_WIKI_PORTAL
        return ctx.registry.get(SVC_WIKI_PORTAL) is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        from city.registry import SVC_WIKI_PORTAL
        wiki = ctx.registry.get(SVC_WIKI_PORTAL)
        wiki_synced = wiki.sync(ctx.pokedex, ctx.heartbeat_count)
        reflection["wiki_synced"] = wiki_synced


# ── Helpers ──────────────────────────────────────────────────────────


def _count_rotation_delta(reflection: dict) -> int:
    """Count real events in this MURALI rotation. 0 = nothing happened."""
    delta = 0
    delta += len(reflection.get("mission_results_terminal", []))
    immune = reflection.get("immune_stats", {})
    delta += immune.get("heals_attempted", 0)
    spawner = reflection.get("spawner_stats", {})
    delta += spawner.get("spawned_this_cycle", 0)
    delta += len(reflection.get("council_executed", []))
    return delta


def _build_post_data(ctx: PhaseContext, reflection: dict) -> dict:
    """Build data dict for Moltbook city update post."""
    stats = reflection.get("city_stats", {})

    elected_mayor = None
    council_seats = 0
    open_proposals = 0
    if ctx.council is not None:
        elected_mayor = ctx.council.elected_mayor
        council_seats = ctx.council.member_count
        open_proposals = len(ctx.council.get_open_proposals())

    contract_status: dict = {}
    if ctx.contracts is not None:
        cs = ctx.contracts.stats()
        contract_status = {
            "total": cs.get("total", 0),
            "passing": cs.get("passing", 0),
            "failing": cs.get("failing", 0),
        }

    # Collect mission results from sankalpa registry
    mission_results: list[dict] = []
    if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
        try:
            all_missions = ctx.sankalpa.registry.list_missions()
            for m in all_missions:
                mission_results.append(
                    {
                        "id": m.id,
                        "name": m.name,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                        "owner": getattr(m, "owner", "unknown"),
                    }
                )
        except Exception as e:
            logger.warning("MOKSHA: Failed to collect mission results for post: %s", e)

    directive_acks = ctx.federation.pending_acks if ctx.federation is not None else []

    return {
        "heartbeat": ctx.heartbeat_count,
        "population": stats.get("total", 0),
        "alive": stats.get("active", 0) + stats.get("citizen", 0),
        "elected_mayor": elected_mayor,
        "council_seats": council_seats,
        "open_proposals": open_proposals,
        "recent_actions": [],
        "contract_status": contract_status,
        "chain_valid": reflection.get("chain_valid", False),
        "mission_results": mission_results,
        "directive_acks": directive_acks,
        "pr_results": reflection.get("pr_results", []),
    }


def _build_city_report(ctx: PhaseContext, reflection: dict) -> object:
    """Build a CityReport from current city state."""
    from city.federation import CityReport

    stats = reflection.get("city_stats", {})
    total = stats.get("total", 0)
    alive = stats.get("active", 0) + stats.get("citizen", 0)

    elected_mayor = None
    council_seats = 0
    open_proposals = 0
    if ctx.council is not None:
        elected_mayor = ctx.council.elected_mayor
        council_seats = ctx.council.member_count
        open_proposals = len(ctx.council.get_open_proposals())

    contract_status: dict = {}
    if ctx.contracts is not None:
        cs = ctx.contracts.stats()
        contract_status = {
            "total": cs.get("total", 0),
            "passing": cs.get("passing", 0),
            "failing": cs.get("failing", 0),
        }

    directive_acks = ctx.federation.pending_acks if ctx.federation is not None else []

    # Collect mission results from sankalpa registry
    mission_results: list[dict] = []
    if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
        try:
            all_missions = ctx.sankalpa.registry.list_missions()
            for m in all_missions:
                mission_results.append(
                    {
                        "id": m.id,
                        "name": m.name,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                        "owner": getattr(m, "owner", "unknown"),
                        "priority": m.priority.name
                        if hasattr(m.priority, "name")
                        else str(m.priority),
                    }
                )
        except Exception as e:
            logger.warning("MOKSHA: Failed to collect mission results: %s", e)

    return CityReport(
        heartbeat=ctx.heartbeat_count,
        timestamp=time.time(),
        population=total,
        alive=alive,
        dead=total - alive,
        elected_mayor=elected_mayor,
        council_seats=council_seats,
        open_proposals=open_proposals,
        chain_valid=reflection.get("chain_valid", False),
        recent_actions=[],
        contract_status=contract_status,
        mission_results=mission_results,
        directive_acks=directive_acks,
        pr_results=reflection.get("pr_results", []),
    )
