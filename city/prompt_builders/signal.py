"""
SIGNAL PromptBuilder — Brain comprehends inter-agent signals.

Extracted from brain_prompt._payload_signal.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.prompt_registry import SCHEMA_BASE, PromptContext


class SignalBuilder:
    """Builds prompts for signal comprehension."""

    @property
    def kind(self) -> str:
        return "signal"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        lines: list[str] = []

        if ctx.receiver_spec:
            domain = ctx.receiver_spec.get("domain", "general")
            role = ctx.receiver_spec.get("role", "observer")
            lines.append(f"You are cognition for a {role} in {domain}.")

        if ctx.decoded_signal is not None:
            concepts = list(
                getattr(ctx.decoded_signal, "resonant_concepts", ())
            )[:5]
            transitions = list(
                getattr(ctx.decoded_signal, "element_transitions", ())
            )[:3]
            sender = getattr(
                getattr(ctx.decoded_signal, "signal", None),
                "sender_name",
                "unknown",
            )
            affinity = getattr(ctx.decoded_signal, "affinity", 0)
            lines.append(
                f"Signal from {sender} (affinity={affinity:.2f}). "
                f"Concepts: {', '.join(str(c) for c in concepts)}. "
                f"Transitions: {', '.join(str(t) for t in transitions)}."
            )

        return lines

    def build_schema(self) -> str:
        return (
            "What does this signal mean for this agent? "
            f"Respond with JSON: {{{SCHEMA_BASE}}}"
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        return "What does this signal mean for this agent?"
