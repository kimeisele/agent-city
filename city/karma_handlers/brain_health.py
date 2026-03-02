"""Brain Health Handler — System-level brain cognition during KARMA."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.BRAIN_HEALTH")

_MAX_BRAIN_CALLS_PER_CYCLE = 3


def brain_budget_ok(ctx: PhaseContext) -> bool:
    """Check if brain call budget is not exhausted for this KARMA cycle."""
    return getattr(ctx, "_brain_calls", 0) < _MAX_BRAIN_CALLS_PER_CYCLE


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
        from city.brain_context import build_context_snapshot, save_before_snapshot

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
        # Record in memory
        if ctx.brain_memory is not None:
            ctx.brain_memory.record(health_thought, ctx.heartbeat_count)
        # Post high-confidence health thoughts to discussions
        if (
            health_thought.confidence >= 0.7
            and ctx.discussions is not None
            and not ctx.offline_mode
        ):
            ctx.discussions.post_brain_thought(health_thought, ctx.heartbeat_count)
        # Budget: health check counts as 1 brain call
        ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1
