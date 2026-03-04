"""
MOKSHA Hook: Reflection & Stats Collection.

Chain verification, nadi/event_bus/immune/learning stats, daemon metrics,
audit with cooldown, pattern analysis, brain reflection + memory decay.

Extracted from moksha.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from config import get_config

from city.missions import create_audit_mission, create_improvement_mission
from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.REFLECTION")


class ReflectionStatsHook(BasePhaseHook):
    """Collect core city stats into reflection dict on ctx."""

    @property
    def name(self) -> str:
        return "reflection_stats"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 5  # first: builds reflection dict that later hooks read

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        stats = ctx.pokedex.stats()
        chain_valid = ctx.pokedex.verify_event_chain()
        network_stats = ctx.network.stats()

        reflection: dict = {
            "chain_valid": chain_valid,
            "heartbeat": ctx.heartbeat_count,
            "city_stats": stats,
            "network_stats": network_stats,
            "events_since_last": len(ctx.recent_events),
        }

        # Nadi stats
        if ctx.city_nadi is not None:
            nadi_stats = ctx.city_nadi.stats()
            if nadi_stats:
                reflection["nadi_stats"] = nadi_stats

        # Cognition: EventBus history + stats
        if ctx.event_bus is not None:
            from city.cognition import get_bus_stats, get_event_history

            bus_stats = get_bus_stats()
            if bus_stats:
                reflection["event_bus_stats"] = bus_stats
            recent_bus_events = get_event_history(limit=20)
            if recent_bus_events:
                reflection["event_bus_recent"] = len(recent_bus_events)

        # Agent Nadi stats
        if ctx.agent_nadi is not None:
            agent_nadi_stats = ctx.agent_nadi.stats()
            if agent_nadi_stats:
                reflection["agent_nadi_stats"] = agent_nadi_stats

        # Immune system stats
        if ctx.immune is not None:
            immune_stats = ctx.immune.stats()
            if immune_stats:
                reflection["immune_stats"] = immune_stats

        # Hebbian learning: decay → trim → flush weights + stats
        if ctx.learning is not None:
            autonomy_cfg = get_config().get("autonomy", {})
            decay_factor = autonomy_cfg.get("decay_factor", 0.01)
            max_entries = autonomy_cfg.get("max_synapse_entries", 500)

            decayed = ctx.learning.decay(decay_factor)
            trimmed = ctx.learning.trim(max_entries)
            ctx.learning.flush()

            learning_stats = ctx.learning.stats()
            if learning_stats:
                learning_stats["decayed"] = decayed
                learning_stats["trimmed"] = trimmed
                reflection["learning_stats"] = learning_stats

        # 12C: GAD-000 Transparency — Prana economy snapshot
        try:
            economy = ctx.pokedex.economy_snapshot()
            if economy:
                reflection["economy_stats"] = economy
        except Exception:
            # economy_snapshot may not exist on older Pokedex versions
            pass

        # Daemon metrics (if running in daemon mode)
        from city.registry import SVC_DAEMON

        daemon = ctx.registry.get(SVC_DAEMON)
        if daemon is not None:
            reflection["daemon_stats"] = daemon.stats()

        # Drain event buffer into reflection
        if ctx.recent_events:
            logger.info(
                "MOKSHA: %d city events since last reflection",
                len(ctx.recent_events),
            )
            ctx.recent_events.clear()

        if not chain_valid:
            logger.warning("MOKSHA: Event chain integrity BROKEN")
        else:
            logger.info(
                "MOKSHA: Reflection — %d agents, chain valid, %d events",
                stats.get("total", 0),
                stats.get("events", 0),
            )

        # Store reflection on ctx for later hooks
        ctx._reflection = reflection  # type: ignore[attr-defined]


class AuditHook(BasePhaseHook):
    """Run audit with cooldown, create missions for critical findings."""

    @property
    def name(self) -> str:
        return "audit"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 20

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.audit is None:
            return False
        cooldown = get_config().get("mayor", {}).get("audit_cooldown_s", 900)
        return (time.time() - ctx.last_audit_time) > cooldown

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        try:
            finding_count = ctx.audit.run_all()
            ctx.last_audit_time = time.time()
            summary = ctx.audit.summary()
            reflection["audit"] = summary

            for finding in ctx.audit.critical_findings():
                create_audit_mission(ctx, finding)

            logger.info("MOKSHA: Audit complete — %d findings", finding_count)
        except Exception as e:
            logger.warning("MOKSHA: Audit failed: %s", e)


class ReflectionAnalysisHook(BasePhaseHook):
    """Pattern analysis + Hebbian synapse bridge."""

    @property
    def name(self) -> str:
        return "reflection_analysis"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 25

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.reflection is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        try:
            insights = ctx.reflection.analyze_patterns()
            if insights:
                proposal = ctx.reflection.propose_improvement(insights)
                if proposal is not None:
                    create_improvement_mission(ctx, proposal)
                    _submit_reflection_proposal(ctx, proposal)
                reflection["insights"] = len(insights)
                reflection["proposal"] = proposal.title if proposal else None

                # Bridge: Reflection insights → Hebbian synapses
                if ctx.learning is not None:
                    for insight in insights:
                        insight_type = getattr(insight, "type", "")
                        insight_msg = getattr(insight, "message", "")[:40]
                        if insight_type == "failure_pattern":
                            ctx.learning.record_outcome(
                                f"pattern:{insight_msg}",
                                "repeat",
                                success=False,
                            )
                        elif insight_type == "performance":
                            ctx.learning.record_outcome(
                                f"pattern:{insight_msg}",
                                "optimize",
                                success=True,
                            )
                    reflection["synapse_bridge_updates"] = len(insights)

            reflection["reflection_stats"] = {
                "executions_analyzed": ctx.reflection.get_stats().executions_analyzed,
                "insights_generated": ctx.reflection.get_stats().insights_generated,
            }
        except Exception as e:
            logger.warning("MOKSHA: Reflection analysis failed: %s", e)


class BrainReflectionHook(BasePhaseHook):
    """Brain cycle reflection + memory decay."""

    @property
    def name(self) -> str:
        return "brain_reflection"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 45

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.brain is not None and hasattr(ctx.brain, "reflect_on_cycle")

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        brain = ctx.brain

        from city.brain_context import (
            build_context_snapshot,
            diff_snapshots,
            load_before_snapshot,
        )

        snapshot = build_context_snapshot(ctx)
        before_snapshot = load_before_snapshot(ctx.state_path.parent)
        if before_snapshot is not None:
            outcome_diff = diff_snapshots(before_snapshot, snapshot)
            reflection["outcome_diff"] = outcome_diff
        cycle_thought = brain.reflect_on_cycle(
            snapshot, reflection, memory=ctx.brain_memory,
        )
        if cycle_thought is not None:
            reflection["brain_reflection"] = cycle_thought.to_dict()
            if ctx.brain_memory is not None:
                ctx.brain_memory.record(cycle_thought, ctx.heartbeat_count)
            # High-confidence improvements → Sankalpa mission
            if (
                cycle_thought.action_hint.startswith("create_mission:")
                and cycle_thought.confidence >= 0.7
                and ctx.sankalpa is not None
            ):
                mission_desc = cycle_thought.action_hint[len("create_mission:"):]
                proposal = type("BrainProposal", (), {
                    "id": f"brain_{ctx.heartbeat_count}",
                    "title": mission_desc[:60] or "Brain improvement",
                    "description": cycle_thought.comprehension,
                })()
                create_improvement_mission(ctx, proposal)

            # 6C-1: Post reflection to Brainstream discussion thread
            if ctx.discussions is not None and not ctx.offline_mode:
                outcome_diff = reflection.get("outcome_diff")
                posted = ctx.discussions.post_brainstream_reflection(
                    cycle_thought, ctx.heartbeat_count, outcome_diff,
                )
                if posted:
                    operations.append(f"brainstream_reflection:#{ctx.heartbeat_count}")

        # Decay stale brain cells, then flush to disk
        if ctx.brain_memory is not None:
            if hasattr(ctx.brain_memory, "decay"):
                reaped = ctx.brain_memory.decay(ctx.heartbeat_count)
                if reaped:
                    reflection["brain_cells_decayed"] = reaped
            ctx.brain_memory.flush()


# ── Helpers ──────────────────────────────────────────────────────────


def _submit_reflection_proposal(ctx: PhaseContext, proposal: object) -> None:
    """Submit a reflection improvement as a council proposal."""
    if ctx.council is None or ctx.council.member_count == 0:
        return

    proposer = ctx.council.elected_mayor
    if proposer is None:
        return

    from city.council import ProposalType

    ctx.council.propose(
        title=f"Improve: {proposal.title}",
        description=proposal.description,
        proposer=proposer,
        proposal_type=ProposalType.POLICY,
        action={"type": "improve", "proposal_id": proposal.id},
        timestamp=time.time(),
        heartbeat=ctx.heartbeat_count,
    )
