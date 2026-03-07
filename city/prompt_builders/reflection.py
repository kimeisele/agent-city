"""
REFLECTION PromptBuilder — Brain reflects on a MURALI rotation.

Extracted from brain_prompt._payload_reflection.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.prompt_registry import PromptContext


class ReflectionBuilder:
    """Builds prompts for end-of-cycle reflection."""

    @property
    def kind(self) -> str:
        return "reflection"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        lines: list[str] = []
        snapshot = ctx.snapshot

        if snapshot is not None:
            lines.append(
                f"End of MURALI rotation. "
                f"{snapshot.alive_count}/{snapshot.agent_count} alive."
            )
            if snapshot.recent_brain_thoughts:
                summaries = []
                for t in snapshot.recent_brain_thoughts[-3:]:
                    thought = t.get("thought", {})
                    summaries.append(
                        f"hb#{t.get('heartbeat', '?')}: "
                        f"{thought.get('intent', '?')} "
                        f"(conf={thought.get('confidence', 0):.0%})"
                    )
                lines.append(
                    f"Recent brain thoughts: {'; '.join(summaries)}."
                )
            if snapshot.audit_findings_count:
                lines.append(
                    f"Audit findings: {snapshot.audit_findings_count}."
                )
            if snapshot.critical_findings:
                lines.append(
                    f"Critical: "
                    f"{', '.join(snapshot.critical_findings[:3])}."
                )

        outcome_diff = ctx.outcome_diff
        if outcome_diff is not None:
            lines.append("")
            lines.append("OUTCOME DIFF (what changed since KARMA):")
            lines.append(
                f"  Agent delta: {outcome_diff.get('agent_delta', 0)}"
            )
            if outcome_diff.get("chain_changed"):
                lines.append("  Chain integrity CHANGED.")
            new_failing = outcome_diff.get("new_failing", ())
            if new_failing:
                lines.append(f"  New failing: {', '.join(new_failing)}")
            resolved = outcome_diff.get("resolved", ())
            if resolved:
                lines.append(f"  Resolved: {', '.join(resolved)}")
            ld = outcome_diff.get("learning_delta", {})
            if ld.get("synapse_delta"):
                lines.append(f"  Synapse delta: {ld['synapse_delta']}")

        reflection = ctx.reflection
        if reflection is not None:
            ls = reflection.get("learning_stats", {})
            if ls:
                lines.append(
                    f"Learning: {ls.get('synapses', 0)} synapses, "
                    f"decayed={ls.get('decayed', 0)}, "
                    f"trimmed={ls.get('trimmed', 0)}."
                )
            ims = reflection.get("immune_stats", {})
            if ims:
                lines.append(
                    f"Immune: {ims.get('heals_attempted', 0)} heals, "
                    f"{ims.get('heals_succeeded', 0)} succeeded."
                )

        return lines

    def build_schema(self) -> str:
        return (
            "Reflect on this MURALI rotation. What worked well? What "
            "degraded or failed? Did the system learn anything — new "
            "patterns, resolved issues, persistent problems? What should "
            "change in the next cycle? If you see a concrete improvement, "
            "name it. How confident are you in this reflection?"
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        parts: list[str] = ["Reflect on this MURALI rotation:"]
        reflection = ctx.reflection
        if reflection is not None:
            if reflection.get("learning_stats"):
                ls = reflection["learning_stats"]
                parts.append(
                    f"Learning: {ls.get('synapses', 0)} synapses, "
                    f"decayed={ls.get('decayed', 0)}, trimmed={ls.get('trimmed', 0)}."
                )
            if reflection.get("immune_stats"):
                ims = reflection["immune_stats"]
                parts.append(
                    f"Immune: {ims.get('heals_attempted', 0)} heals, "
                    f"{ims.get('heals_succeeded', 0)} succeeded."
                )
            if reflection.get("mission_results_terminal"):
                parts.append(
                    f"Missions completed: {len(reflection['mission_results_terminal'])}."
                )
            events = reflection.get("events_since_last", 0)
            if events:
                parts.append(f"Events this rotation: {events}.")
        return " ".join(parts)
