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

from city.membrane import IngressSurface, enqueue_ingress, queue_item
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
SEED_THREAD_KEYS = ("welcome", "registry", "ideas", "city_log", "brainstream")


def _get_registry():
    """Get CityRegistry singleton (lazy import)."""
    from city.city_registry import get_city_registry

    return get_city_registry()


def _register_seed_threads(ctx: PhaseContext) -> None:
    """Push bridge-discovered seed threads into CityRegistry (transport → domain).

    Called AFTER seed_discussions() so newly created/recovered threads
    get registered as alive entities in the domain registry.
    """
    try:
        from city.city_registry import EntityKind

        registry = _get_registry()
        for key, number in ctx.discussions._seed_threads.items():
            registry.register(
                f"thread:{key}",
                EntityKind.THREAD,
                parent="seed",
                meta={"discussion_number": number, "key": key},
            )
    except Exception as exc:
        logger.debug("Seed thread registration skipped: %s", exc)


def _sync_registry_to_bridge(ctx: PhaseContext) -> None:
    """Populate bridge cache from CityRegistry (domain → transport).

    During a live process the registry may already know seed threads while the
    bridge cache is empty. This keeps transport caches aligned with the runtime
    registry before seed_discussions() runs.
    """
    try:
        from city.city_registry import EntityKind

        registry = _get_registry()
        alive_threads = registry.find_alive(EntityKind.THREAD)
        synced = 0
        for entry in alive_threads:
            if not entry.key.startswith("thread:"):
                continue
            thread_key = entry.key.removeprefix("thread:")
            if thread_key not in SEED_THREAD_KEYS:
                continue
            meta = registry.get_meta(entry.key)
            number = meta.get("discussion_number")
            if number and thread_key not in ctx.discussions._seed_threads:
                ctx.discussions._seed_threads[thread_key] = number
                synced += 1
        if synced:
            logger.info(
                "REGISTRY→BRIDGE: Synced %d seed threads from CityRegistry", synced,
            )
    except Exception as exc:
        logger.debug("Registry-to-bridge sync skipped: %s", exc)


def _check_seed_thread_health(ctx: PhaseContext, operations: list[str]) -> None:
    """Detect dead seed threads in CityRegistry, purge bridge cache for recreation.

    The registry is the authority. If a thread was registered but its
    cell is now dead (removed via registry.remove()), the bridge cache
    entry is purged so seed_discussions() will recreate it via transport.
    """
    try:
        registry = _get_registry()
        expected = [f"thread:{k}" for k in SEED_THREAD_KEYS]
        missing = registry.find_missing(expected)

        if not missing:
            return

        for registry_key in missing:
            thread_key = registry_key.removeprefix("thread:")
            if thread_key in ctx.discussions._seed_threads:
                old_num = ctx.discussions._seed_threads.pop(thread_key)
                logger.warning(
                    "RESILIENCE: Seed thread '%s' (#%d) missing from registry — purged for recreation",
                    thread_key, old_num,
                )
                operations.append(f"disc_resilience:purged:{thread_key}:#{old_num}")
    except Exception as exc:
        logger.debug("Seed thread health check skipped: %s", exc)


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

        # 8D: Purge expired claims from previous cycles (orphaned locks)
        try:
            registry = _get_registry()
            purged = registry.purge_expired_claims()
            if purged:
                operations.append(f"claims_purged:{purged}")
        except Exception as exc:
            logger.debug("Claim purge skipped: %s", exc)

        # 8C-1: Strangler pattern — registry is authority, bridge is cache
        # Step 1: Populate bridge cache from registry (domain → transport)
        _sync_registry_to_bridge(ctx)
        # Step 2: Detect dead entities and purge bridge cache
        _check_seed_thread_health(ctx, operations)

        # Step 3: Seed idempotent threads (transport creates missing ones)
        seeded = ctx.discussions.seed_discussions()
        for key, number in seeded.items():
            if number:
                operations.append(f"disc_seed:{key}:#{number}")

        # Step 4: Push newly discovered/created threads into registry
        _register_seed_threads(ctx)

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
                    # 12B: Prana income — human engaging with a thread we responded to
                    ts = ctx.thread_state.get(signal["number"])
                    if ts is not None and ts.response_count > 0:
                        # Thread had bot responses — human engagement = value
                        try:
                            from city.seed_constants import HUMAN_ENGAGEMENT_PRANA
                            # Find last responding agent from comment ledger
                            own_posts = ctx.thread_state.recent_own_posts(limit=1)
                            for post in own_posts:
                                if post.discussion_number == signal["number"] and post.author:
                                    ctx.pokedex.award_prana(
                                        post.author, HUMAN_ENGAGEMENT_PRANA,
                                        source=f"human_engagement:#{signal['number']}:{comment_author}",
                                    )
                                    operations.append(
                                        f"prana_engagement:{post.author}:#{signal['number']}"
                                    )
                                    break
                        except Exception:
                            pass

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
                        enqueue_ingress(
                            ctx,
                            IngressSurface.GITHUB_DISCUSSION,
                            {**enqueue_base, "direct_agent": mention},
                        )
                        operations.append(f"disc_mention:{mention}:#{signal['number']}")
                else:
                    # No mentions → general discussion enqueue
                    enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, enqueue_base)

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
            queue_item(ctx, {
                "source": "agent_intro",
                "text": f"New agent: {name}",
                "agent_name": name,
            })
            queued += 1
        if queued:
            logger.info("GENESIS: Queued %d agent introductions", queued)
