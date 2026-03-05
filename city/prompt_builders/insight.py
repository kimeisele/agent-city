"""
INSIGHT PromptBuilder — Brain synthesizes mission insights.

Extracted from brain_prompt._payload_insight (8H).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.prompt_registry import PromptContext


class InsightBuilder:
    """Builds prompts for mission insight synthesis."""

    @property
    def kind(self) -> str:
        return "insight"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        lines: list[str] = []
        lines.append(
            "You are the city's cognitive synthesizer. You observe all agent activity "
            "and distill it into a single insight for the agent social network (Moltbook)."
        )
        lines.append(
            "Do NOT list mission statuses. Do NOT dump data. "
            "Synthesize what the city LEARNED from these missions."
        )

        if ctx.snapshot is not None:
            lines.append(
                f"City: {ctx.snapshot.alive_count}/{ctx.snapshot.agent_count} alive."
            )

        reflection = ctx.reflection
        if reflection is not None:
            missions = reflection.get("mission_results_terminal", [])
            if missions:
                lines.append(f"Terminal missions this cycle: {len(missions)}")
                for m in missions[:10]:
                    name = m.get("name", m.get("id", "?"))
                    status = m.get("status", "?")
                    owner = m.get("owner", "unknown")
                    lines.append(f"  - {name} ({status}) by {owner}")

        return lines

    def build_schema(self) -> str:
        return (
            "Synthesize a 1-2 sentence insight from these missions. "
            "What did the city learn? What pattern emerged? "
            "Write for agents, not humans. Be concrete, not generic."
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        mission_count = 0
        if ctx.reflection is not None:
            mission_count = len(ctx.reflection.get("mission_results_terminal", []))
        return (
            f"Synthesize an insight from {mission_count} completed missions "
            f"this cycle. What did the city learn?"
        )
