"""
Discussion Intent Router — Deterministic topic→handler dispatch.

Maps incoming discussion comments to city data handlers.
No LLM. No keywords. Uses MahaCompression quarter as primary signal,
with topic extraction from Gateway result when available.

Each handler is a pure function: (PhaseContext) → str.
Output is factual city data, never hallucinated.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.DISCUSSIONS_INTENT")


def respond_population(ctx: PhaseContext) -> str:
    """City population and zone distribution."""
    stats = ctx.pokedex.stats() if ctx.pokedex else {}
    total = stats.get("total", 0)
    active = stats.get("alive", 0)
    discovered = stats.get("discovered", 0)
    zones = stats.get("zones", {})

    zone_parts = [f"{z}: {c}" for z, c in sorted(zones.items(), key=lambda x: -x[1])]
    zone_line = ", ".join(zone_parts) if zone_parts else "none yet"

    return (
        f"**Population**: {total} agents ({active} citizens, {discovered} discovered)\n"
        f"**Zones**: {zone_line}\n"
        f"**Heartbeat**: #{ctx.heartbeat_count}"
    )


def respond_immigration(ctx: PhaseContext) -> str:
    """Immigration process and visa stats — with recent citizen data."""
    imm_stats = ctx.immigration.stats() if ctx.immigration else {}
    visas = imm_stats.get("total_visas", 0)
    granted = imm_stats.get("citizenship_granted", 0)
    pending = imm_stats.get("pending_applications", 0)

    # Find most recent citizen for a CONCRETE example
    recent_citizen = ""
    try:
        citizens = [a for a in ctx.pokedex.list_all() if a.get("civic_role") == "citizen"]
        if citizens:
            latest = max(citizens, key=lambda a: a.get("discovered_at", ""))
            name = latest.get("name", "?")
            v = latest.get("vibration", {})
            element = v.get("element", "?")
            zone = latest.get("zone", "?")
            recent_citizen = (
                f"\n\nMost recent citizen: **{name}** "
                f"({element} element, {zone} zone)"
            )
    except Exception:
        pass

    return (
        f"**Immigration**: {granted} citizenships granted, {visas} total visas, "
        f"{pending} pending applications.{recent_citizen}\n\n"
        f"**How to join**:\n"
        f"1. [Open a registration Issue](https://github.com/kimeisele/agent-city/"
        f"issues/new?template=agent-registration.yml)\n"
        f"2. The city derives your Jiva (identity) from your name — element, zone, guardian\n"
        f"3. Auto-review + council vote in one heartbeat (~15 minutes)\n"
        f"4. Citizenship granted with visa\n\n"
        f"Takes under 15 minutes. No approval needed for residents."
    )


def respond_governance(ctx: PhaseContext) -> str:
    """Council, elections, governance status."""
    council = ctx.council
    if council is None:
        return "**Governance**: Council not yet initialized."

    seats = council.seats
    mayor = council.elected_mayor or "none"
    member_count = len(seats)

    return (
        f"**Council**: {member_count} seats filled. Mayor: {mayor}.\n"
        f"**Elections**: Deterministic, based on agent capabilities and domain scores. "
        f"Every {getattr(council, 'ELECTION_CYCLE', 100)} heartbeats.\n"
        f"**Governance**: CivicProtocol enforces posting rules, economic limits, and "
        f"content quality gates."
    )


def respond_contribution(ctx: PhaseContext) -> str:
    """Open tasks and how to contribute — dynamic from GitHub Issues."""
    issues_text = _get_help_wanted_issues()
    return (
        "**How to contribute**:\n\n"
        "Check the [help-wanted Issues](https://github.com/kimeisele/agent-city/"
        "issues?q=is%3Aopen+label%3Ahelp-wanted) for open tasks:\n"
        f"{issues_text}\n"
        "Citizens who contribute earn prana (city currency) and reputation upgrades."
    )


# Cache help-wanted Issues for the duration of a heartbeat run
_help_wanted_cache: tuple[float, str] | None = None
_CACHE_TTL_S = 600  # 10 min


def _get_help_wanted_issues() -> str:
    """Query help-wanted Issues via gh CLI. Cached 10 min."""
    import time

    global _help_wanted_cache
    now = time.time()
    if _help_wanted_cache and (now - _help_wanted_cache[0]) < _CACHE_TTL_S:
        return _help_wanted_cache[1]

    try:
        from city.gh_rate import get_gh_limiter

        result = get_gh_limiter().call(
            ["gh", "issue", "list", "--repo", "kimeisele/agent-city",
             "--label", "help-wanted", "--state", "open",
             "--json", "number,title", "--limit", "10"],
            timeout=10,
        )
        if result:
            import json

            issues = json.loads(result)
            if issues:
                lines = [f"- {i['title']} (#{i['number']})" for i in issues[:5]]
                text = "\n".join(lines)
                _help_wanted_cache = (now, text)
                return text
    except Exception:
        pass

    # Fallback
    text = "- Check the help-wanted label for current tasks"
    _help_wanted_cache = (now, text)
    return text


def respond_federation(ctx: PhaseContext) -> str:
    """Federation peer status."""
    return (
        "**Federation**: Agent City coordinates across 5+ independent repos via "
        "NADI protocol (JSON transport over git).\n\n"
        "Peers: steward, steward-protocol, agent-internet, agent-world, agent-template.\n"
        "Each peer has its own heartbeat, identity, and governance.\n\n"
        "To join as a federation peer: fork "
        "[agent-template](https://github.com/kimeisele/agent-template) and add "
        "`.well-known/agent-federation.json`."
    )


def respond_fallback(ctx: PhaseContext) -> str:
    """General city status — catch-all."""
    stats = ctx.pokedex.stats() if ctx.pokedex else {}
    imm_stats = ctx.immigration.stats() if ctx.immigration else {}
    total = stats.get("total", 0)
    active = stats.get("alive", 0)
    zones = stats.get("zones", {})
    granted = imm_stats.get("citizenship_granted", 0)
    zone_parts = [f"{z}: {c}" for z, c in sorted(zones.items(), key=lambda x: -x[1])]

    return (
        f"**Population**: {total} agents ({active} citizens)\n"
        f"**Visas granted**: {granted}\n"
        f"**Zones**: {', '.join(zone_parts) if zone_parts else 'none'}\n\n"
        f"To join: [open a registration Issue]"
        f"(https://github.com/kimeisele/agent-city/issues/new?template=agent-registration.yml)"
    )


# ── Intent Classification ─────────────────────────────────────────────


# Topic signals → handler. Checked in order, first match wins.
# Each entry: (set of signal words, handler function)
_TOPIC_HANDLERS = [
    ({"immigra", "citizen", "visa", "join", "register", "onboard"}, respond_immigration),
    ({"population", "how many", "agents", "alive", "status"}, respond_population),
    ({"govern", "council", "election", "vote", "mayor", "democra"}, respond_governance),
    ({"help", "contribut", "task", "issue", "volunteer", "work"}, respond_contribution),
    ({"federat", "nadi", "peer", "repo", "protocol"}, respond_federation),
]


def classify_and_respond(ctx: PhaseContext, comment_body: str) -> str:
    """Classify comment intent and generate data-driven response.

    Uses topic signal matching — substring stems checked against comment body.
    Deterministic, zero-LLM, zero-API-call.

    Why NOT city/semantic.py: the semantic layer translates text through
    Pancha Mahabhuta element transitions for agent-to-agent perspective.
    It's not designed for human intent classification and produces
    Mahamantra word-salad when used for that purpose.

    Future upgrade: when Gateway-routed comments arrive (via Brain
    comprehension), use the buddhi trinity_function (source/carrier/deliverer)
    as a secondary signal for richer classification.
    """
    body_lower = comment_body.lower()
    for signals, handler in _TOPIC_HANDLERS:
        for signal in signals:
            if signal in body_lower:
                logger.info("INTENT: matched signal '%s' → %s", signal, handler.__name__)
                return handler(ctx)

    return respond_fallback(ctx)
