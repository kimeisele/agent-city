"""Assistant Handler — Moltbook Assistant on_karma execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.ASSISTANT")


class AssistantHandler(BaseKarmaHandler):
    """Moltbook Assistant: execute planned actions (invites, posts, upvotes)."""

    @property
    def name(self) -> str:
        return "assistant"

    @property
    def priority(self) -> int:
        return 90

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_assistant is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        # Gate posting on governance approval — invites always allowed
        governance_actions = getattr(ctx, "_governance_actions", None)
        should_post = governance_actions is not None and governance_actions.should_post_city_report
        assistant_result = ctx.moltbook_assistant.on_karma(
            ctx.heartbeat_count,
            ctx.pokedex.stats(),
            should_post_content=should_post,
        )
        if assistant_result.get("invites_sent"):
            operations.append(f"assistant:invites={assistant_result['invites_sent']}")
        if assistant_result.get("post_created"):
            operations.append("assistant:post_created")
        elif not should_post:
            operations.append("assistant:post_skipped:governance_gate")
