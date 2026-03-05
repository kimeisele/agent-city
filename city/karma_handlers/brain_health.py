"""Brain Health Handler — System-level brain cognition during KARMA."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler
from city.brain_cell import BRAIN_CALL_COST
from city.seed_constants import NAVA, TRINITY

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.BRAIN_HEALTH")

_MAX_BRAIN_CALLS_PER_CYCLE = 3
# Max prana the brain can spend per KARMA cycle: 3 calls × 9 prana = 27
_MAX_BRAIN_PRANA_PER_CYCLE = NAVA * TRINITY  # 27 prana


def brain_budget_ok(ctx: PhaseContext) -> bool:
    """Check if brain call budget is not exhausted for this KARMA cycle.

    Two gates (defense in depth):
    1. Call count: max 3 LLM invocations per cycle
    2. Prana budget: max 27 prana spent per cycle (tracked by BrainMemory)
    """
    if getattr(ctx, "_brain_calls", 0) >= _MAX_BRAIN_CALLS_PER_CYCLE:
        return False
    if ctx.brain_memory is not None:
        spent = getattr(ctx.brain_memory, "total_prana_spent", 0)
        if isinstance(spent, int) and spent >= _MAX_BRAIN_PRANA_PER_CYCLE:
            return False
    return True


class BrainHealthHandler(BaseKarmaHandler):
    """Evaluate system health via CityBrain. Persists before_snapshot for MOKSHA."""

    @property
    def name(self) -> str:
        return "brain_health"

    @property
    def priority(self) -> int:
        return 10

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.brain is not None and hasattr(ctx.brain, "evaluate_health")

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.brain_context import (
            build_context_snapshot,
            build_field_digest,
            save_before_snapshot,
        )

        snapshot = build_context_snapshot(ctx)
        save_before_snapshot(snapshot, ctx.state_path.parent)
        health_thought = ctx.brain.evaluate_health(snapshot, memory=ctx.brain_memory)
        if health_thought is None:
            return

        operations.append(
            f"brain_health:intent={health_thought.intent.value}"
            f":confidence={health_thought.confidence:.2f}"
            f":hint={health_thought.action_hint or 'none'}"
        )
        # Record in memory (returns prana cost of the cell)
        if ctx.brain_memory is not None:
            prana_cost = ctx.brain_memory.record(
                health_thought, ctx.heartbeat_count,
            )
            if prana_cost:
                logger.debug(
                    "Brain health cost: %d prana (total spent: %d/%d)",
                    prana_cost,
                    ctx.brain_memory.total_prana_spent,
                    _MAX_BRAIN_PRANA_PER_CYCLE,
                )
        # Post high-confidence health thoughts to discussions
        if (
            health_thought.confidence >= 0.7
            and ctx.discussions is not None
            and not ctx.offline_mode
        ):
            ctx.discussions.post_brain_thought(health_thought, ctx.heartbeat_count)
        # Budget: health check counts as 1 brain call
        ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1

        # 12C: Track brain operations for GAD-000 transparency
        brain_ops = getattr(ctx, "_brain_operations", [])
        brain_ops.append(
            f"health:intent={health_thought.intent.value}"
            f":confidence={health_thought.confidence:.2f}"
        )
        ctx._brain_operations = brain_ops  # type: ignore[attr-defined]

        # 10B: Field Critique — Brain as Kshetrajna evaluates system output
        if brain_budget_ok(ctx) and hasattr(ctx.brain, "critique_field"):
            field_summary = build_field_digest(ctx)
            critique = ctx.brain.critique_field(
                field_summary, snapshot=snapshot, memory=ctx.brain_memory,
            )
            if critique is not None:
                operations.append(
                    f"brain_critique:intent={critique.intent.value}"
                    f":confidence={critique.confidence:.2f}"
                    f":hint={critique.action_hint or 'none'}"
                )
                if ctx.brain_memory is not None:
                    ctx.brain_memory.record(critique, ctx.heartbeat_count)
                ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1

                # 12C: Track critique for GAD-000 transparency
                brain_ops = getattr(ctx, "_brain_operations", [])
                brain_ops.append(
                    f"critique:intent={critique.intent.value}"
                    f":confidence={critique.confidence:.2f}"
                    f":hint={critique.action_hint or 'none'}"
                )
                ctx._brain_operations = brain_ops  # type: ignore[attr-defined]

                # 10C: Self-healing loop — execute critique action hints
                if critique.action_hint:
                    _execute_critique_hint(ctx, critique, operations)

                # Post high-confidence critiques to brainstream
                if (
                    critique.confidence >= 0.6
                    and ctx.discussions is not None
                    and not ctx.offline_mode
                ):
                    ctx.discussions.post_brain_thought(
                        critique, ctx.heartbeat_count,
                    )


def _execute_critique_hint(
    ctx: PhaseContext,
    critique: object,
    operations: list[str],
) -> None:
    """10C: Execute Brain critique action_hints — self-healing loop.

    Unlike discussion hints, these are system-level (no discussion context).
    The Brain is authorized to act on its own field critique.

    Schritt 2: Uses typed ActionParser instead of startswith() chains.
    """
    from city.brain_action import ActionVerb, parse_action_hint

    hint = getattr(critique, "action_hint", "")
    if not hint:
        return

    try:
        confidence = float(getattr(critique, "confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    action = parse_action_hint(hint, confidence=confidence)

    if action is None:
        operations.append(f"critique_hint_unknown:{hint[:40]}")
        return

    # Enforcement verbs require minimum confidence
    if action.is_enforcement and not action.confidence_sufficient:
        operations.append(
            f"critique_hint_low_confidence:{action.verb.value}"
            f":conf={confidence:.2f}"
        )
        logger.info(
            "BRAIN: %s rejected — confidence %.2f below threshold",
            action.verb.value, confidence,
        )
        # Track rejection for Brain feedback loop
        rejected = getattr(ctx, "_rejected_actions", [])
        rejected.append({
            "verb": action.verb.value,
            "target": action.target,
            "reason": f"confidence {confidence:.2f} below enforcement threshold",
            "source": "critique",
        })
        ctx._rejected_actions = rejected  # type: ignore[attr-defined]
        return

    verb = action.verb

    if verb == ActionVerb.FLAG_BOTTLENECK:
        if hasattr(ctx, "reactor") and ctx.reactor is not None:
            try:
                ctx.reactor.emit_pain(
                    source="brain_critique",
                    severity=0.6,
                    detail=f"Field critique: bottleneck in {action.target}",
                )
                operations.append(action.to_ops_string())
            except Exception as e:
                logger.warning("Critique hint flag_bottleneck failed: %s", e)
        return

    if verb == ActionVerb.INVESTIGATE:
        if action.target and ctx.sankalpa is not None:
            try:
                from city.missions import create_discussion_mission
                mission_id = create_discussion_mission(
                    ctx, 0, f"Brain critique: {action.target}", "inquiry",
                )
                if mission_id:
                    operations.append(f"critique_hint_investigate:{mission_id}")
            except Exception as e:
                logger.warning("Critique hint investigate failed: %s", e)
        return

    if verb == ActionVerb.CHECK_HEALTH:
        if hasattr(ctx, "reactor") and ctx.reactor is not None:
            try:
                ctx.reactor.emit_pain(
                    source="brain_critique",
                    severity=0.3,
                    detail=f"Field critique: health check needed for {action.target}",
                )
            except Exception as e:
                logger.warning("Critique hint check_health failed: %s", e)
        operations.append(action.to_ops_string())
        return

    if verb == ActionVerb.ESCALATE:
        if hasattr(ctx, "reactor") and ctx.reactor is not None:
            try:
                ctx.reactor.emit_pain(
                    source="brain_critique",
                    severity=0.8,
                    detail=f"ESCALATION from field critique: {action.target}",
                )
            except Exception as e:
                logger.warning("Critique hint escalate failed: %s", e)
        operations.append(action.to_ops_string())
        return

    # 12A: Retract a bad post — edit it to [RETRACTED] on GitHub
    if verb == ActionVerb.RETRACT:
        comment_id = action.target
        if comment_id and ctx.discussions is not None and not ctx.offline_mode:
            try:
                reason = getattr(critique, "evidence", "") or "quality"
                retracted = ctx.discussions.retract_post(comment_id, reason=reason)
                if retracted:
                    operations.append(f"critique_retract:{comment_id[:20]}")
                    logger.info("BRAIN: Retracted post %s", comment_id[:20])
                else:
                    operations.append(f"critique_retract_failed:{comment_id[:20]}")
            except Exception as e:
                logger.warning("Critique hint retract failed: %s", e)
        return

    # 12A: Quarantine an agent — freeze + drain prana
    if verb == ActionVerb.QUARANTINE:
        agent_name = action.target
        if agent_name and ctx.pokedex is not None:
            try:
                reason = getattr(critique, "evidence", "") or "brain_critique"
                ctx.pokedex.freeze(agent_name, f"quarantine:{reason[:60]}")
                from city.registry import SVC_ROUTER
                router = ctx.registry.get(SVC_ROUTER) if ctx.registry else None
                if router is not None:
                    router.remove(agent_name)
                operations.append(f"critique_quarantine:{agent_name}")
                logger.info("BRAIN: Quarantined agent %s — %s", agent_name, reason[:60])
            except Exception as e:
                logger.warning("Critique hint quarantine failed: %s", e)
        return

    # Verb recognized but no handler — log for audit trail
    operations.append(f"critique_hint_unhandled:{action.verb.value}")
