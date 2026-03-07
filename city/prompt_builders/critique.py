"""
CRITIQUE PromptBuilder — Brain as Kshetrajna (Knower of the Field).

Extracted from brain_prompt._payload_critique (10B).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.prompt_registry import PromptContext


class CritiqueBuilder:
    """Builds prompts for critical field evaluation."""

    @property
    def kind(self) -> str:
        return "critique"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        lines: list[str] = []
        lines.append(
            "You are the Kshetrajna — the Knower of the Field. "
            "Your role is to CRITICALLY EVALUATE system output quality. "
            "You must think like an auditor, not a summarizer."
        )
        lines.append(
            "Ask yourself: Are outputs clean and meaningful? Is agent language proper? "
            "Are workflows functioning correctly? Can I detect misbehavior or spam? "
            "Is any agent producing mechanical or repetitive content?"
        )
        lines.append(
            "If you detect problems, set action_hint to propose a concrete fix. "
            "If everything is clean, say so with high confidence."
        )

        if ctx.snapshot is not None:
            lines.append(
                f"City state: {ctx.snapshot.alive_count}/{ctx.snapshot.agent_count} alive, "
                f"chain_valid={ctx.snapshot.chain_valid}."
            )
            if ctx.snapshot.failing_contracts:
                lines.append(
                    f"Failing contracts: {', '.join(ctx.snapshot.failing_contracts[:5])}."
                )

        if ctx.field_summary:
            lines.append("")
            lines.append("=== FIELD DIGEST (MahaCompression-derived) ===")
            lines.append(ctx.field_summary)
            lines.append("=== END FIELD DIGEST ===")

        return lines

    def build_schema(self) -> str:
        return (
            "Critically evaluate the system's output quality. Are agents "
            "producing meaningful content or mechanical repetition? Are "
            "there anomalies in behavior — spam, misbehavior, dead loops? "
            "Is language quality acceptable? Are workflows functioning as "
            "intended? If you detect problems, propose a concrete fix. "
            "Be harsh but precise. What evidence supports your critique?"
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        base = (
            "Critically evaluate the Field Summary below. "
            "Are outputs clean? Is language proper? Are workflows healthy? "
            "Flag any anomalies and propose fixes."
        )
        if ctx.field_summary:
            return f"{base}\n\n{ctx.field_summary}"
        return base
