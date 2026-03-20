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
        if snapshot.discussion_activity:
            da = snapshot.discussion_activity
            lines.append(
                f"Discussions: {da.get('total_seen', 0)} seen, "
                f"{da.get('unreplied', 0)} unreplied."
            )
        if snapshot.thread_stats:
            ts = snapshot.thread_stats
            lines.append(
                f"Threads: {ts.get('human_comments', 0)} human comments, "
                f"{ts.get('agent_responses', 0)} agent responses, "
                f"{ts.get('unresolved', 0)} unresolved."
            )
        if snapshot.active_missions:
            active = [m for m in snapshot.active_missions if m.get("status") != "completed"]
            if active:
                mission_summaries = [
                    f"{m.get('name', m.get('id', '?'))}({m.get('status', '?')})"
                    for m in active[:5]
                ]
                lines.append(f"Active missions: {', '.join(mission_summaries)}.")
        if snapshot.active_campaigns:
            summaries = []
            for campaign in snapshot.active_campaigns[:3]:
                gaps = campaign.get("last_gap_summary", [])
                north_star = campaign.get("north_star")
                goal_text = f"; north_star={north_star}" if north_star else ""
                gap_text = f"; gaps={', '.join(gaps[:2])}" if gaps else ""
                summaries.append(
                    f"{campaign.get('title') or campaign.get('id', '?')}"
                    f"({campaign.get('status', '?')}{goal_text}{gap_text})"
                )
            lines.append(f"Campaigns: {' | '.join(summaries)}.")

        return lines

    def build_schema(self) -> str:
        return (
            "Evaluate the system's health. What is working correctly? "
            "What is failing or degrading, and what is the root cause — "
            "not just the symptom? Are there patterns in the failures? "
            "How confident are you in this diagnosis?\n\n"
            "IMPORTANT — action_hint vocabulary (use EXACTLY these formats):\n"
            "- \"observe\" — no action needed, system is healthy\n"
            "- \"flag_bottleneck:<domain>\" — a domain is stuck or degrading\n"
            "- \"investigate:<topic>\" — something needs a deeper look\n"
            "- \"create_mission:<description>\" — a concrete problem exists that "
            "an agent should fix. Use this when you see anomalies like: "
            "spam loops (response_count >> human_count), unresolved threads "
            "with no agent activity, broken contracts, dead agents that "
            "should be alive, or any clear actionable problem.\n\n"
            "You MUST set action_hint to one of the above. Do NOT just observe "
            "when there is a clear problem — ACT by emitting create_mission "
            "with a specific description of what needs to be done. "
            "Set confidence >= 0.7 when the evidence is clear.\n\n"
            "What evidence supports your assessment?"
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        return "Evaluate the current system health."
