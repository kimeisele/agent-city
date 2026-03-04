"""Triage Handler — Act on community triage items from DHARMA.

DHARMA's CommunityTriageHook computes _triage_items (respond/escalate actions).
This handler reads them and acts: posts responses, enqueues escalations.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.TRIAGE")


class TriageHandler(BaseKarmaHandler):
    """Consume triage items planned by DHARMA and execute them.

    Priority 25: after BrainHealth (10), Gateway (20), before Sankalpa (30).
    This ensures triage responses share the same per-cycle comment budget
    as regular discussion responses.
    """

    @property
    def name(self) -> str:
        return "triage"

    @property
    def priority(self) -> int:
        return 25

    def should_run(self, ctx: PhaseContext) -> bool:
        return hasattr(ctx, "_triage_items") and bool(ctx._triage_items)

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        triage_items = getattr(ctx, "_triage_items", [])
        if not triage_items:
            return

        acted = 0
        for item in triage_items:
            action = item.action
            disc_num = item.discussion_number

            if action == "respond":
                acted += _handle_respond(ctx, item, operations)
            elif action == "escalate":
                acted += _handle_escalate(ctx, item, operations)
            else:
                operations.append(f"triage_skip:{action}:#{disc_num}")

        if acted:
            logger.info("TRIAGE: acted on %d/%d items", acted, len(triage_items))

        # Clear consumed items
        ctx._triage_items = []  # type: ignore[attr-defined]


def _handle_respond(ctx: PhaseContext, item: object, operations: list[str]) -> int:
    """Post a triage-driven response to an unresolved thread.

    11A: Brain-gated — if Brain is offline, stay silent.
    No Brain = No Post applies to ALL outbound agent paths.
    """
    disc_num = item.discussion_number
    if ctx.discussions is None or ctx.offline_mode:
        operations.append(f"triage_respond_offline:#{disc_num}")
        return 0

    # 11A: Kill Switch — triage must not post if Brain is offline
    if ctx.brain is None:
        operations.append(f"triage_brain_offline:#{disc_num}")
        return 0

    if not ctx.discussions.can_respond(disc_num):
        operations.append(f"triage_respond_rate_limited:#{disc_num}")
        return 0

    # Build a simple acknowledgement response
    agent_name = item.suggested_agent or "mayor"
    body = (
        f"**{agent_name}** acknowledges your message in #{disc_num}.\n\n"
        f"*Triage reason*: {item.reason}\n"
        f"*Thread energy*: {item.energy:.2f}"
    )

    posted = ctx.discussions.comment(disc_num, body)
    if posted:
        ctx.discussions.record_response(disc_num)
        if ctx.thread_state is not None:
            ctx.thread_state.record_agent_response(disc_num)
        operations.append(f"triage_responded:{agent_name}:#{disc_num}")
        return 1

    operations.append(f"triage_respond_failed:#{disc_num}")
    return 0


def _handle_escalate(ctx: PhaseContext, item: object, operations: list[str]) -> int:
    """Escalate a repetition alert — emit pain signal via reactor."""
    disc_num = item.discussion_number

    # Emit pain signal if reactor is wired
    if hasattr(ctx, "reactor") and ctx.reactor is not None:
        try:
            ctx.reactor.emit_pain(
                source="community_triage",
                severity=0.7,
                detail=f"Repetition alert on #{disc_num}: {item.reason}",
            )
            operations.append(f"triage_escalated:#{disc_num}")
            return 1
        except Exception as e:
            logger.warning("TRIAGE: escalate failed for #%d: %s", disc_num, e)

    operations.append(f"triage_escalate_no_reactor:#{disc_num}")
    return 0
