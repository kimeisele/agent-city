"""
MOLTBOOK INBOUND HOOK — Fetches mentions/replies and ingests them as signals.

This hook runs during GENESIS phase. It uses the dumb bridge to fetch raw data,
converts them to standard Signal objects, and appends them to the city's inbox.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.MOLTBOOK_INBOUND")


class MoltbookInboundHook(BasePhaseHook):
    """Ingest Moltbook mentions and replies as signals."""

    @property
    def name(self) -> str:
        return "moltbook_inbound"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 22  # after feed scan, before other processing

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_bridge is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        bridge = ctx.moltbook_bridge

        # Fetch new mentions and replies with error resilience
        try:
            mentions = bridge.fetch_mentions(limit=20)
        except Exception as e:
            logger.error("Failed to fetch mentions: %s", e)
            mentions = []
        try:
            replies = bridge.fetch_replies(limit=20)
        except Exception as e:
            logger.error("Failed to fetch replies: %s", e)
            replies = []

        all_items = mentions + replies
        if not all_items:
            operations.append("moltbook_inbound:no_new_items")
            return

        # Convert to standard signal format
        signals = []
        for item in all_items:
            signal = {
                "source": item.get("source", "moltbook"),
                "id": item.get("id", ""),
                "author": item.get("author", ""),
                "body": item.get("body", ""),
                "post_id": item.get("post_id"),
                "parent_id": item.get("parent_id"),
                "timestamp": ctx.heartbeat_count,
            }
            signals.append(signal)

        # Append to city's inbox using enqueue_ingress (standard ingress surface)
        from city.membrane import enqueue_ingress, IngressSurface
        for sig in signals:
            try:
                enqueue_ingress(
                    ctx,
                    IngressSurface.MOLTBOOK_MENTION if sig["source"] == "moltbook_mention" else IngressSurface.MOLTBOOK_REPLY,
                    {
                        "source": sig["source"],
                        "text": sig["body"],
                        "from_agent": sig["author"],
                        "signal_id": sig["id"],
                        "post_id": sig.get("post_id"),
                        "parent_id": sig.get("parent_id"),
                    },
                )
                operations.append(f"moltbook_inbound:enqueued:{sig['id'][:8]}")
            except Exception as e:
                logger.error("Failed to enqueue signal %s: %s", sig["id"], e)
                operations.append("moltbook_inbound:enqueue_failed")

        logger.info(
            "MOLTBOOK_INBOUND: ingested %d signals (%d mentions, %d replies)",
            len(signals), len(mentions), len(replies)
        )
