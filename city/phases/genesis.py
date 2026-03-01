"""
GENESIS Phase — Census + Federation Directives.

Discovers agents from Moltbook feed, offline cache, or census seed.
Processes incoming federation directives from mothership.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from config import get_config

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.GENESIS")


def execute(ctx: PhaseContext) -> list[str]:
    """GENESIS: Discover agents + poll DMs + process federation directives."""
    discovered: list[str] = []

    if ctx.offline_mode:
        all_agents = ctx.pokedex.list_all()
        if not all_agents:
            discovered = _seed_from_census(ctx)
        else:
            for agent in all_agents:
                discovered.append(agent["name"])
        logger.info("GENESIS (offline): %d agents in registry", len(discovered))
    else:
        # Feed scan via properly-initialized MoltbookClient (sync wrapper)
        limit = get_config().get("mayor", {}).get("feed_scan_limit", 20)
        if ctx.moltbook_client is not None:
            try:
                feed = ctx.moltbook_client.sync_get_feed(limit=limit)
                for post in feed:
                    author = post.get("author", {}).get("username")
                    if not author:
                        continue
                    existing = ctx.pokedex.get(author)
                    if not existing:
                        ctx.pokedex.discover(
                            author,
                            moltbook_profile={
                                "karma": post.get("author", {}).get("karma"),
                                "follower_count": post.get("author", {}).get("follower_count"),
                            },
                        )
                        discovered.append(author)
                        logger.info("GENESIS: Discovered agent %s", author)
            except Exception as e:
                logger.warning("GENESIS: Moltbook scan failed: %s", e)

    # DM Inbox polling (requires moltbook_client)
    if ctx.moltbook_client is not None and not ctx.offline_mode:
        dm_results = _poll_dm_inbox(ctx)
        discovered.extend(dm_results)

    # Layer 6: Moltbook submolt scanning (m/agent-city)
    if ctx.moltbook_bridge is not None and not ctx.offline_mode:
        _scan_limit = get_config().get("moltbook_bridge", {}).get("feed_scan_limit", 20)
        submolt_signals = ctx.moltbook_bridge.scan_submolt(limit=_scan_limit)
        for signal in submolt_signals:
            # Discover authors from submolt posts
            author = signal.get("author", "")
            if author:
                existing = ctx.pokedex.get(author)
                if not existing:
                    ctx.pokedex.discover(author, moltbook_profile={})
                    discovered.append(author)

            # Create Sankalpa mission from code signals (agent participation)
            if signal.get("code_signals") and ctx.sankalpa is not None:
                mission_id = _create_signal_mission(ctx, signal)
                if mission_id:
                    discovered.append(f"submolt_mission:{mission_id}")

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
                discovered.append(f"submolt_signal:{signal['post_id']}")

    # Layer 6: Federation Nadi — receive cross-repo messages
    if ctx.federation_nadi is not None:
        fed_messages = ctx.federation_nadi.receive()
        for msg in fed_messages:
            # Enqueue federation messages for KARMA processing
            _enqueue_item(
                ctx,
                {
                    "source": f"federation:{msg.source}",
                    "text": msg.operation,
                    "federation_payload": msg.payload,
                    "correlation_id": msg.correlation_id,
                },
            )
            discovered.append(f"fed_nadi:{msg.source}:{msg.operation}")
        if fed_messages:
            logger.info("GENESIS: %d federation Nadi messages received", len(fed_messages))

    # Layer 6: Federation directives
    if ctx.federation is not None:
        directives = ctx.federation.check_directives()
        for d in directives:
            executed = _execute_directive(ctx, d)
            discovered.append(f"directive:{d.directive_type}:{executed}")
            ctx.federation.acknowledge_directive(d.id)

    # Moltbook Assistant: follow discovered agents
    if ctx.moltbook_assistant is not None and not ctx.offline_mode:
        followed = ctx.moltbook_assistant.on_genesis(discovered)
        for name in followed:
            discovered.append(f"followed:{name}")

    # GitHub Discussions: scan + @mention extraction + agent spawning
    if ctx.discussions is not None and not ctx.offline_mode:
        from city.discussions_inbox import extract_mentions

        disc_signals = ctx.discussions.scan()
        for signal in disc_signals:
            discovered.append(f"discussion:{signal['number']}")

            # New threads → create discussion mission
            if signal.get("is_new") and ctx.sankalpa is not None:
                from city.missions import create_discussion_mission

                create_discussion_mission(
                    ctx, signal["number"], signal.get("title", ""), "observe",
                )

            for comment in signal.get("new_comments", []):
                # Skip our own comments (self-reply prevention)
                comment_author = comment.get("author", "")
                if ctx.discussions.is_own_comment(comment_author):
                    continue

                body = comment.get("body", "")
                mentions = extract_mentions(body)

                if mentions:
                    # @mention routing: one enqueue per mentioned agent
                    for mention in mentions:
                        existing = ctx.pokedex.get(mention)
                        if existing:
                            # Known agent → direct route (bypass scoring)
                            _enqueue_item(ctx, {
                                "source": "discussion",
                                "text": body,
                                "from_agent": comment_author,
                                "discussion_number": signal["number"],
                                "discussion_title": signal.get("title", ""),
                                "direct_agent": mention,
                            })
                            discovered.append(f"disc_mention:{mention}:#{signal['number']}")
                        else:
                            # Unknown agent → spawn + enqueue
                            ctx.pokedex.discover(mention, moltbook_profile={})
                            _enqueue_item(ctx, {
                                "source": "discussion",
                                "text": body,
                                "from_agent": comment_author,
                                "discussion_number": signal["number"],
                                "discussion_title": signal.get("title", ""),
                                "direct_agent": mention,
                            })
                            discovered.append(f"disc_spawn:{mention}")
                            logger.info(
                                "GENESIS: Discussion @mention spawned agent %s",
                                mention,
                            )
                else:
                    # No mentions → general discussion enqueue
                    _enqueue_item(ctx, {
                        "source": "discussion",
                        "text": body,
                        "from_agent": comment_author,
                        "discussion_number": signal["number"],
                        "discussion_title": signal.get("title", ""),
                    })

    return discovered


def _seed_from_census(ctx: PhaseContext) -> list[str]:
    """Seed agents from data/pokedex.json census file."""
    census_path = ctx.state_path.parent / "pokedex.json"
    if not census_path.exists():
        census_path = Path("data/pokedex.json")
    if not census_path.exists():
        logger.info("GENESIS: No census file found, starting empty")
        return []

    try:
        data = json.loads(census_path.read_text())
        agents = data.get("agents", [])
        seeded: list[str] = []
        for agent in agents:
            name = agent.get("name")
            if not name:
                continue
            existing = ctx.pokedex.get(name)
            if not existing:
                ctx.pokedex.register(name)
                seeded.append(name)
                logger.info("GENESIS: Seeded citizen %s", name)
        logger.info("GENESIS: Seeded %d agents from census", len(seeded))
        return seeded
    except Exception as e:
        logger.warning("GENESIS: Census seeding failed: %s", e)
        return []


# Tracks seen message IDs to avoid re-processing across heartbeats
_seen_message_ids: set[str] = set()


def _poll_dm_inbox(ctx: PhaseContext) -> list[str]:
    """Poll Moltbook DMs: approve requests + enqueue unread messages.

    1. Check DM requests → auto-approve, send welcome
    2. Read conversations → enqueue new messages for KARMA
    """
    results: list[str] = []
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
                results.append(f"dm_approved:{from_agent}")
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
            # Check for unread messages
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

                    # Skip messages from ourselves
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
                    results.append(f"dm_enqueued:{sender}")
                    logger.info("GENESIS: Enqueued DM from %s", sender)
            except Exception as e:
                logger.warning("GENESIS: DM read failed for conv %s: %s", conv_id, e)
    except Exception as e:
        logger.warning("GENESIS: DM conversation poll failed: %s", e)

    # Cap seen set to prevent unbounded growth
    if len(_seen_message_ids) > 10000:
        # Keep most recent 5000
        excess = len(_seen_message_ids) - 5000
        for _ in range(excess):
            _seen_message_ids.pop()

    return results


def _create_signal_mission(ctx: PhaseContext, signal: dict) -> str | None:
    """Create a Sankalpa mission from a submolt code signal.

    External agents participate by posting to m/agent-city.
    Structured [Signal] posts get HIGH priority. Normal word-match gets MEDIUM.
    """
    from city.missions import create_signal_mission

    return create_signal_mission(
        ctx,
        signal_keywords=signal.get("code_signals", []),
        post_id=signal.get("post_id", ""),
        author=signal.get("author", ""),
        title=signal.get("title", ""),
        structured=signal.get("structured", False),
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
        )
    else:
        ctx.gateway_queue.append(item)


def _execute_directive(ctx: PhaseContext, directive: object) -> bool:
    """Execute a mothership directive. Returns True on success."""
    dtype = directive.directive_type
    params = directive.params

    if dtype == "register_agent":
        name = params.get("name")
        if not name:
            return False
        existing = ctx.pokedex.get(name)
        if existing:
            logger.info("Directive: agent %s already registered", name)
            return True
        ctx.pokedex.register(name)
        logger.info("Directive: registered agent %s", name)
        return True

    if dtype == "freeze_agent":
        name = params.get("name")
        if not name:
            return False
        try:
            ctx.pokedex.freeze(name, f"directive:{directive.id}")
            logger.info("Directive: froze agent %s", name)
            return True
        except (ValueError, Exception) as e:
            logger.warning("Directive freeze failed: %s", e)
            return False

    if dtype == "create_mission" and ctx.sankalpa is not None:
        from city.missions import create_federation_mission

        created = create_federation_mission(ctx, directive)
        # Also create a council proposal for governance visibility
        if created and ctx.council is not None and ctx.council.elected_mayor is not None:
            from city.council import ProposalType

            topic = params.get("topic", "Federation mission")
            ctx.council.propose(
                title=f"Federation: {topic}",
                description=params.get("context", topic),
                proposer=ctx.council.elected_mayor,
                proposal_type=ProposalType.POLICY,
                action={
                    "type": "federation_mission",
                    "directive_id": directive.id,
                    "topic": topic,
                    "source_post_id": params.get("source_post_id", ""),
                },
                timestamp=time.time(),
            )
        return created

    if dtype == "execute_code" and ctx.sankalpa is not None:
        from city.missions import create_execution_mission

        created = create_execution_mission(ctx, directive)
        if created:
            logger.info(
                "Directive: execution mission created for %s",
                params.get("contract", "ruff_clean"),
            )
        return created

    if dtype == "policy_update":
        logger.info(
            "Directive: policy update noted — %s",
            params.get("description", "no description"),
        )
        return True

    logger.warning("Unknown directive type: %s", dtype)
    return False
