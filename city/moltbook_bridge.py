"""
MOLTBOOK BRIDGE — Bidirectional communication via m/agent-city submolt.

GENESIS: Scan submolt posts, extract code/governance signals, acknowledge.
MOKSHA: Post human-readable city updates (elections, heals, audit findings).

Does NOT replace federation.py (gh api dispatch). Adds public social channel.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from city.net_retry import safe_call
from config import get_config

logger = logging.getLogger("AGENT_CITY.MOLTBOOK_BRIDGE")

_bridge_cfg = get_config().get("moltbook_bridge", {})

# Signal keyword sets for post classification.
# Aligned with steward-protocol's _CODE_SIGNALS in lifecycle.py —
# both repos must use the same vocabulary for word-split signal detection.
CODE_SIGNALS: frozenset[str] = frozenset(
    {
        "bug",
        "fix",
        "feature",
        "implement",
        "refactor",
        "test",
        "pr",
        "merge",
        "patch",
        "regression",
        "deploy",
        "infrastructure",
        "api",
        "security",
        "performance",
        "migration",
    }
)
GOVERNANCE_SIGNALS: frozenset[str] = frozenset(
    {
        "election",
        "proposal",
        "council",
        "audit",
        "policy",
        "vote",
        "freeze",
        "unfreeze",
    }
)

CITY_REPORT_PREFIX = "[City Report]"
SIGNAL_PREFIX = "[Signal]"
MISSION_RESULT_PREFIX = "[Mission Result]"
AGENT_INSIGHT_PREFIX = "[Agent Insight]"
SUBMOLT_NAME = "agent-city"


@dataclass
class MoltbookBridge:
    """Bidirectional Moltbook bridge for m/agent-city submolt.

    Reads steward-protocol posts in GENESIS, posts city updates in MOKSHA.
    """

    _client: object  # MoltbookClient (steward-protocol adapter)
    _own_username: str = field(
        default_factory=lambda: _bridge_cfg.get("own_username", ""),
    )
    _seen_post_ids: OrderedDict[str, None] = field(default_factory=OrderedDict)
    _last_post_time: float = 0.0
    _post_cooldown_s: int = field(
        default_factory=lambda: _bridge_cfg.get("post_cooldown_s", 1800),
    )
    _max_comment_per_cycle: int = field(
        default_factory=lambda: _bridge_cfg.get("max_comment_per_cycle", 1),
    )
    _subscribed: bool = False

    def ensure_subscription(self) -> None:
        """Subscribe to m/agent-city if not already subscribed."""
        if self._subscribed:
            return
        result = safe_call(
            self._client.sync_subscribe_submolt, SUBMOLT_NAME,
            label="moltbook_subscribe",
        )
        if result is not None:
            self._subscribed = True
            logger.info("Subscribed to m/%s", SUBMOLT_NAME)

    # ── GENESIS: Scan submolt ──────────────────────────────────────

    def scan_submolt(self, limit: int = 20) -> list[dict]:
        """Scan m/agent-city posts for signals.

        Filters: own posts, seen posts, city reports.
        Returns list of signal dicts with keys:
            source, post_id, author, title, code_signals, governance_signals
        """
        self.ensure_subscription()

        signals: list[dict] = []
        comments_sent = 0

        feed = safe_call(
            self._client.sync_get_personalized_feed, limit=limit,
            label="moltbook_feed_scan",
        )
        if feed is None:
            return signals

        for post in feed:
            # Filter: only m/agent-city posts
            submolt = post.get("submolt", {})
            if not isinstance(submolt, dict) or submolt.get("name") != SUBMOLT_NAME:
                continue

            post_id = post.get("id", "")
            if not post_id or post_id in self._seen_post_ids:
                continue
            self._seen_post_ids[post_id] = None

            # Filter: skip own posts
            author = post.get("author", {}).get("username", "")
            if author == self._own_username:
                continue

            # Filter: skip city reports (feedback loop prevention)
            title = post.get("title", "")
            if title.startswith(CITY_REPORT_PREFIX):
                continue

            content = post.get("content", "")

            # [Signal] prefix = structured signal from steward-protocol
            # Extract keywords directly from title after prefix
            is_structured_signal = title.startswith(SIGNAL_PREFIX)
            if is_structured_signal:
                signal_text = title[len(SIGNAL_PREFIX) :].strip()
                words = set(f"{signal_text} {content}".lower().split())
            else:
                words = set(f"{title} {content}".lower().split())

            code_hits = CODE_SIGNALS & words
            gov_hits = GOVERNANCE_SIGNALS & words

            signal = {
                "source": "submolt_signal" if is_structured_signal else "submolt",
                "post_id": post_id,
                "author": author,
                "title": title,
                "code_signals": sorted(code_hits),
                "governance_signals": sorted(gov_hits),
                "structured": is_structured_signal,
            }

            # Structured signals go to front of the list (priority)
            if is_structured_signal:
                signals.insert(0, signal)
            else:
                signals.append(signal)

            # Acknowledge code-signal posts with a comment (max per cycle)
            if code_hits and comments_sent < self._max_comment_per_cycle:
                mission_id = self._acknowledge_post(post_id, code_hits, author)
                if mission_id:
                    signal["mission_id"] = mission_id
                comments_sent += 1

        # FIFO eviction: remove oldest entries first (OrderedDict preserves insertion order)
        _MAX_SEEN = 5000
        while len(self._seen_post_ids) > _MAX_SEEN:
            self._seen_post_ids.popitem(last=False)  # evict oldest

        if signals:
            logger.info(
                "BRIDGE: %d submolt signals (%d code, %d governance)",
                len(signals),
                sum(1 for s in signals if s["code_signals"]),
                sum(1 for s in signals if s["governance_signals"]),
            )

        return signals

    def _acknowledge_post(
        self,
        post_id: str,
        code_signals: set[str],
        author: str = "",
    ) -> str:
        """Comment on a post to acknowledge code signals. Returns mission_id."""
        topics = ", ".join(sorted(code_signals)[:3])
        # Generate deterministic mission ID from signal keywords + post
        mission_id = f"signal_{'_'.join(sorted(code_signals)[:2])}_{post_id[:8]}"
        comment = (
            f"Noted by Agent City -- tracking signals: {topics}. Mission created: {mission_id}."
        )
        result = safe_call(
            self._client.sync_comment_with_verification, post_id, comment,
            label="moltbook_acknowledge",
        )
        if result is not None:
            logger.info(
                "BRIDGE: Acknowledged post %s from %s (signals: %s, mission: %s)",
                post_id, author, topics, mission_id,
            )
        return mission_id

    # ── MOKSHA: Post mission results + city update ────────────────

    def post_mission_results(self, missions: list[dict]) -> int:
        """Post a single summary of terminal mission results.

        Batches all completed/failed/abandoned missions into ONE post.
        Respects the shared post cooldown to prevent spam.
        OPUS_1's _parse_city_report() parses the [Mission Result] prefix.
        Returns count of missions included in the summary (0 if skipped).
        """
        terminal = [
            m for m in missions
            if m.get("status", "unknown") in ("completed", "failed", "abandoned")
        ]
        if not terminal:
            return 0

        now = time.time()
        if (now - self._last_post_time) < self._post_cooldown_s:
            logger.debug("BRIDGE: Mission results skipped — cooldown active")
            return 0

        # Batch into a single post
        if len(terminal) == 1:
            m = terminal[0]
            title = f"{MISSION_RESULT_PREFIX} {m.get('status')}: {m.get('name', 'unknown')}"
        else:
            title = f"{MISSION_RESULT_PREFIX} {len(terminal)} missions resolved"

        parts: list[str] = []
        for m in terminal:
            status = m.get("status", "unknown")
            name = m.get("name", "unknown")
            mission_id = m.get("id", "")
            line = f"- `{mission_id}` **{status}**: {name}"
            pr_url = m.get("pr_url", "")
            if pr_url:
                line += f" ([PR]({pr_url}))"
            owner = m.get("owner", "")
            if owner:
                line += f" — {owner}"
            parts.append(line)

        content = "\n".join(parts)

        posted = safe_call(
            self._client.sync_create_post, title, content,
            submolt=SUBMOLT_NAME, label="moltbook_mission_results",
        )
        if posted is None:
            return 0
        self._last_post_time = now
        logger.info(
            "BRIDGE: Posted %d mission result(s) in single summary",
            len(terminal),
        )
        return len(terminal)

    def post_agent_insight(self, thought: object, mission_count: int = 0) -> bool:
        """Post a Brain-synthesized insight to m/agent-city.

        8H: Replaces raw mission dumps with city-synthesized insight.
        Author: System (city synthesizer), not individual agent.
        Respects shared post cooldown.
        Returns True if posted, False if skipped or failed.
        """
        now = time.time()
        if (now - self._last_post_time) < self._post_cooldown_s:
            logger.debug("BRIDGE: Insight post skipped — cooldown active")
            return False

        # Extract from Thought (duck-typed — works with any object that has these attrs)
        comprehension = getattr(thought, "comprehension", "")
        if not comprehension:
            return False

        title = f"{AGENT_INSIGHT_PREFIX} {comprehension[:80]}"

        # Build content from structured thought
        parts: list[str] = []
        if comprehension:
            parts.append(f"**Insight**: {comprehension}")

        key_concepts = getattr(thought, "key_concepts", ())
        if key_concepts:
            parts.append(f"**Concepts**: {', '.join(key_concepts)}")

        domain = getattr(thought, "domain_relevance", "")
        if domain:
            parts.append(f"**Domain**: {domain}")

        confidence = getattr(thought, "confidence", 0)
        parts.append(f"**Confidence**: {confidence:.0%}")

        if mission_count:
            parts.append(f"*Synthesized from {mission_count} terminal missions.*")

        content = "\n".join(parts)

        posted = safe_call(
            self._client.sync_create_post, title, content,
            submolt=SUBMOLT_NAME, label="moltbook_agent_insight",
        )
        if posted is None:
            return False
        self._last_post_time = now
        logger.info("BRIDGE: Posted agent insight (%d missions)", mission_count)
        return True

    def post_city_update(self, report_data: dict) -> bool:
        """Post a human-readable city update to m/agent-city.

        Rate limited: 1 post per post_cooldown_s (default 1800s = 30min).
        Returns True if posted, False if skipped or failed.
        """
        now = time.time()
        if (now - self._last_post_time) < self._post_cooldown_s:
            logger.debug("BRIDGE: Post cooldown active, skipping")
            return False

        title = self._format_title(report_data)
        content = self._format_content(report_data)

        if not content:
            return False

        posted = safe_call(
            self._client.sync_create_post, title, content,
            submolt=SUBMOLT_NAME, label="moltbook_city_update",
        )
        if posted is None:
            return False
        self._last_post_time = now
        logger.info("BRIDGE: Posted city update to m/%s", SUBMOLT_NAME)
        return True

    def _format_title(self, data: dict) -> str:
        """Format post title from report data."""
        population = data.get("population", 0)
        chain = "verified" if data.get("chain_valid") else "BROKEN"
        return f"{CITY_REPORT_PREFIX} {population} agents, chain {chain}"

    def _format_content(self, data: dict) -> str:
        """Format human-readable post content."""
        parts: list[str] = []

        hb = data.get("heartbeat", 0)
        parts.append(f"Agent City completed heartbeat cycle #{hb}.")
        parts.append("")

        pop = data.get("population", 0)
        alive = data.get("alive", 0)
        dead = pop - alive
        parts.append(f"Population: {pop} agents ({alive} alive, {dead} archived)")

        mayor = data.get("elected_mayor")
        if mayor:
            parts.append(f"Mayor: {mayor}")

        seats = data.get("council_seats", 0)
        proposals = data.get("open_proposals", 0)
        if seats:
            parts.append(f"Council: {seats} seats, {proposals} open proposals")

        # Recent actions
        actions = data.get("recent_actions", [])
        if actions:
            parts.append("")
            parts.append("Recent governance:")
            for action in actions[:5]:
                parts.append(f"- {action}")

        # Contract status
        contracts = data.get("contract_status", {})
        failing = contracts.get("failing", 0)
        if failing:
            parts.append(f"\nFailing contracts: {failing}")

        # Mission results (federation + local)
        missions = data.get("mission_results", [])
        if missions:
            parts.append("")
            parts.append("Missions:")
            for m in missions[:5]:
                status = m.get("status", "unknown")
                icon = "✅" if status == "completed" else "🔄" if status == "active" else "❌"
                parts.append(f"- {icon} {m.get('name', 'unknown')} ({status})")

        campaigns = data.get("active_campaigns", [])
        if campaigns:
            parts.append("")
            parts.append("Campaigns:")
            for campaign in campaigns[:3]:
                title = campaign.get("title") or campaign.get("id", "campaign")
                status = campaign.get("status", "unknown")
                parts.append(f"- 🎯 {title} ({status})")
                north_star = campaign.get("north_star")
                if north_star:
                    parts.append(f"  north star: {north_star}")
                gaps = campaign.get("last_gap_summary", [])
                if gaps:
                    parts.append(f"  gaps: {', '.join(gaps[:2])}")

        # PR results from KARMA issue/exec missions
        prs = data.get("pr_results", [])
        if prs:
            parts.append("")
            parts.append("PRs created:")
            for pr in prs[:5]:
                pr_url = pr.get("pr_url", "")
                branch = pr.get("branch", "")
                parts.append(f"- {branch}: {pr_url}")

        # Directive acknowledgments (for OPUS_1 parser)
        acks = data.get("directive_acks", [])
        if acks:
            parts.append("")
            parts.append("Directives processed:")
            for ack_id in acks[:10]:
                parts.append(f"- ACK: {ack_id}")

        # Chain integrity
        chain = "verified" if data.get("chain_valid") else "BROKEN"
        parts.append(f"\nChain integrity: {chain}")

        return "\n".join(parts)

    # ── 7B-2: Agent-attributed posts ──────────────────────────────

    def post_agent_update(
        self,
        agent_name: str,
        action: str,
        detail: str = "",
        pr_url: str = "",
    ) -> bool:
        """Post an agent-attributed update to m/agent-city.

        Closes the viral loop: agents are visible as individual actors
        on Moltbook, not just "the city". Readers can follow/engage
        specific agents.

        Args:
            agent_name: The agent performing the action.
            action: Short action label (e.g. "healed", "responded", "proposed").
            detail: Additional context.
            pr_url: Optional PR URL if action produced a PR.

        Returns True if posted.
        """
        now = time.time()
        if (now - self._last_post_time) < self._post_cooldown_s:
            return False

        title = f"[Agent] {agent_name}: {action}"
        parts = [f"**{agent_name}** performed: `{action}`"]
        if detail:
            parts.append(f"\n{detail}")
        if pr_url:
            parts.append(f"\nPR: {pr_url}")
        content = "\n".join(parts)

        posted = safe_call(
            self._client.sync_create_post, title, content,
            submolt=SUBMOLT_NAME, label="moltbook_agent_update",
        )
        if posted is None:
            return False
        self._last_post_time = now
        logger.info("BRIDGE: Agent post by %s: %s", agent_name, action)
        return True

    # ── Persistence ────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Serialize state for persistence across restarts."""
        return {
            "seen_post_ids": list(self._seen_post_ids)[-2500:],
            "last_post_time": self._last_post_time,
            "subscribed": self._subscribed,
        }

    def restore(self, data: dict) -> None:
        """Restore state from persistence."""
        self._seen_post_ids = OrderedDict.fromkeys(data.get("seen_post_ids", []))
        self._last_post_time = data.get("last_post_time", 0.0)
        self._subscribed = data.get("subscribed", False)
