"""
MOLTBOOK SENDER HOOK — Drains the persistent outbox and sends messages via the dumb bridge.

This hook runs during MOKSHA phase, after other outbound hooks that may append messages.
It reads pending messages from data/moltbook_outbox.json, attempts to send them,
and removes them on success.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.MOLTBOOK_SENDER")


class MoltbookSenderHook(BasePhaseHook):
    """Send pending outbox messages via the dumb bridge."""

    @property
    def name(self) -> str:
        return "moltbook_sender"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        # Must run after hooks that append to outbox (e.g., EventDrivenOutboundHook pri=65)
        return 66  # right after EventDrivenOutboundHook

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_bridge is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.moltbook_outbox import get_pending_messages, mark_as_sent

        pending = get_pending_messages()
        if not pending:
            operations.append("moltbook_sender:no_pending")
            return

        bridge = ctx.moltbook_bridge
        sent_count = 0
        failed_count = 0

        # Process in reverse order to avoid index shifting when removing
        for i in reversed(range(len(pending))):
            msg = pending[i]
            text = msg.get("text", "")
            thread_id = msg.get("thread_id", "")

            if not text:
                logger.warning("Skipping empty message in outbox")
                mark_as_sent(i)  # remove malformed entry
                continue

            success = False
            if thread_id:
                # This is a comment reply
                success = bridge.comment_with_verification(thread_id, text)
            else:
                # This is a new post
                title = msg.get("metadata", {}).get("title", "Agent City Update")
                success = bridge.create_post(title, text)

            if success:
                mark_as_sent(i)
                sent_count += 1
                logger.info("Outbound message sent (thread_id=%s)", thread_id)
            else:
                failed_count += 1
                logger.error("Failed to send outbound message (thread_id=%s)", thread_id)

        operations.append(f"moltbook_sender:sent={sent_count},failed={failed_count}")
        logger.info(
            "MOLTBOOK_SENDER: processed %d messages (%d sent, %d failed)",
            len(pending), sent_count, failed_count
        )
