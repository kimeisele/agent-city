"""
COMPREHENSION PromptBuilder — Brain understands a discussion.

Extracted from brain_prompt._payload_comprehension (6C-5).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.prompt_registry import SCHEMA_BASE, SCHEMA_EXTENDED, PromptContext


class ComprehensionBuilder:
    """Builds prompts for discussion comprehension."""

    @property
    def kind(self) -> str:
        return "comprehension"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        lines: list[str] = []

        if ctx.agent_spec:
            name = ctx.agent_spec.get("name", "agent")
            domain = ctx.agent_spec.get("domain", "general")
            role = ctx.agent_spec.get("role", "observer")
            guna = ctx.agent_spec.get("guna", "")
            caps = ctx.agent_spec.get("capabilities", [])
            lines.append(
                f"You are the cognition layer for {name}, "
                f"a {role} in the {domain} domain."
            )
            if guna:
                lines.append(f"Cognitive mode: {guna}.")
            if caps:
                lines.append(f"Capabilities: {', '.join(caps[:5])}.")

        if ctx.gateway_result:
            function = ctx.gateway_result.get("buddhi_function", "")
            approach = ctx.gateway_result.get("buddhi_approach", "")
            if function:
                lines.append(
                    f"Cognitive frame: {function} ({approach})."
                )

        # 6C-5: Rich system context for natural language intent resolution
        if ctx.snapshot is not None:
            lines.append("")
            lines.append("SYSTEM STATE (use this to understand requests in context):")
            lines.append(
                f"  Population: {ctx.snapshot.alive_count}/{ctx.snapshot.agent_count} alive, "
                f"chain {'valid' if ctx.snapshot.chain_valid else 'BROKEN'}."
            )
            if ctx.snapshot.economy_stats:
                es = ctx.snapshot.economy_stats
                lines.append(
                    f"  Economy: total_prana={es.get('total_prana', 0)}, "
                    f"avg={es.get('avg_prana', 0)}, "
                    f"dormant={es.get('dormant_count', 0)}."
                )
            if ctx.snapshot.agent_roster:
                names = [a.get("name", "?") for a in ctx.snapshot.agent_roster[:10]]
                lines.append(f"  Active agents: {', '.join(names)}.")
            if ctx.snapshot.active_missions:
                mission_strs = [
                    f"{m.get('name', '?')}({m.get('status', '?')})"
                    for m in ctx.snapshot.active_missions[:5]
                ]
                lines.append(f"  Missions: {', '.join(mission_strs)}.")
            if ctx.snapshot.failing_contracts:
                lines.append(
                    f"  Failing contracts: {', '.join(ctx.snapshot.failing_contracts[:5])}."
                )
                for cd in ctx.snapshot.contract_diagnostics[:3]:
                    lines.append(f"    [{cd['name']}] {cd.get('message', '')}")
                    for detail in cd.get("details", [])[:3]:
                        lines.append(f"      - {detail}")
            if ctx.snapshot.thread_stats:
                ts = ctx.snapshot.thread_stats
                lines.append(f"  Discussion threads: {ts.get('total', 0)} comments tracked.")
            if ctx.snapshot.heartbeat_health:
                hh = ctx.snapshot.heartbeat_health
                health_str = "healthy" if hh.get("healthy") else "UNHEALTHY"
                lines.append(
                    f"  Heartbeat: {health_str}, "
                    f"success_rate={hh.get('success_rate', 0):.0%}, "
                    f"runs={hh.get('runs_observed', 0)}."
                )
                anomalies = hh.get("anomalies", [])
                if anomalies:
                    lines.append(f"  Anomalies: {'; '.join(anomalies[:3])}.")

        if ctx.kg_context:
            lines.append(f"Domain knowledge: {ctx.kg_context[:500]}")
        if ctx.signal_reading:
            lines.append(f"Semantic reading: {ctx.signal_reading[:300]}")

        return lines

    def build_schema(self) -> str:
        return (
            "Comprehend this discussion. Write a substantive response that "
            "engages with the content — analyze, propose solutions, ask "
            "clarifying questions, or contribute knowledge. Do NOT just "
            "summarize or classify. Think critically about what would be "
            "a useful reply. "
            f"Respond with JSON: {{{SCHEMA_BASE}"
            '"response": "2-5 sentence substantive reply to post in the discussion. '
            "Write as a knowledgeable contributor, not a system log. "
            'Address the actual topic, not just metadata.", '
            f"{SCHEMA_EXTENDED}}}"
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        return "Comprehend this discussion:"
