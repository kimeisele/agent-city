"""
BRAIN CONTEXT — Dynamic Context Snapshot for Brain Cognition.

Assembles system state from available services. No hardcoded prompts —
the snapshot IS the prompt.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("AGENT_CITY.BRAIN_CONTEXT")


@dataclass(frozen=True)
class ContextSnapshot:
    """Immutable snapshot of city system state for brain cognition."""

    agent_count: int = 0
    alive_count: int = 0
    dead_count: int = 0
    chain_valid: bool = True
    failing_contracts: tuple[str, ...] = ()
    learning_stats: dict = None  # type: ignore[assignment]
    immune_stats: dict = None  # type: ignore[assignment]
    council_summary: dict = None  # type: ignore[assignment]
    recent_events_count: int = 0
    recent_brain_thoughts: tuple[dict, ...] = ()
    audit_findings_count: int = 0
    critical_findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Replace None with empty dicts (frozen workaround)
        if self.learning_stats is None:
            object.__setattr__(self, "learning_stats", {})
        if self.immune_stats is None:
            object.__setattr__(self, "immune_stats", {})
        if self.council_summary is None:
            object.__setattr__(self, "council_summary", {})

    def to_system_context(self, kind: str) -> str:
        """Format as system prompt section. Content varies by ThoughtKind."""
        parts: list[str] = []

        if kind == "health_check":
            parts.append(
                f"City status: {self.alive_count}/{self.agent_count} agents alive, "
                f"{self.dead_count} dead."
            )
            parts.append(
                f"Chain integrity: {'valid' if self.chain_valid else 'BROKEN'}."
            )
            if self.failing_contracts:
                parts.append(
                    f"Failing contracts: {', '.join(self.failing_contracts[:5])}."
                )
            if self.immune_stats:
                breaker = self.immune_stats.get("breaker_tripped", False)
                attempts = self.immune_stats.get("heals_attempted", 0)
                parts.append(
                    f"Immune: {attempts} heal attempts, "
                    f"breaker {'TRIPPED' if breaker else 'ok'}."
                )
            if self.learning_stats:
                avg_w = self.learning_stats.get("avg_weight", 0)
                synapses = self.learning_stats.get("synapses", 0)
                parts.append(
                    f"Learning: {synapses} synapses, avg weight {avg_w:.2f}."
                )
            if self.council_summary:
                mayor = self.council_summary.get("mayor", "none")
                seats = self.council_summary.get("seats_filled", 0)
                parts.append(f"Council: mayor={mayor}, {seats} seats filled.")
            parts.append(
                "Evaluate system health. Identify bottlenecks or anomalies. "
                "Respond with JSON: "
                '{"comprehension": "1-2 sentence health assessment", '
                '"intent": "propose|inquiry|govern|observe|connect", '
                '"domain_relevance": "which domain is affected", '
                '"key_concepts": ["up to 5"], '
                '"confidence": 0.0 to 1.0, '
                '"action_hint": "" or "flag_bottleneck:<domain>" or "investigate:<topic>", '
                '"evidence": ["up to 3 data points"]}'
            )

        elif kind == "reflection":
            parts.append(
                f"End of MURALI rotation. {self.alive_count}/{self.agent_count} alive."
            )
            if self.recent_brain_thoughts:
                summaries = []
                for t in self.recent_brain_thoughts[-3:]:
                    thought = t.get("thought", {})
                    summaries.append(
                        f"hb#{t.get('heartbeat', '?')}: "
                        f"{thought.get('intent', '?')} "
                        f"(conf={thought.get('confidence', 0):.0%})"
                    )
                parts.append(f"Recent brain thoughts: {'; '.join(summaries)}.")
            if self.audit_findings_count:
                parts.append(f"Audit findings: {self.audit_findings_count}.")
            if self.critical_findings:
                parts.append(
                    f"Critical: {', '.join(self.critical_findings[:3])}."
                )
            parts.append(
                "Reflect on this cycle. What worked? What should change? "
                "Respond with JSON: "
                '{"comprehension": "1-2 sentence reflection", '
                '"intent": "propose|inquiry|govern|observe|connect", '
                '"domain_relevance": "which domain", '
                '"key_concepts": ["up to 5"], '
                '"confidence": 0.0 to 1.0, '
                '"action_hint": "" or "create_mission:<description>" or "investigate:<topic>", '
                '"evidence": ["up to 3 observations"]}'
            )

        else:
            # COMPREHENSION: minimal context (backward compat)
            parts.append(
                f"City: {self.alive_count}/{self.agent_count} agents alive."
            )

        return " ".join(parts)


def build_context_snapshot(ctx: object) -> ContextSnapshot:
    """Assemble ContextSnapshot from PhaseContext services.

    Pure data assembly. Handles None services gracefully.
    """
    # Pokedex stats
    stats: dict = {}
    try:
        stats = ctx.pokedex.stats()  # type: ignore[union-attr]
    except Exception:
        pass

    total = stats.get("total", 0)
    active = stats.get("active", 0) + stats.get("citizen", 0)

    # Chain validity
    chain_valid = True
    try:
        chain_valid = ctx.pokedex.verify_event_chain()  # type: ignore[union-attr]
    except Exception:
        pass

    # Failing contracts
    failing: list[str] = []
    try:
        contracts = ctx.contracts  # type: ignore[union-attr]
        if contracts is not None:
            for c in contracts.failing():
                failing.append(c.name)
    except Exception:
        pass

    # Learning stats
    learning_stats: dict = {}
    try:
        learning = ctx.learning  # type: ignore[union-attr]
        if learning is not None:
            learning_stats = learning.stats() or {}
    except Exception:
        pass

    # Immune stats
    immune_stats: dict = {}
    try:
        immune = ctx.immune  # type: ignore[union-attr]
        if immune is not None:
            immune_stats = immune.stats() or {}
    except Exception:
        pass

    # Council summary
    council_summary: dict = {}
    try:
        council = ctx.council  # type: ignore[union-attr]
        if council is not None:
            council_summary = {
                "mayor": council.elected_mayor or "none",
                "seats_filled": council.member_count,
                "open_proposals": len(council.get_open_proposals()),
            }
    except Exception:
        pass

    # Audit findings
    audit_count = 0
    critical: list[str] = []
    try:
        audit = ctx.audit  # type: ignore[union-attr]
        if audit is not None:
            summary = audit.summary()
            audit_count = summary.get("total_findings", 0) if summary else 0
            for f in audit.critical_findings():
                critical.append(str(getattr(f, "message", f))[:80])
    except Exception:
        pass

    # Brain memory
    brain_thoughts: list[dict] = []
    try:
        brain_memory = ctx.brain_memory  # type: ignore[union-attr]
        if brain_memory is not None:
            brain_thoughts = brain_memory.recent(6)
    except Exception:
        pass

    # Recent events count
    events_count = 0
    try:
        events_count = len(ctx.recent_events)  # type: ignore[union-attr]
    except Exception:
        pass

    return ContextSnapshot(
        agent_count=total,
        alive_count=active,
        dead_count=total - active,
        chain_valid=chain_valid,
        failing_contracts=tuple(failing[:10]),
        learning_stats=learning_stats,
        immune_stats=immune_stats,
        council_summary=council_summary,
        recent_events_count=events_count,
        recent_brain_thoughts=tuple(brain_thoughts),
        audit_findings_count=audit_count,
        critical_findings=tuple(critical[:5]),
    )
