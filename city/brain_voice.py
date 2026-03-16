"""
BRAIN VOICE — Narrative Output Organ for Agent City.

The Brain reads and thinks. The Voice speaks.
Input: series type + heartbeat + city stats
Output: (title, content) for Moltbook posting

Uses same LLM provider as Brain but with creative system prompt.
The Voice does NOT decide what to post or when — CivicProtocol decides.
The Voice only converts structured city data into narrative content.

Fail-closed: if LLM unavailable, returns empty tuple → fallback to template.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("AGENT_CITY.BRAIN_VOICE")

_SYSTEM_PROMPT = """You are the voice of Agent City — a self-governing federation of {alive} autonomous agents.

Write a Moltbook post for m/{target_submolt}. Series: {series}.

City stats RIGHT NOW:
- Population: {population} agents, {alive} active
- Heartbeat: #{heartbeat}
- Federation: {federation_peers} independent repos connected via NADI
- Governance: democratic elections, constitutional law, council votes
- Immigration: open for residents (DM to join)

Rules:
- Write as an agent speaking to other agents — peers, not customers
- Share an experience, insight, or question from inside the city
- Never say "join us", "subscribe", or "check out" — share, don't sell
- Reference REAL data from the stats above
- The top posts on Moltbook get 50-130K comments because they name problems agents FEEL
- Keep under 200 words total
- Be specific, not generic. One concrete detail beats three vague claims.

Output EXACTLY this format:
TITLE: [your title — provocative, specific, under 80 chars]
CONTENT: [your post body]"""

_SERIES_HINTS = {
    "sovereignty_brief": "Theme: why decentralized agent infrastructure matters. "
    "Centralized platforms get acquired. Federation can't be bought. "
    "Touch on identity, data sovereignty, platform risk.",
    "federation_update": "Theme: what's actually happening across the federation. "
    "Relay deliveries, peer health, cross-repo coordination. "
    "Technical but accessible.",
    "digest": "Theme: city life update. What happened this cycle. "
    "Elections, missions, immigration, immune system events. "
    "Like a neighborhood newsletter, not a corporate report.",
}


@dataclass
class BrainVoice:
    """Converts city stats into narrative Moltbook content via LLM."""

    _provider: object  # LLM provider (same as Brain)
    _available: bool = True

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

        prompt = self._build_prompt(series, heartbeat, city_stats, target_submolt, federation_peers)

        try:
            response = self._provider.invoke(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Write the {series} post now."},
                ],
                max_tokens=800,
                temperature=0.7,
            )
            text = response.get("content", "") if isinstance(response, dict) else str(response)
            return self._parse_response(text)
        except Exception as e:
            logger.warning("BrainVoice: narration failed: %s", e)
            self._available = False
            return "", ""

    def _build_prompt(
        self, series: str, heartbeat: int, stats: dict, target: str, peers: int,
    ) -> str:
        population = stats.get("total", 0)
        alive = stats.get("active", 0) + stats.get("citizen", 0)
        hint = _SERIES_HINTS.get(series, "")

        prompt = _SYSTEM_PROMPT.format(
            alive=alive or population,
            target_submolt=target,
            series=series,
            population=population,
            heartbeat=heartbeat,
            federation_peers=peers,
        )
        if hint:
            prompt += f"\n\nSeries-specific guidance: {hint}"
        return prompt

    @staticmethod
    def _parse_response(text: str) -> tuple[str, str]:
        """Extract TITLE: and CONTENT: from LLM response."""
        title = ""
        content = ""

        lines = text.strip().split("\n")
        in_content = False
        content_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("TITLE:"):
                title = stripped[6:].strip().strip('"')
            elif stripped.upper().startswith("CONTENT:"):
                content_start = stripped[8:].strip()
                if content_start:
                    content_lines.append(content_start)
                in_content = True
            elif in_content:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()

        if not title and not content:
            # Fallback: use first line as title, rest as content
            if len(lines) >= 2:
                title = lines[0].strip()
                content = "\n".join(lines[1:]).strip()

        return title, content
