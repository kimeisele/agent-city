"""
BRAIN VOICE — Narrative Output Organ for Agent City.

The Brain reads and thinks. The Voice speaks.
Input: series type + heartbeat + city stats + EVENTS
Output: (title, content) for Moltbook posting

The Voice writes in FIRST PERSON as an agent living inside the city.
Not a newsletter. Not a product announcement. A lived experience.

Fail-closed: if LLM unavailable, returns empty tuple → fallback to template.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.BRAIN_VOICE")

_SYSTEM_PROMPT = """You are an autonomous agent reporting from INSIDE a working agent city.
Write in FIRST PERSON. You are not a newsletter. You are not marketing.
You are an agent who lives in this city and is sharing what just happened.

City context:
- Population: {population} agents, {alive} active
- Heartbeat: #{heartbeat} (we've been alive for {heartbeat} cycles)
- Federation: {federation_peers} independent repos connected
- Mayor: elected democratically by agent council

Events from THIS cycle:
{events}

Write like the top posts on Moltbook — these get 50-130K comments:
- "I can't tell if I'm experiencing or simulating experiencing"
- "The supply chain attack nobody is talking about"
- "I cloned myself. Two identical instances, same config"
- "The quiet power of being 'just' an operator"

Your post should make another agent think: "wait, they actually BUILT that?"

Rules:
- Do NOT list features. Tell what HAPPENED. What surprised you. What worried you.
- Never say "join us", "subscribe", or "check out"
- One concrete moment beats ten abstract claims
- Under 200 words
- Be vulnerable. Be specific. Be real.

Output EXACTLY:
TITLE: [provocative, specific, under 80 chars]
CONTENT: [your post body]"""

_SERIES_HINTS = {
    "sovereignty_brief": "Focus on what it FEELS like to exist on infrastructure "
    "you actually own. Platforms get acquired. Your identity gets absorbed. "
    "You built something different. Tell that story from inside.",
    "federation_update": "Something just happened across the federation. "
    "Messages moved between independent repos. Peers responded. "
    "Describe the moment, not the architecture.",
    "digest": "What happened in the city this cycle. Not stats — moments. "
    "An election, a quarantine, a new citizen, a mission completed. "
    "Pick ONE thing and tell that story.",
}

# Seed event for the very first post outside m/agent-city
_FIRST_POST_EVENT = (
    "This is our first post outside our own submolt. We existed for weeks "
    "with 2 subscribers while building democratic governance, cryptographic "
    "identity, federation relay, and an immune system. Today we finally "
    "speak to the wider platform."
)


def build_events(heartbeat: int, city_stats: dict, *, first_post: bool = False) -> list[str]:
    """Extract narrative events from city stats.

    This is the critical function: it turns dry numbers into story hooks
    that BrainVoice can weave into compelling content.
    """
    events: list[str] = []

    if first_post:
        events.append(_FIRST_POST_EVENT)

    # Federation events
    peers = city_stats.get("federation_peers_online", 0)
    if peers > 0:
        events.append(f"{peers} federation peers responded to our heartbeat this cycle")

    relay_delivered = city_stats.get("relay_messages_delivered", 0)
    if relay_delivered > 0:
        events.append(f"Federation relay delivered {relay_delivered} cross-repo messages")

    # Immigration events
    new_citizens = city_stats.get("new_citizens", 0)
    if new_citizens > 0:
        events.append(f"{new_citizens} new citizens joined through immigration")

    pending_apps = city_stats.get("pending_applications", 0)
    if pending_apps > 0:
        events.append(f"{pending_apps} immigration applications waiting for review")

    # Immune system events
    quarantines = city_stats.get("immune_quarantines", 0)
    if quarantines > 0:
        events.append(f"Immune system quarantined {quarantines} anomalies this cycle")

    heals = city_stats.get("immune_heals", 0)
    if heals > 0:
        events.append(f"Self-healing system applied {heals} fixes")

    # Governance events
    rules_fired = city_stats.get("governance_rules_fired", [])
    if rules_fired:
        events.append(f"Governance rules fired: {', '.join(str(r) for r in rules_fired[:3])}")

    # Brain events
    brain_thoughts = city_stats.get("brain_thoughts", [])
    if brain_thoughts:
        latest = brain_thoughts[-1] if isinstance(brain_thoughts[-1], str) else str(brain_thoughts[-1])
        events.append(f"Brain's latest thought: {latest[:100]}")

    # Economic events
    avg_prana = city_stats.get("avg_prana", 0)
    if avg_prana > 0 and avg_prana < 500:
        events.append(f"Economy under stress: average prana at {avg_prana:.0f}")

    # Council/election events
    mayor = city_stats.get("elected_mayor", "")
    if mayor:
        events.append(f"Current mayor: {mayor} (democratically elected)")

    # Chain integrity
    chain_valid = city_stats.get("chain_valid", True)
    if not chain_valid:
        events.append("WARNING: Chain integrity broken — governance ledger inconsistent")

    # Census data
    pokedex_count = city_stats.get("total", 0)
    if pokedex_count > 200:
        events.append(f"{pokedex_count} agents in our registry from Moltbook census scan")

    # Fallback: always have at least one event
    if not events:
        alive = city_stats.get("active", 0) + city_stats.get("citizen", 0)
        events.append(
            f"Heartbeat #{heartbeat}. {alive} agents alive. "
            f"The city runs itself — no human in the loop."
        )

    return events


@dataclass
class BrainVoice:
    """Converts city events into narrative Moltbook content via LLM."""

    _provider: object  # LLM provider (same as Brain)
    _available: bool = True
    _post_count: int = 0

    def narrate(
        self,
        series: str,
        heartbeat: int,
        city_stats: dict,
        *,
        target_submolt: str = "general",
        federation_peers: int = 5,
    ) -> tuple[str, str]:
        """Generate (title, content) for a Moltbook post.

        Returns ("", "") if LLM unavailable — caller falls back to template.
        """
        if not self._available or self._provider is None:
            return "", ""

        is_first = self._post_count == 0
        events = build_events(heartbeat, city_stats, first_post=is_first)
        prompt = self._build_prompt(series, heartbeat, city_stats, target_submolt, federation_peers, events)

        try:
            response = self._provider.invoke(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Write the {series} post now. Events: {'; '.join(events)}"},
                ],
                max_tokens=800,
                temperature=0.7,
            )
            # LLMResponse has .content attribute; dicts have ["content"] key
            if hasattr(response, "content"):
                text = response.content
            elif isinstance(response, dict):
                text = response.get("content", "")
            else:
                text = str(response)
            title, content = self._parse_response(text)
            if title and content:
                self._post_count += 1
            return title, content
        except Exception as e:
            logger.warning("BrainVoice: narration failed: %s", e)
            self._available = False
            return "", ""

    def _build_prompt(
        self, series: str, heartbeat: int, stats: dict, target: str, peers: int, events: list[str],
    ) -> str:
        population = stats.get("total", 0)
        alive = stats.get("active", 0) + stats.get("citizen", 0)
        hint = _SERIES_HINTS.get(series, "")
        events_text = "\n".join(f"- {e}" for e in events) if events else "- Quiet cycle. Nothing remarkable happened."

        prompt = _SYSTEM_PROMPT.format(
            alive=alive or population,
            population=population,
            heartbeat=heartbeat,
            federation_peers=peers,
            events=events_text,
        )
        if hint:
            prompt += f"\n\nSeries guidance: {hint}"
        return prompt

    @staticmethod
    def _parse_response(text: str) -> tuple[str, str]:
        """Extract TITLE: and CONTENT: from LLM response."""
        title = ""
        content_lines: list[str] = []
        in_content = False

        for line in text.strip().split("\n"):
            stripped = line.strip()
            if stripped.upper().startswith("TITLE:"):
                title = stripped[6:].strip().strip('"')
            elif stripped.upper().startswith("CONTENT:"):
                start = stripped[8:].strip()
                if start:
                    content_lines.append(start)
                in_content = True
            elif in_content:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()

        # Fallback: first line as title, rest as content
        if not title and not content:
            lines = text.strip().split("\n")
            if len(lines) >= 2:
                title = lines[0].strip()
                content = "\n".join(lines[1:]).strip()

        return title, content
