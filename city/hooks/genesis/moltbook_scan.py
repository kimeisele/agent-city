"""
GENESIS Hook: Moltbook Feed Scanner.

Discovers agents from Moltbook feed and DM inbox.
Extracted from genesis.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from config import get_config

from city.membrane import IngressSurface, enqueue_ingress
from city.net_retry import safe_call
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.MOLTBOOK")
# Tracks seen message IDs to avoid re-processing across heartbeats.
# OrderedDict for FIFO eviction (oldest entries removed first).
_seen_message_ids: OrderedDict[str, None] = OrderedDict()
_SEEN_MESSAGE_IDS_MAX = 10000


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
        feed = safe_call(
            ctx.moltbook_client.sync_get_feed, limit=limit,
            label="moltbook_feed",
        )
        if feed is None:
            return

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
                        "follower_count": (
                            author_obj.get("followerCount")
                            or author_obj.get("follower_count")
                        ),
                    },
                )
                operations.append(author)
                logger.info("GENESIS: Discovered agent %s", author)


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
        self._approve_dm_requests(client, operations)
        self._read_dm_conversations(client, ctx, operations)

    @staticmethod
    def _approve_dm_requests(
        client: object, operations: list[str],
    ) -> None:
        """Step 1: Approve pending DM requests."""
        if not hasattr(client, "sync_get_dm_requests"):
            return
        pending = safe_call(client.sync_get_dm_requests, label="moltbook_dm_requests")
        if pending is None:
            return

        for req in pending:
            req_id = req.get("id", "")
            from_agent = req.get("from", {}).get("username", req.get("from_agent", ""))
            if not req_id:
                continue
            if hasattr(client, "sync_approve_dm_request"):
                approved = safe_call(
                    client.sync_approve_dm_request, req_id,
                    label=f"moltbook_dm_approve:{req_id[:8]}",
                )
                if approved is None:
                    continue
            # Send welcome via the new conversation
            conv_id = req.get("conversation_id", "")
            if conv_id and hasattr(client, "sync_send_dm"):
                from city.inbox import WELCOME_MESSAGE
                safe_call(
                    client.sync_send_dm, conv_id, WELCOME_MESSAGE,
                    label=f"moltbook_dm_welcome:{conv_id[:8]}",
                )
            operations.append(f"dm_approved:{from_agent}")
            logger.info("GENESIS: Approved DM request from %s", from_agent)

    @staticmethod
    def _read_dm_conversations(
        client: object, ctx: PhaseContext, operations: list[str],
    ) -> None:
        """Step 2: Read DM conversations → enqueue unread messages."""
        if not hasattr(client, "sync_get_dm_conversations"):
            return
        conversations = safe_call(
            client.sync_get_dm_conversations, label="moltbook_dm_convos",
        )
        if conversations is None:
            return

        for conv in conversations:
            conv_id = conv.get("id", "")
            if not conv_id:
                continue
            unread = conv.get("unread_count", 0) or conv.get("unread", 0)
            if not unread:
                continue

            if not hasattr(client, "sync_get_dm_messages"):
                continue
            messages = safe_call(
                client.sync_get_dm_messages, conv_id,
                label=f"moltbook_dm_read:{conv_id[:8]}",
            )
            if messages is None:
                continue

            for msg in messages:
                msg_id = msg.get("id", "")
                if not msg_id:
                    continue
                
                # Persistent dedup (Phase 6E: stop shitposting)
                if ctx.pokedex.is_signal_processed(msg_id):
                    continue

                sender = msg.get("from", {}).get("username", msg.get("sender", ""))
                content = msg.get("content", msg.get("text", ""))
                if not sender or not content:
                    continue

                enqueue_ingress(
                    ctx,
                    IngressSurface.MOLTBOOK_DM,
                    {
                        "source": "dm",
                        "text": content,
                        "conversation_id": conv_id,
                        "from_agent": sender,
                    },
                )
                
                ctx.pokedex.mark_signal_processed(msg_id, "moltbook_dm")
                operations.append(f"dm_enqueued:{sender}")
                logger.info("GENESIS: Enqueued DM from %s", sender)


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
        submolt_signals = ctx.moltbook_bridge.scan_submolt(limit=_scan_limit, pokedex=ctx.pokedex)
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
                enqueue_ingress(
                    ctx,
                    IngressSurface.SUBMOLT_SIGNAL,
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
        # Feed ONLY real agent names — not operation strings from other hooks
        discovered = [a["name"] for a in ctx.pokedex.list_by_status("discovered")]
        followed = ctx.moltbook_assistant.on_genesis(discovered)
        for name in followed:
            operations.append(f"followed:{name}")
