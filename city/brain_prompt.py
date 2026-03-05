"""
BRAIN PROMPT — Thin Dispatcher + Header/Assembly.

8I: Plugin Architecture. All payload logic lives in city/prompt_builders/*.
This file delegates to PromptRegistry. Public API unchanged:
  build_header(), build_payload(), build_schema(), build_system_prompt().

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.brain_context import ContextSnapshot

from city.prompt_registry import PromptContext, PromptRegistry, render_past_thoughts

logger = logging.getLogger("AGENT_CITY.BRAIN_PROMPT")

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


# ── PromptRegistry Singleton ──────────────────────────────────────────


def _build_registry() -> PromptRegistry:
    """Build and populate the default PromptRegistry.

    Called once per process. Each ThoughtKind gets a dedicated builder.
    New kinds = new builder file in city/prompt_builders/, register here.
    """
    from city.prompt_builders.comprehension import ComprehensionBuilder
    from city.prompt_builders.critique import CritiqueBuilder
    from city.prompt_builders.health import HealthCheckBuilder
    from city.prompt_builders.insight import InsightBuilder
    from city.prompt_builders.reflection import ReflectionBuilder
    from city.prompt_builders.signal import SignalBuilder

    registry = PromptRegistry()
    registry.register(ComprehensionBuilder())
    registry.register(HealthCheckBuilder())
    registry.register(ReflectionBuilder())
    registry.register(InsightBuilder())
    registry.register(CritiqueBuilder())
    registry.register(SignalBuilder())
    return registry


_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    """Get or create the singleton PromptRegistry."""
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


# ── Payload (backward-compatible dispatcher) ─────────────────────────


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
    field_summary: str = "",
) -> list[str]:
    """Build payload lines. Delegates to PromptRegistry builders.

    Public API unchanged — all callers continue to work.
    """
    ctx = PromptContext(
        snapshot=snapshot,
        agent_spec=agent_spec,
        gateway_result=gateway_result,
        kg_context=kg_context,
        signal_reading=signal_reading,
        decoded_signal=decoded_signal,
        receiver_spec=receiver_spec,
        reflection=reflection,
        outcome_diff=outcome_diff,
        field_summary=field_summary,
        past_thoughts=past_thoughts,
    )

    registry = get_prompt_registry()
    lines = registry.build_payload(kind, ctx)

    # Echo Chamber Guard (shared, appended after builder payload)
    lines.extend(render_past_thoughts(past_thoughts))

    return lines


def build_schema(kind: str) -> str:
    """Return JSON schema instruction for the given ThoughtKind."""
    registry = get_prompt_registry()
    return registry.build_schema(kind)


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
