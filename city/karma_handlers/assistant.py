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
        # NOTE: GovernanceEvalHook runs in MOKSHA (after KARMA), so we
        # CANNOT gate on governance_actions here — they don't exist yet.
        # The assistant has its own cooldown logic in on_dharma().
        assistant_result = ctx.moltbook_assistant.on_karma(
            ctx.heartbeat_count,
            ctx.pokedex.stats(),
        )
        if assistant_result.get("invites_sent"):
            operations.append(f"assistant:invites={assistant_result['invites_sent']}")
        if assistant_result.get("post_created"):
            operations.append("assistant:post_created")
