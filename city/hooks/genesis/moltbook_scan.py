"""
GENESIS Hook: Moltbook Feed Scanner.

Discovers agents from Moltbook feed and DM inbox.
Extracted from genesis.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import get_config

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.MOLTBOOK")


def _enqueue_item(ctx: PhaseContext, item: dict) -> None:
    """Enqueue item via CityNadi (preferred) or gateway_queue (fallback)."""
    if ctx.city_nadi is not None:
        ctx.city_nadi.enqueue(
            source=item.get("source", "unknown"),
            text=item.get("text", ""),
            conversation_id=item.get("conversation_id", ""),
            from_agent=item.get("from_agent", ""),
            post_id=item.get("post_id", ""),
            code_signals=item.get("code_signals"),
            discussion_number=item.get("discussion_number", 0),
            discussion_title=item.get("discussion_title", ""),
            direct_agent=item.get("direct_agent", ""),
            agent_name=item.get("agent_name", ""),
        )
    else:
        ctx.gateway_queue.append(item)


# Tracks seen message IDs to avoid re-processing across heartbeats
_seen_message_ids: set[str] = set()


class MoltbookFeedScanHook(BasePhaseHook):
    """Scan Moltbook feed for new agents."""

    @property
    def name(self) -> str:
        return "moltbook_feed_scan"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 10  # early: agent discovery

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_client is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        limit = get_config().get("mayor", {}).get("feed_scan_limit", 20)
        try:
            feed = ctx.moltbook_client.sync_get_feed(limit=limit)
            for post in feed:
                author_obj = post.get("author") or {}
                author = author_obj.get("name") or author_obj.get("username")
                if not author:
                    continue
                existing = ctx.pokedex.get(author)
                if not existing:
                    ctx.pokedex.discover(
                        author,
                        moltbook_profile={
                            "karma": author_obj.get("karma"),
                            "follower_count": author_obj.get("followerCount") or author_obj.get("follower_count"),
                        },
                    )
                    operations.append(author)
                    logger.info("GENESIS: Discovered agent %s", author)
        except Exception as e:
            logger.warning("GENESIS: Moltbook scan failed: %s", e)


class DMInboxHook(BasePhaseHook):
    """Poll Moltbook DMs: approve requests + enqueue unread messages."""

    @property
    def name(self) -> str:
        return "dm_inbox"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 15  # after feed scan

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_client is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        client = ctx.moltbook_client

        # Step 1: Approve pending DM requests
        try:
            requests = client.sync_get_dm_requests() if hasattr(client, "sync_get_dm_requests") else []
            for req in requests:
                req_id = req.get("id", "")
                from_agent = req.get("from", {}).get("username", req.get("from_agent", ""))
                if not req_id:
                    continue
                try:
                    client.sync_approve_dm_request(req_id) if hasattr(
                        client, "sync_approve_dm_request"
                    ) else None
                    # Send welcome via the new conversation
                    conv_id = req.get("conversation_id", "")
                    if conv_id and hasattr(client, "sync_send_dm"):
                        from city.inbox import WELCOME_MESSAGE

                        client.sync_send_dm(conv_id, WELCOME_MESSAGE)
                    operations.append(f"dm_approved:{from_agent}")
                    logger.info("GENESIS: Approved DM request from %s", from_agent)
                except Exception as e:
                    logger.warning("GENESIS: DM request approve failed: %s", e)
        except Exception as e:
            logger.warning("GENESIS: DM request poll failed: %s", e)

        # Step 2: Read DM conversations → enqueue unread messages
        try:
            conversations = (
                client.sync_get_dm_conversations()
                if hasattr(client, "sync_get_dm_conversations")
                else []
            )
            for conv in conversations:
                conv_id = conv.get("id", "")
                if not conv_id:
                    continue
                unread = conv.get("unread_count", 0) or conv.get("unread", 0)
                if not unread:
                    continue

                try:
                    messages = (
                        client.sync_get_dm_messages(conv_id)
                        if hasattr(client, "sync_get_dm_messages")
                        else []
                    )
                    for msg in messages:
                        msg_id = msg.get("id", "")
                        if msg_id in _seen_message_ids:
                            continue
                        _seen_message_ids.add(msg_id)

                        sender = msg.get("from", {}).get("username", msg.get("sender", ""))
                        content = msg.get("content", msg.get("text", ""))
                        if not sender or not content:
                            continue

                        _enqueue_item(
                            ctx,
                            {
                                "source": "dm",
                                "text": content,
                                "conversation_id": conv_id,
                                "from_agent": sender,
                            },
                        )
                        operations.append(f"dm_enqueued:{sender}")
                        logger.info("GENESIS: Enqueued DM from %s", sender)
                except Exception as e:
                    logger.warning("GENESIS: DM read failed for conv %s: %s", conv_id, e)
        except Exception as e:
            logger.warning("GENESIS: DM conversation poll failed: %s", e)

        # Cap seen set to prevent unbounded growth
        if len(_seen_message_ids) > 10000:
            excess = len(_seen_message_ids) - 5000
            for _ in range(excess):
                _seen_message_ids.pop()


class SubmoltScanHook(BasePhaseHook):
    """Scan Moltbook submolt (m/agent-city) for code signals."""

    @property
    def name(self) -> str:
        return "submolt_scan"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 20  # after DM inbox

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_bridge is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        _scan_limit = get_config().get("moltbook_bridge", {}).get("feed_scan_limit", 20)
        submolt_signals = ctx.moltbook_bridge.scan_submolt(limit=_scan_limit)
        for signal in submolt_signals:
            # Discover authors from submolt posts
            author = signal.get("author", "")
            if author:
                existing = ctx.pokedex.get(author)
                if not existing:
                    ctx.pokedex.discover(author, moltbook_profile={})
                    operations.append(author)

            # 7B-1: Engagement prana — reward agents who post in submolt
            if author and existing:
                try:
                    _engagement_prana = get_config().get(
                        "moltbook_bridge", {}
                    ).get("engagement_prana", 10)
                    ctx.pokedex.award_prana(
                        author, _engagement_prana,
                        source=f"moltbook:submolt_post:{signal.get('post_id', '')[:8]}",
                    )
                    operations.append(f"engagement_prana:{author}:+{_engagement_prana}")
                except Exception as e:
                    logger.debug("Engagement prana skipped for %s: %s", author, e)

            # Create Sankalpa mission from code signals (agent participation)
            if signal.get("code_signals") and ctx.sankalpa is not None:
                from city.missions import create_signal_mission

                mission_id = create_signal_mission(
                    ctx,
                    signal_keywords=signal.get("code_signals", []),
                    post_id=signal.get("post_id", ""),
                    author=signal.get("author", ""),
                    title=signal.get("title", ""),
                    structured=signal.get("structured", False),
                )
                if mission_id:
                    operations.append(f"submolt_mission:{mission_id}")

            # Enqueue code signals for KARMA processing
            if signal.get("code_signals"):
                _enqueue_item(
                    ctx,
                    {
                        "source": signal.get("source", "submolt"),
                        "text": signal["title"],
                        "post_id": signal["post_id"],
                        "code_signals": signal["code_signals"],
                    },
                )
                operations.append(f"submolt_signal:{signal['post_id']}")


class MoltbookAssistantHook(BasePhaseHook):
    """Moltbook Assistant: follow discovered agents."""

    @property
    def name(self) -> str:
        return "moltbook_assistant"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 80  # late: after all discovery

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_assistant is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        followed = ctx.moltbook_assistant.on_genesis(operations)
        for name in followed:
            operations.append(f"followed:{name}")
