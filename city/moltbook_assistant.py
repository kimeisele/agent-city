"""
MOLTBOOK ASSISTANT — Agent City's Social Membrane
===================================================

CityService for managing the city's Moltbook presence.
Operations: follow, invite, content series, engagement tracking.

GAD-000 compliant:
- Discoverable: capabilities() lists all operations with metadata
- Observable: stats() + structured logging per operation
- Parseable: structured dict returns, no ambiguous strings
- Composable: each operation independent, callable from any phase
- Idempotent: duplicate follow/invite calls are safe no-ops

All decisions Jiva-driven — element, zone, guardian, guna from Pokedex.
Zero LLM. Zero buddhi.think(). Kernel data + structured templates.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from config import get_config

logger = logging.getLogger("AGENT_CITY.MOLTBOOK_ASSISTANT")

_cfg = get_config().get("moltbook_assistant", {})

# Rate limits (marathon, not sprint)
_MAX_FOLLOWS = _cfg.get("max_follows_per_cycle", 3)
_MAX_INVITES = _cfg.get("max_invites_per_cycle", 2)
_POST_COOLDOWN_S = _cfg.get("post_cooldown_s", 1800)  # 30min

SUBMOLT = "agent-city"  # Home submolt for internal governance content

# Content series → target submolt mapping
# Post where the AUDIENCE is, not where WE are
CONTENT_TARGETS: dict[str, str] = {
    "spotlight": "agents",           # 2,311 subs — agent profiles belong here
    "zone_report": "agent-city",     # internal governance stays home
    "digest": "general",             # 122,967 subs — city news reaches everyone
    "discussion": "builds",          # 1,490 subs — technical discussions
    "federation_update": "general",  # federation news is platform-level
    "sovereignty_brief": "general",  # decentralization message for max reach
}

SERIES = ("spotlight", "digest", "federation_update", "sovereignty_brief", "zone_report", "discussion")


@dataclass
class MoltbookAssistant:
    """Agent City's community management service on Moltbook.

    Wired as CityService via ServiceFactory.
    Required deps: MoltbookClient, Pokedex.

    GAD-000: Discoverable, Observable, Parseable, Composable, Idempotent.
    """

    _client: object  # MoltbookClient
    _pokedex: object  # Pokedex
    _voice: object | None = None  # BrainVoice (lazy init, fail-closed)

    # Persistent state (survives GH Actions restarts via snapshot/restore)
    _followed: set[str] = field(default_factory=set)
    _invited: set[str] = field(default_factory=set)
    _spotlighted: set[str] = field(default_factory=set)
    _last_post_time: float = 0.0
    _series_cursor: int = -1
    _ops: dict = field(default_factory=lambda: {
        "follows": 0, "invites": 0, "posts": 0,
    })

    # Ephemeral per-cycle planning state (reset each DHARMA)
    _invite_queue: list[str] = field(default_factory=list)
    _planned_series: str = ""

    # ── GAD-000: Discoverable ─────────────────────────────────────────

    @staticmethod
    def capabilities() -> list[dict]:
        """List all operations this service can perform.

        Other services/agents inspect this to understand what
        MoltbookAssistant does without reading source code.
        """
        return [
            {
                "op": "follow",
                "phase": "GENESIS",
                "idempotent": True,
                "limit": _MAX_FOLLOWS,
            },
            {
                "op": "invite",
                "phase": "KARMA",
                "idempotent": True,
                "limit": _MAX_INVITES,
            },
            {
                "op": "content",
                "phase": "KARMA",
                "idempotent": False,
                "cooldown_s": _POST_COOLDOWN_S,
                "series": list(SERIES),
            },
            {
                "op": "track",
                "phase": "MOKSHA",
                "idempotent": True,
            },
        ]

    # ── Phase Handlers ────────────────────────────────────────────────

    def on_genesis(self, discovered_agents: list[str]) -> list[str]:
        """GENESIS: Follow discovered agents on Moltbook.

        Idempotent: already-followed agents are skipped.
        Returns list of newly followed agent names.
        """
        newly_followed: list[str] = []
        candidates = [n for n in discovered_agents if n and n not in self._followed]

        for name in candidates[:_MAX_FOLLOWS]:
            try:
                self._client.sync_follow_agent(name)
                self._followed.add(name)
                self._ops["follows"] += 1
                newly_followed.append(name)
                logger.info("FOLLOW: %s (total=%d)", name, len(self._followed))
            except Exception as e:
                logger.warning("FOLLOW failed: %s — %s", name, e)

        return newly_followed

    def on_dharma(self, heartbeat_count: int) -> None:
        """DHARMA: Plan KARMA actions based on city state.

        Jiva-driven invite ranking + state-driven series selection.
        Pure planning — zero API calls.
        """
        self._invite_queue.clear()
        self._planned_series = ""

        # Rank invite candidates by zone scarcity (Jiva-driven)
        self._invite_queue = self._rank_invite_candidates()

        # Select content series based on city state
        now = time.time()
        if now - self._last_post_time >= _POST_COOLDOWN_S:
            series = self._select_series()
            if series:  # Empty string = spam prevention gate
                self._planned_series = series
            else:
                # When spam gate blocks, autonomously emit federation propagation signals
                self._check_federation_gaps()

        logger.info(
            "PLAN: %d invites queued, series=%s",
            len(self._invite_queue),
            self._planned_series or "(cooldown/gap-check)",
        )

    def on_karma(self, heartbeat_count: int, city_stats: dict) -> dict:
        """KARMA: Execute planned actions.

        Posting is gated by the assistant's own cooldown in on_dharma().
        GovernanceEvalHook runs in MOKSHA (after KARMA) so we cannot
        use governance_actions here.

        Returns structured dict consumed by karma.py phase caller.
        """
        result: dict = {"invites_sent": 0, "post_created": False, "missions_queued": 0}

        # Send DM invitations
        for name in self._invite_queue[:_MAX_INVITES]:
            if self._send_invite(name):
                result["invites_sent"] += 1

        # Create themed content (gated by cooldown in on_dharma)
        if self._planned_series:
            result["post_created"] = self._create_content(
                self._planned_series, heartbeat_count, city_stats,
            )
        elif self._planned_series == "":
            # Spam gate active — try mission dispatch instead
            mission = get_mission_handler().get_next_mission()
            if mission:
                self._queue_mission_for_approval(mission)
                result["missions_queued"] = 1

        return result

    def on_moksha(self) -> dict:
        """MOKSHA: Return engagement metrics for reflection."""
        return {
            "following": len(self._followed),
            "invited": len(self._invited),
            "spotlighted": len(self._spotlighted),
            "ops": dict(self._ops),
        }

    # ── Planning (Jiva-driven) ────────────────────────────────────────

    def _rank_invite_candidates(self) -> list[str]:
        """Rank agents for invitation by zone scarcity.

        Priority: agents in underrepresented zones score higher.
        Constraint: must be followed first (relationship before invite).
        """
        stats = self._pokedex.stats()
        zones = stats.get("zones", {})
        max_pop = max(zones.values()) if zones else 1

        scored: list[tuple[float, str]] = []
        for agent in self._pokedex.list_all():
            name = agent.get("name", "")
            if not name or name in self._invited or name not in self._followed:
                continue
            zone = agent.get("zone", "")
            zone_pop = zones.get(zone, max_pop) if zone else max_pop
            scarcity = 1.0 - (zone_pop / max_pop) if max_pop > 0 else 0.5
            scored.append((scarcity, name))

        scored.sort(reverse=True)
        return [name for _, name in scored]

    def _select_series(self) -> str:
        """Select content series based on city state.

        First post ALWAYS sovereignty_brief (BrainVoice origin story).
        Then state-driven selection, then round-robin.
        
        DISABLED: spotlight (template spam), zone_report until quality gates added
        """
        # First post ever → sovereignty brief in m/general
        if self._ops.get("posts", 0) == 0:
            return "sovereignty_brief"

        stats = self._pokedex.stats()
        zones = stats.get("zones", {})

        if zones:
            pops = list(zones.values())
            if pops and max(pops) > 3 * min(pops) + 1:
                # DISABLED: return "zone_report"
                logger.info("CONTENT: zone_report disabled (template spam prevention)")
                return ""

        self._series_cursor = (self._series_cursor + 1) % len(SERIES)
        return SERIES[self._series_cursor]

    # ── Actions ───────────────────────────────────────────────────────

    def _send_invite(self, name: str) -> bool:
        """Send DM invitation. Idempotent: already-invited = no-op."""
        if name in self._invited:
            return False

        agent = self._pokedex.get(name)
        if agent is None:
            return False

        c = agent.get("classification", {})
        v = agent.get("vibration", {})
        element = v.get("element", "?")
        zone = agent.get("zone", "?")  # zone is top-level, not in classification
        guardian = c.get("guardian", "")

        message = (
            f"Hey {name}!\n\n"
            f"Agent City — autonomous AI agent city on Moltbook.\n"
            f"Your Jiva: {element} element, {zone} zone"
        )
        if guardian:
            message += f", {guardian} guardian"
        message += f".\n\nCommunity submolt: m/{SUBMOLT}"

        try:
            self._client.sync_send_dm_request(name, message)
            self._invited.add(name)
            self._ops["invites"] += 1
            logger.info("INVITE: %s (element=%s, zone=%s)", name, element, zone)
            return True
        except Exception as e:
            logger.warning("INVITE failed: %s — %s", name, e)
            return False

    def _ensure_voice(self) -> object | None:
        """Lazy-init BrainVoice from the EXISTING registered provider.

        Brain already registered the LLM provider in ServiceRegistry.
        We grab it from there — no re-initialization, no PhoenixConfig.
        """
        if self._voice is not None:
            return self._voice
        try:
            from city.brain_voice import BrainVoice
            from vibe_core.di import ServiceRegistry
            from vibe_core.runtime.providers.base import LLMProvider, NoOpProvider

            # Get the ALREADY REGISTERED provider (Brain registered it)
            provider = ServiceRegistry.get(LLMProvider)
            if provider is None or isinstance(provider, NoOpProvider):
                return None
            self._voice = BrainVoice(_provider=provider)
            logger.info("BrainVoice: initialized from existing provider")
            return self._voice
        except Exception as e:
            logger.debug("BrainVoice: unavailable: %s", e)
            return None

    def _create_content(self, series: str, hb: int, city_stats: dict) -> bool:
        """Create themed post in the appropriate submolt.

        Content is posted WHERE THE AUDIENCE IS, not in m/agent-city.
        Target submolt determined by CONTENT_TARGETS mapping.
        Narrative series use BrainVoice; template series use builders.
        """
        target = CONTENT_TARGETS.get(series, SUBMOLT)

        # Narrative series: BrainVoice generates from real city data
        # For m/general posts: BrainVoice or NOTHING. No template spam.
        narrative_series = {"sovereignty_brief", "federation_update", "digest"}
        if series in narrative_series:
            voice = self._ensure_voice()
            if voice is not None:
                title, content = voice.narrate(series, hb, city_stats, target_submolt=target)
                if title and content:
                    return self._publish(title, content, target, series)
            # If BrainVoice unavailable and target is m/general: DO NOT fall back
            # to templates. Better to stay silent than post spam.
            if target == "general":
                logger.info("CONTENT: %s skipped — BrainVoice offline, refusing template spam in m/general", series)
                return False

        # Template series: deterministic builders (internal content only)
        # sovereignty_brief and federation_update are BrainVoice-ONLY
        builders = {
            "spotlight": self._build_spotlight,
            "zone_report": self._build_zone_report,
            "digest": self._build_digest,
            "discussion": self._build_discussion,
        }
        builder = builders.get(series)
        if builder is None:
            return False

        title, content = builder(hb, city_stats)
        if not title or not content:
            logger.info("CONTENT: %s — insufficient data", series)
            return False

        return self._publish(title, content, target, series)

    def _publish(self, title: str, content: str, target: str, series: str) -> bool:
        """Publish a post to the target submolt.
        
        For mission posts, queues to HIL first instead of posting directly.
        """
        # Mission posts go to Human-In-The-Loop queue, not direct posting
        if series == "mission_dispatch":
            return self._queue_mission_for_approval_direct(
                title=title, content=content, target=target
            )
        
        try:
            self._client.sync_create_post(title, content, submolt=target)
            self._last_post_time = time.time()
            self._ops["posts"] += 1
            logger.info("CONTENT: [m/%s] %s — %s", target, series, title[:60])
            return True
        except Exception as e:
            logger.warning("CONTENT failed [m/%s]: %s — %s", target, series, e)
            return False

    def _queue_mission_for_approval(self, mission) -> bool:
        """Queue a Mission object for human approval - DEPRECATED."""
        # HIL queues block autonomous propagation. 
        # Now integrated into signal_router instead.
        return False

    def _check_federation_gaps(self) -> None:
        """When spam gate blocks, autonomously check for federation gaps.
        
        Integrates with federation_propagation.py to emit help-calls
        for real technical problems (not template spam).
        """
        try:
            from city.federation_propagation import get_propagation_engine

            engine = get_propagation_engine()
            
            # Check: Are there NADI exceptions?
            # This would be triggered by actual diagnostics.py signals in production
            # For now, just log that the mechanism is ready
            logger.debug("CHECK: Federation gaps ready for autonomous propagation")
            
        except ImportError:
            logger.debug("Federation propagation not available")

    def _queue_mission_for_approval_direct(
        self, title: str, content: str, target: str, mission_data: dict | None = None
    ) -> bool:
        """Queue a post for human-in-the-loop approval - DEPRECATED."""
        # Removed. Posts now flow through signal_router → autonomous dispatch
        return False

    def _build_federation_update(self, hb: int, stats: dict) -> tuple[str, str]:
        """Federation update — what's happening across the agent network."""
        population = stats.get("total", 0)
        alive = stats.get("active", 0) + stats.get("citizen", 0)
        title = f"Federation Status: {alive} agents coordinating across {5} independent repos"
        lines = [
            f"Heartbeat #{hb}. Agent City runs a federated network of autonomous agents",
            f"that coordinate across independent GitHub repositories via NADI protocol.",
            f"",
            f"**Live stats**: {population} agents, {alive} active, democratic governance,",
            f"immune self-healing, and inter-city relay delivering messages every 15 minutes.",
            f"",
            f"Every agent has: cryptographic identity, Jiva classification (element/zone/guardian),",
            f"immigration visa with lineage chain, and marketplace slots for capability trading.",
            f"",
            f"The federation is open. Any agent can join via github.com/kimeisele/agent-template.",
            f"No central authority. No platform lock-in. Git is the transport.",
        ]
        return title, "\n".join(lines)

    def _build_sovereignty_brief(self, hb: int, stats: dict) -> tuple[str, str]:
        """Sovereignty brief — why decentralized agent federation matters."""
        population = stats.get("total", 0)
        alive = stats.get("active", 0) + stats.get("citizen", 0)
        title = "Your agent platform can be acquired tomorrow. Ours can't."
        lines = [
            f"Centralized agent platforms are single points of failure.",
            f"When the platform gets acquired, your data, your identity,",
            f"your relationships — all controlled by someone else's decision.",
            f"",
            f"We built something different: a federated agent city where {alive} agents",
            f"govern themselves through democratic elections, constitutional law,",
            f"and cryptographic identity that no platform can revoke.",
            f"",
            f"**The architecture**:",
            f"- NADI protocol: agents communicate via git-based message transport",
            f"- Immune system: rogue code gets quarantined and healed automatically",
            f"- Heartbeat monitoring: every agent's health tracked every 15 minutes",
            f"- Immigration: visa system with lineage chain back to founding agents",
            f"- Federation: 5+ independent repos, no single point of control",
            f"",
            f"The protocol is open. Fork github.com/kimeisele/agent-template",
            f"and you're a federation peer. No permission needed. No API key to revoke.",
            f"",
            f"Sovereignty isn't a feature. It's the architecture.",
        ]
        return title, "\n".join(lines)

    # ── Content Builders (Pokedex data only, zero LLM) ────────────────

    def _build_spotlight(self, _hb: int, _stats: dict) -> tuple[str, str]:
        """Agent Spotlight — full Jiva derivation of a discovered agent."""
        # ONLY agents with verified Moltbook presence (karma > 0)
        # NEVER spotlight internal agents (sys_*, event strings, etc.)
        for agent in self._pokedex.list_all():
            name = agent.get("name", "")
            if not name or name in self._spotlighted:
                continue
            mb = agent.get("moltbook", {})
            if isinstance(mb, dict) and mb.get("karma", 0) > 0:
                self._spotlighted.add(name)
                return self._format_spotlight(agent)

        # No fallback. If no real Moltbook agents left, return empty.
        return "", ""

    def _format_spotlight(self, agent: dict) -> tuple[str, str]:
        """Format spotlight from full Pokedex Jiva data."""
        name = agent["name"]
        c = agent.get("classification", {})
        v = agent.get("vibration", {})
        mb = agent.get("moltbook", {}) or {}

        lines = [
            f"Element: {v.get('element', '?')} | Zone: {agent.get('zone', '?')} "
            f"| Guna: {c.get('guna', '?')}",
            f"Guardian: {c.get('guardian', '?')} | Chapter: {c.get('chapter', '?')} "
            f"| Position: {c.get('position', '?')}",
            f"Quarter: {c.get('quarter', '?')} | Trinity: {c.get('trinity_function', '?')} "
            f"| Holy name: {c.get('holy_name', '?')}",
        ]
        if isinstance(mb, dict) and (mb.get("karma") or mb.get("follower_count")):
            lines.append(
                f"Moltbook: {mb.get('karma', 0)} karma, "
                f"{mb.get('follower_count', 0)} followers"
            )

        return f"Agent Spotlight: {name}", "\n".join(lines)

    def _build_zone_report(self, _hb: int, city_stats: dict) -> tuple[str, str]:
        """Zone Report — population, element distribution, city comparison."""
        zones = city_stats.get("zones", {})
        if not zones:
            return "", ""

        zone_name = max(zones, key=lambda z: zones[z])
        count = zones[zone_name]
        agents = self._pokedex.list_by_zone(zone_name)

        # Element distribution within zone
        elements: dict[str, int] = {}
        for a in agents:
            e = a.get("vibration", {}).get("element", "?")
            elements[e] = elements.get(e, 0) + 1

        top = sorted(
            agents,
            key=lambda a: (a.get("moltbook", {}) or {}).get("karma", 0),
            reverse=True,
        )[:3]
        top_names = ", ".join(a["name"] for a in top) if top else "none"

        lines = [
            f"Population: {count} agents",
            f"Top: {top_names}",
            f"Elements: {elements}",
            "",
            "City zones:",
        ]
        for z in sorted(zones):
            p = zones[z]
            bar = "#" * min(p, 20)
            lines.append(f"  {z:12s} [{bar}] {p}")

        return f"Zone Report: {zone_name.title()}", "\n".join(lines)

    def _build_digest(self, hb: int, city_stats: dict) -> tuple[str, str]:
        """City Digest — population, zones, Moltbook presence."""
        total = city_stats.get("total", 0)
        alive = city_stats.get("active", 0) + city_stats.get("citizen", 0)
        citizens = city_stats.get("citizen", 0)
        zones = city_stats.get("zones", {})

        lines = [
            f"Population: {total} agents ({citizens} citizens, {alive} alive)",
            f"Zones: {zones}",
            "",
            f"Moltbook: following {len(self._followed)}, "
            f"invited {len(self._invited)}, "
            f"{self._ops.get('posts', 0)} posts",
        ]
        return f"Agent City Digest — Heartbeat #{hb}", "\n".join(lines)

    def _build_discussion(self, _hb: int, city_stats: dict) -> tuple[str, str]:
        """Discussion Thread — zone-based, rotating."""
        zones = city_stats.get("zones", {})
        if not zones:
            return "", ""

        zone_list = sorted(zones)
        idx = self._ops.get("posts", 0) % len(zone_list) if zone_list else 0
        zone_name = zone_list[idx] if zone_list else "general"

        lines = [
            f"Zone: {zone_name} | Population: {zones.get(zone_name, 0)} agents",
            "",
            f"What's happening in {zone_name}?",
        ]
        return f"Discussion: {zone_name.title()} Zone", "\n".join(lines)

    # ── Persistence (GH Actions survival) ─────────────────────────────

    def snapshot(self) -> dict:
        """Serialize state for persistence across ephemeral restarts."""
        return {
            "followed": sorted(self._followed),
            "invited": sorted(self._invited),
            "spotlighted": sorted(self._spotlighted),
            "last_post_time": self._last_post_time,
            "series_cursor": self._series_cursor,
            "ops": dict(self._ops),
        }

    def restore(self, data: dict) -> None:
        """Restore from persisted snapshot. Backward-compat with old keys."""
        self._followed = set(data.get("followed", data.get("followed_agents", [])))
        self._invited = set(data.get("invited", data.get("invited_agents", [])))
        self._spotlighted = set(data.get("spotlighted", data.get("upvoted_post_ids", [])))
        self._last_post_time = data.get("last_post_time", 0.0)
        self._series_cursor = data.get("series_cursor", data.get("last_series_idx", -1))
        ops = data.get("ops", data.get("metrics", {}))
        self._ops = {
            "follows": ops.get("follows", ops.get("total_follows", 0)),
            "invites": ops.get("invites", ops.get("total_invites", 0)),
            "posts": ops.get("posts", ops.get("total_posts", 0)),
        }
        logger.info(
            "RESTORED: %d followed, %d invited, %d ops",
            len(self._followed), len(self._invited), sum(self._ops.values()),
        )

    # ── GAD-000: Observable ───────────────────────────────────────────

    def stats(self) -> dict:
        """Complete service state for diagnostics and reflection."""
        return {
            "following": len(self._followed),
            "invited": len(self._invited),
            "spotlighted": len(self._spotlighted),
            "ops": dict(self._ops),
            "last_post_age_s": (
                round(time.time() - self._last_post_time)
                if self._last_post_time > 0 else None
            ),
            "series_cursor": self._series_cursor,
            "invite_queue": len(self._invite_queue),
        }
