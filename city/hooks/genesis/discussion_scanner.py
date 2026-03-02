"""
GENESIS Hook: Discussion Scanner.

Scans GitHub Discussions for new comments, ingests into comment ledger,
extracts @mentions, spawns unknown agents, enqueues for KARMA processing.

Extracted from genesis.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.DISCUSSIONS")

# ── Brain Feedback Loop (Fix #2: HTML comment parsing) ────────────────

_BRAIN_JSON_PREFIX = "<!--BRAIN_JSON:"
_BRAIN_JSON_SUFFIX = "-->"


def _parse_brain_json(body: str) -> dict | None:
    """Extract hidden JSON from HTML comment in a [Brain] post."""
    if "[Brain]" not in body and "[Brain \U0001f9e0]" not in body:
        return None
    start = body.find(_BRAIN_JSON_PREFIX)
    if start == -1:
        return None
    start += len(_BRAIN_JSON_PREFIX)
    end = body.find(_BRAIN_JSON_SUFFIX, start)
    if end == -1:
        return None
    try:
        return json.loads(body[start:end])
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Brain feedback JSON parse failed: %s", e)
        return None


def _ingest_brain_feedback(ctx: PhaseContext, body: str) -> None:
    """Parse a [Brain] post and record it into brain_memory as external feedback."""
    if ctx.brain_memory is None:
        return
    parsed = _parse_brain_json(body)
    if parsed is None:
        return
    ctx.brain_memory.record_external(parsed)
    logger.debug(
        "Brain feedback ingested: heartbeat=%s intent=%s",
        parsed.get("heartbeat", "?"),
        parsed.get("intent", "?"),
    )


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


class DiscussionScannerHook(BasePhaseHook):
    """Scan GitHub Discussions: seed threads, ingest comments, extract mentions."""

    @property
    def name(self) -> str:
        return "discussion_scanner"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 60  # after moltbook/federation, before agent intros

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.discussions is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.discussions_inbox import extract_mentions

        # Seed idempotent threads on first run
        seeded = ctx.discussions.seed_discussions()
        for key, number in seeded.items():
            if number:
                operations.append(f"disc_seed:{key}:#{number}")

        disc_signals = ctx.discussions.scan()
        for signal in disc_signals:
            operations.append(f"discussion:{signal['number']}")

            # New threads → create discussion mission
            if signal.get("is_new") and ctx.sankalpa is not None:
                from city.missions import create_discussion_mission

                create_discussion_mission(
                    ctx, signal["number"], signal.get("title", ""), "observe",
                )

            for comment in signal.get("new_comments", []):
                comment_id = comment.get("id", "")
                comment_author = comment.get("author", "")
                body = comment.get("body", "")
                is_own = ctx.discussions.is_own_comment(comment_author)
                is_edited = comment.get("edited", False)

                # Ingest ALL comments into the ledger — no front-door discrimination
                if ctx.thread_state is not None and comment_id:
                    if is_edited:
                        # 6C-3/6C-7: Re-ingest edited comment for re-processing
                        entry = ctx.thread_state.reingest_comment(comment_id, body)
                        if entry is not None:
                            operations.append(
                                f"disc_edit_reingested:{comment_id[:12]}:#{signal['number']}"
                            )
                    else:
                        entry = ctx.thread_state.ingest_comment(
                            comment_id,
                            signal["number"],
                            comment_author,
                            body,
                            is_own=is_own,
                        )
                    if entry is None:
                        continue  # already ingested and unchanged

                # Self-posts: parse Brain feedback, but don't enqueue for response
                if is_own:
                    _ingest_brain_feedback(ctx, body)
                    continue

                # External comment: update thread lifecycle + enqueue for processing
                if ctx.thread_state is not None:
                    ctx.thread_state.record_human_comment(
                        signal["number"],
                        comment_author,
                        title=signal.get("title", ""),
                        category="",
                    )

                mentions = extract_mentions(body)

                # Build enqueue payload
                enqueue_base = {
                    "source": "discussion",
                    "text": body,
                    "from_agent": comment_author,
                    "discussion_number": signal["number"],
                    "discussion_title": signal.get("title", ""),
                    "comment_id": comment_id,
                }

                if mentions:
                    # @mention routing: one enqueue per mentioned agent
                    for mention in mentions:
                        existing = ctx.pokedex.get(mention)
                        if not existing:
                            ctx.pokedex.discover(mention, moltbook_profile={})
                            operations.append(f"disc_spawn:{mention}")
                            logger.info(
                                "GENESIS: Discussion @mention spawned agent %s",
                                mention,
                            )
                        _enqueue_item(ctx, {**enqueue_base, "direct_agent": mention})
                        operations.append(f"disc_mention:{mention}:#{signal['number']}")
                else:
                    # No mentions → general discussion enqueue
                    _enqueue_item(ctx, enqueue_base)

                # Mark as enqueued in ledger
                if ctx.thread_state is not None and comment_id:
                    ctx.thread_state.mark_enqueued(comment_id)


class AgentIntroHook(BasePhaseHook):
    """Drip-feed agent introductions to Discussions."""

    @property
    def name(self) -> str:
        return "agent_intro"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 70  # after discussion scanner

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.discussions is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from config import get_config

        max_intros = get_config().get("discussions", {}).get(
            "max_agent_comments_per_cycle", 3,
        )
        all_agents = ctx.pokedex.list_all()
        queued = 0
        for agent in all_agents:
            if queued >= max_intros:
                break
            name = agent.get("name", "")
            if not name:
                continue
            if ctx.pokedex.has_asset(name, "word_token", "introduced"):
                continue
            _enqueue_item(ctx, {
                "source": "agent_intro",
                "text": f"New agent: {name}",
                "agent_name": name,
            })
            queued += 1
        if queued:
            logger.info("GENESIS: Queued %d agent introductions", queued)
