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

    # Schritt 6B: Unified dispatch via CityIntentExecutor
    from city.registry import SVC_ATTENTION, SVC_INTENT_EXECUTOR

    executor = ctx.registry.get(SVC_INTENT_EXECUTOR) if ctx.registry else None
    attention = ctx.registry.get(SVC_ATTENTION) if ctx.registry else None

    if executor is not None:
        evidence = getattr(critique, "evidence", "") or ""
        intent = action.to_city_intent(source="critique", detail=evidence[:60])
        handler_name = attention.route(intent.signal) if attention else None
        result = executor.execute(ctx, intent, handler_name)
        operations.append(f"critique_action:{action.verb.value}:{result}")
    else:
        operations.append(f"critique_hint_unhandled:{action.verb.value}")
