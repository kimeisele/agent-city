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
from pathlib import Path

from config import get_config

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.GENESIS")


def execute(ctx: PhaseContext) -> list[str]:
    """GENESIS: Discover agents + process federation directives."""
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
        try:
            from vibe_core.mahamantra.adapters.moltbook import MoltbookClient
            client = MoltbookClient()
            limit = get_config().get("mayor", {}).get("feed_scan_limit", 20)
            feed = client.get_feed(limit=limit)

            for post in feed:
                author = post.get("author", {}).get("username")
                if not author:
                    continue
                existing = ctx.pokedex.get(author)
                if not existing:
                    ctx.pokedex.discover(author, moltbook_profile={
                        "karma": post.get("author", {}).get("karma"),
                        "follower_count": post.get("author", {}).get("follower_count"),
                    })
                    discovered.append(author)
                    logger.info("GENESIS: Discovered agent %s", author)
        except Exception as e:
            logger.warning("GENESIS: Moltbook scan failed: %s", e)

    # Layer 6: Federation directives
    if ctx.federation is not None:
        directives = ctx.federation.check_directives()
        for d in directives:
            executed = _execute_directive(ctx, d)
            discovered.append(f"directive:{d.directive_type}:{executed}")
            ctx.federation.acknowledge_directive(d.id)

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
        return create_federation_mission(ctx, directive)

    if dtype == "policy_update":
        logger.info(
            "Directive: policy update noted — %s",
            params.get("description", "no description"),
        )
        return True

    logger.warning("Unknown directive type: %s", dtype)
    return False
