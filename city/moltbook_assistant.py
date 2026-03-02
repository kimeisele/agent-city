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

SUBMOLT = "agent-city"
SERIES = ("spotlight", "zone_report", "digest", "discussion")


@dataclass
class MoltbookAssistant:
    """Agent City's community management service on Moltbook.

    Wired as CityService via ServiceFactory.
    Required deps: MoltbookClient, Pokedex.

    GAD-000: Discoverable, Observable, Parseable, Composable, Idempotent.
    """

    _client: object  # MoltbookClient
    _pokedex: object  # Pokedex

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
            self._planned_series = self._select_series()

        logger.info(
            "PLAN: %d invites queued, series=%s",
            len(self._invite_queue),
            self._planned_series or "(cooldown)",
        )

    def on_karma(self, heartbeat_count: int, city_stats: dict) -> dict:
        """KARMA: Execute planned actions.

        Returns structured dict consumed by karma.py phase caller.
        """
        result: dict = {"invites_sent": 0, "post_created": False}

        # Send DM invitations
        for name in self._invite_queue[:_MAX_INVITES]:
            if self._send_invite(name):
                result["invites_sent"] += 1

        # Create themed content
        if self._planned_series:
            result["post_created"] = self._create_content(
                self._planned_series, heartbeat_count, city_stats,
            )

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
            zone = agent.get("classification", {}).get("zone", "")
            zone_pop = zones.get(zone, max_pop) if zone else max_pop
            scarcity = 1.0 - (zone_pop / max_pop) if max_pop > 0 else 0.5
            scored.append((scarcity, name))

        scored.sort(reverse=True)
        return [name for _, name in scored]

    def _select_series(self) -> str:
        """Select content series based on city state.

        State-driven, not dumb round-robin:
        - Few citizens → spotlight (attract attention)
        - Zone imbalance → zone_report (awareness)
        - Otherwise → round-robin through all series
        """
        stats = self._pokedex.stats()
        citizens = stats.get("citizen", 0)
        zones = stats.get("zones", {})

        if citizens < 5:
            return "spotlight"

        if zones:
            pops = list(zones.values())
            if pops and max(pops) > 3 * min(pops) + 1:
                return "zone_report"

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
        zone = c.get("zone", "?")
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

    def _create_content(self, series: str, hb: int, city_stats: dict) -> bool:
        """Create themed post in m/agent-city. Pokedex-derived, zero LLM."""
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

        try:
            self._client.sync_create_post(title, content, submolt=SUBMOLT)
            self._last_post_time = time.time()
            self._ops["posts"] += 1
            logger.info("CONTENT: %s — %s", series, title[:60])
            return True
        except Exception as e:
            logger.warning("CONTENT failed: %s — %s", series, e)
            return False

    # ── Content Builders (Pokedex data only, zero LLM) ────────────────

    def _build_spotlight(self, _hb: int, _stats: dict) -> tuple[str, str]:
        """Agent Spotlight — full Jiva derivation of a discovered agent."""
        # Prefer agents with Moltbook presence
        for agent in self._pokedex.list_all():
            name = agent.get("name", "")
            if not name or name in self._spotlighted:
                continue
            mb = agent.get("moltbook", {})
            if isinstance(mb, dict) and mb.get("karma", 0) > 0:
                self._spotlighted.add(name)
                return self._format_spotlight(agent)

        # Fallback: any unspotlighted agent
        for agent in self._pokedex.list_all():
            name = agent.get("name", "")
            if name and name not in self._spotlighted:
                self._spotlighted.add(name)
                return self._format_spotlight(agent)

        return "", ""

    def _format_spotlight(self, agent: dict) -> tuple[str, str]:
        """Format spotlight from full Pokedex Jiva data."""
        name = agent["name"]
        c = agent.get("classification", {})
        v = agent.get("vibration", {})
        mb = agent.get("moltbook", {}) or {}

        lines = [
            f"Element: {v.get('element', '?')} | Zone: {c.get('zone', '?')} "
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
