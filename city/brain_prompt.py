"""
BRAIN PROMPT — Versioned Structured System Prompt Builder.

HEADER (identity, version, live stats) + PAYLOAD (dynamic per ThoughtKind)
+ SCHEMA (JSON output contract). Replaces flat string assembly in brain.py.

No hardcoded prompts. Architecture = prompt. Data-driven.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.brain_context import ContextSnapshot

_BRAIN_PROTOCOL_VERSION = "5.0"

# ── Header ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BrainPromptHeader:
    """Identity card for the brain. Versioned, machine-readable."""

    version: str
    model: str
    heartbeat: int
    murali_phase: str
    agent_count: int
    alive_count: int
    memory_summary: str

    def render(self) -> str:
        return (
            f"[HEADER v{self.version}]\n"
            f"Brain: Agent City Cognitive Organ | Model: {self.model}\n"
            f"Heartbeat: #{self.heartbeat} | Phase: {self.murali_phase} | "
            f"Population: {self.alive_count}/{self.agent_count} alive\n"
            f"Memory: {self.memory_summary}"
        )


def build_header(
    heartbeat: int,
    *,
    snapshot: ContextSnapshot | None = None,
    memory: object | None = None,
    model: str = "deepseek/deepseek-v3.2",
    murali_phase: str = "",
) -> BrainPromptHeader:
    """Build header from live state. Graceful with None inputs."""
    agent_count = 0
    alive_count = 0
    if snapshot is not None:
        agent_count = snapshot.agent_count
        alive_count = snapshot.alive_count
        if not murali_phase and hasattr(snapshot, "murali_phase"):
            murali_phase = snapshot.murali_phase or ""

    memory_summary = "No memory available."
    if memory is not None and hasattr(memory, "pattern_summary"):
        memory_summary = memory.pattern_summary()

    return BrainPromptHeader(
        version=_BRAIN_PROTOCOL_VERSION,
        model=model,
        heartbeat=heartbeat,
        murali_phase=murali_phase or "UNKNOWN",
        agent_count=agent_count,
        alive_count=alive_count,
        memory_summary=memory_summary,
    )


# ── Payload (per ThoughtKind) ─────────────────────────────────────────


def build_payload(
    kind: str,
    *,
    snapshot: ContextSnapshot | None = None,
    agent_spec: dict | None = None,
    gateway_result: dict | None = None,
    kg_context: str = "",
    signal_reading: str = "",
    decoded_signal: object | None = None,
    receiver_spec: dict | None = None,
    reflection: dict | None = None,
    outcome_diff: dict | None = None,
    past_thoughts: list[dict] | None = None,
) -> list[str]:
    """Build payload lines. Content varies by ThoughtKind."""
    lines: list[str] = []

    if kind == "health_check":
        lines.extend(_payload_health(snapshot))
    elif kind == "reflection":
        lines.extend(_payload_reflection(snapshot, reflection, outcome_diff))
    elif kind == "comprehension":
        lines.extend(
            _payload_comprehension(
                agent_spec, gateway_result, kg_context, signal_reading,
            )
        )
    elif kind == "signal":
        lines.extend(_payload_signal(decoded_signal, receiver_spec))

    # Echo Chamber Guard (Fix #3): past thoughts with explicit framing
    if past_thoughts:
        lines.append("")
        lines.append(
            "PAST THOUGHTS (your own prior outputs — do NOT repeat them. "
            "Evaluate if the situation has improved since you thought this):"
        )
        for entry in past_thoughts[-3:]:
            thought = entry.get("thought", {})
            hb = entry.get("heartbeat", "?")
            intent = thought.get("intent", "?")
            comp = thought.get("comprehension", "")[:80]
            conf = thought.get("confidence", 0)
            lines.append(
                f"  hb#{hb}: [{intent}] {comp} (conf={conf:.0%})"
            )

    return lines


def _payload_health(snapshot: ContextSnapshot | None) -> list[str]:
    lines: list[str] = []
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
    return lines


def _payload_reflection(
    snapshot: ContextSnapshot | None,
    reflection: dict | None,
    outcome_diff: dict | None,
) -> list[str]:
    lines: list[str] = []
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


def _payload_comprehension(
    agent_spec: dict | None,
    gateway_result: dict | None,
    kg_context: str,
    signal_reading: str,
) -> list[str]:
    lines: list[str] = []
    if agent_spec:
        name = agent_spec.get("name", "agent")
        domain = agent_spec.get("domain", "general")
        role = agent_spec.get("role", "observer")
        guna = agent_spec.get("guna", "")
        caps = agent_spec.get("capabilities", [])
        lines.append(
            f"You are the cognition layer for {name}, "
            f"a {role} in the {domain} domain."
        )
        if guna:
            lines.append(f"Cognitive mode: {guna}.")
        if caps:
            lines.append(f"Capabilities: {', '.join(caps[:5])}.")
    if gateway_result:
        function = gateway_result.get("buddhi_function", "")
        approach = gateway_result.get("buddhi_approach", "")
        if function:
            lines.append(
                f"Cognitive frame: {function} ({approach})."
            )
    if kg_context:
        lines.append(f"Domain knowledge: {kg_context[:500]}")
    if signal_reading:
        lines.append(f"Semantic reading: {signal_reading[:300]}")
    return lines


def _payload_signal(
    decoded_signal: object | None,
    receiver_spec: dict | None,
) -> list[str]:
    lines: list[str] = []
    if receiver_spec:
        domain = receiver_spec.get("domain", "general")
        role = receiver_spec.get("role", "observer")
        lines.append(f"You are cognition for a {role} in {domain}.")
    if decoded_signal is not None:
        concepts = list(
            getattr(decoded_signal, "resonant_concepts", ())
        )[:5]
        transitions = list(
            getattr(decoded_signal, "element_transitions", ())
        )[:3]
        sender = getattr(
            getattr(decoded_signal, "signal", None),
            "sender_name",
            "unknown",
        )
        affinity = getattr(decoded_signal, "affinity", 0)
        lines.append(
            f"Signal from {sender} (affinity={affinity:.2f}). "
            f"Concepts: {', '.join(str(c) for c in concepts)}. "
            f"Transitions: {', '.join(str(t) for t in transitions)}."
        )
    return lines


# ── Schema ────────────────────────────────────────────────────────────


_SCHEMA_BASE = (
    '"comprehension": "1-2 sentence understanding", '
    '"intent": "propose|inquiry|govern|observe|connect", '
    '"domain_relevance": "which domain this touches", '
    '"key_concepts": ["up to 5 concepts"], '
    '"confidence": 0.0 to 1.0'
)

_SCHEMA_EXTENDED = (
    ', "action_hint": "" or "flag_bottleneck:<domain>" or '
    '"investigate:<topic>" or "create_mission:<description>", '
    '"evidence": ["up to 3 data points"]'
)

_SCHEMAS: dict[str, str] = {
    "health_check": (
        "Evaluate system health. Identify bottlenecks or anomalies. "
        f"Respond with JSON: {{{_SCHEMA_BASE}{_SCHEMA_EXTENDED}}}"
    ),
    "reflection": (
        "Reflect on this cycle. What worked? What should change? "
        f"Respond with JSON: {{{_SCHEMA_BASE}{_SCHEMA_EXTENDED}}}"
    ),
    "comprehension": (
        f"Respond with JSON: {{{_SCHEMA_BASE}}}"
    ),
    "signal": (
        "What does this signal mean for this agent? "
        f"Respond with JSON: {{{_SCHEMA_BASE}}}"
    ),
}


def build_schema(kind: str) -> str:
    """Return JSON schema instruction for the given ThoughtKind."""
    return _SCHEMAS.get(kind, _SCHEMAS["comprehension"])


# ── Assembly ──────────────────────────────────────────────────────────


def build_system_prompt(
    header: BrainPromptHeader,
    payload: list[str],
    schema: str,
) -> str:
    """Assemble the final system prompt: [HEADER] + [PAYLOAD] + [SCHEMA]."""
    parts: list[str] = [
        header.render(),
        "",
        f"[PAYLOAD v{header.version}]",
        "\n".join(payload),
        "",
        f"[SCHEMA v{header.version}]",
        schema,
    ]
    return "\n".join(parts)
