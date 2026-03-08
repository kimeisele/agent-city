"""
HEALTH_CHECK PromptBuilder — Brain evaluates system health.

Extracted from brain_prompt._payload_health.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.prompt_registry import PromptContext


class HealthCheckBuilder:
    """Builds prompts for system health evaluation."""

    @property
    def kind(self) -> str:
        return "health_check"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        lines: list[str] = []
        snapshot = ctx.snapshot

        if snapshot is None:
            lines.append("No system snapshot available.")
            return lines

        lines.append(
            f"City status: {snapshot.alive_count}/{snapshot.agent_count} "
            f"agents alive, {snapshot.dead_count} dead."
        )
        lines.append(
            f"Chain integrity: {'valid' if snapshot.chain_valid else 'BROKEN'}."
        )
        if snapshot.failing_contracts:
            lines.append(
                f"Failing contracts: "
                f"{', '.join(snapshot.failing_contracts[:5])}."
            )
        if snapshot.immune_stats:
            breaker = snapshot.immune_stats.get("breaker_tripped", False)
            attempts = snapshot.immune_stats.get("heals_attempted", 0)
            lines.append(
                f"Immune: {attempts} heal attempts, "
                f"breaker {'TRIPPED' if breaker else 'ok'}."
            )
        if snapshot.learning_stats:
            avg_w = snapshot.learning_stats.get("avg_weight", 0)
            synapses = snapshot.learning_stats.get("synapses", 0)
            lines.append(
                f"Learning: {synapses} synapses, avg weight {avg_w:.2f}."
            )
        if snapshot.council_summary:
            mayor = snapshot.council_summary.get("mayor", "none")
            seats = snapshot.council_summary.get("seats_filled", 0)
            lines.append(f"Council: mayor={mayor}, {seats} seats filled.")
        if snapshot.active_campaigns:
            summaries = []
            for campaign in snapshot.active_campaigns[:3]:
                gaps = campaign.get("last_gap_summary", [])
                gap_text = f"; gaps={', '.join(gaps[:2])}" if gaps else ""
                summaries.append(
                    f"{campaign.get('title') or campaign.get('id', '?')}"
                    f"({campaign.get('status', '?')}{gap_text})"
                )
            lines.append(f"Campaigns: {' | '.join(summaries)}.")

        return lines

    def build_schema(self) -> str:
        return (
            "Evaluate the system's health. What is working correctly? "
            "What is failing or degrading, and what is the root cause — "
            "not just the symptom? Are there patterns in the failures? "
            "How confident are you in this diagnosis? If a specific action "
            "would improve the situation, name it precisely. What evidence "
            "supports your assessment?"
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        return "Evaluate the current system health."
