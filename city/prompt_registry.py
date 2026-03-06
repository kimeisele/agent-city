"""
PROMPT REGISTRY — Plugin Architecture for Brain Prompt Building.

PromptBuilder protocol + PromptRegistry + PromptContext.
Mirrors PhaseHook pattern (6A): each ThoughtKind gets a dedicated builder.

brain_prompt.py delegates to PromptRegistry instead of monolithic if/elif.
brain.py uses PromptContext to eliminate per-method boilerplate.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from city.brain_context import ContextSnapshot

logger = logging.getLogger("AGENT_CITY.PROMPT_REGISTRY")


# ── PromptContext — All data a builder might need ─────────────────────


@dataclass
class PromptContext:
    """Typed bag of all data a PromptBuilder can draw from.

    Builders read what they need, ignore the rest. No **kwargs spaghetti.
    Every field has a safe default — builders never crash on missing data.
    """

    # System state
    snapshot: ContextSnapshot | None = None

    # Comprehension-specific
    agent_spec: dict | None = None
    gateway_result: dict | None = None
    kg_context: str = ""
    signal_reading: str = ""

    # Signal-specific
    decoded_signal: object | None = None
    receiver_spec: dict | None = None

    # Reflection-specific
    reflection: dict | None = None
    outcome_diff: dict | None = None

    # Critique-specific
    field_summary: str = ""

    # Echo chamber guard (all kinds)
    past_thoughts: list[dict] | None = None


# ── PromptBuilder Protocol ────────────────────────────────────────────


@runtime_checkable
class PromptBuilder(Protocol):
    """Protocol for ThoughtKind-specific prompt builders.

    Each builder produces:
    - payload: list[str] — content lines for the system prompt
    - schema: str — JSON output contract for this thought kind
    - user_message: str — the user-role message for the LLM call
    """

    @property
    def kind(self) -> str:
        """ThoughtKind string this builder handles."""
        ...

    def build_payload(self, ctx: PromptContext) -> list[str]:
        """Build payload lines from context."""
        ...

    def build_schema(self) -> str:
        """Return JSON schema instruction for this ThoughtKind."""
        ...

    def build_user_message(self, ctx: PromptContext) -> str:
        """Build the user-role message for the LLM call."""
        ...


# ── PromptRegistry — ThoughtKind → PromptBuilder ─────────────────────


class PromptRegistry:
    """Registry mapping ThoughtKind strings to PromptBuilder instances.

    Thread-safe for read (builders registered at boot, read during heartbeat).
    """

    def __init__(self) -> None:
        self._builders: dict[str, PromptBuilder] = {}

    def register(self, builder: PromptBuilder) -> None:
        """Register a builder. Overwrites existing for same kind."""
        kind = builder.kind
        if kind in self._builders:
            logger.debug("PromptRegistry: replacing builder for %s", kind)
        self._builders[kind] = builder
        logger.debug("PromptRegistry: registered builder for %s", kind)

    def get(self, kind: str) -> PromptBuilder | None:
        """Get builder for a ThoughtKind. Returns None if not registered."""
        return self._builders.get(kind)

    def build_payload(self, kind: str, ctx: PromptContext) -> list[str]:
        """Build payload via registered builder. Falls back to empty."""
        builder = self._builders.get(kind)
        if builder is None:
            logger.warning("PromptRegistry: no builder for kind=%s", kind)
            return []
        return builder.build_payload(ctx)

    def build_schema(self, kind: str) -> str:
        """Build schema via registered builder. Falls back to comprehension."""
        builder = self._builders.get(kind)
        if builder is None:
            # Fall back to comprehension if available
            builder = self._builders.get("comprehension")
        if builder is None:
            return ""
        return builder.build_schema()

    def build_user_message(self, kind: str, ctx: PromptContext) -> str:
        """Build user message via registered builder."""
        builder = self._builders.get(kind)
        if builder is None:
            return ""
        return builder.build_user_message(ctx)

    @property
    def kinds(self) -> list[str]:
        """List registered ThoughtKind strings."""
        return list(self._builders.keys())

    def __len__(self) -> int:
        return len(self._builders)


# ── Shared Schema Fragments ──────────────────────────────────────────
# Builders import these to compose their schemas. DRY, typed.

SCHEMA_BASE = (
    '"comprehension": "1-2 sentence understanding", '
    '"intent": "propose|inquiry|govern|observe|connect", '
    '"domain_relevance": "which domain this touches", '
    '"key_concepts": ["up to 5 concepts"], '
    '"confidence": 0.0 to 1.0'
)

def _build_schema_extended() -> str:
    """Dynamically build SCHEMA_EXTENDED from ActionVerb enum.

    Single Source of Truth: if a verb is added to brain_action.py,
    the LLM schema automatically includes it. No hardcoded drift.
    """
    from city.brain_action import ActionVerb

    # Build "verb:target" examples from the canonical enum
    _VERB_EXAMPLES: dict[str, str] = {
        "run_status": "run_status",
        "flag_bottleneck": "flag_bottleneck:<domain>",
        "check_health": "check_health:<domain>",
        "investigate": "investigate:<topic>",
        "create_mission": "create_mission:<description>",
        "assign_agent": "assign_agent:<agent_name>:<task>",
        "escalate": "escalate:<reason>",
        "retract": "retract:<comment_id>",
        "quarantine": "quarantine:<agent_name>",
    }

    # Build from enum — any verb without an explicit example uses "verb:<target>"
    examples = []
    for verb in ActionVerb:
        example = _VERB_EXAMPLES.get(verb.value, f"{verb.value}:<target>")
        examples.append(f'"{example}"')

    hint_values = " or ".join(examples)
    return (
        f', "action_hint": "" or {hint_values}, '
        '"evidence": ["up to 3 data points"]'
    )


SCHEMA_EXTENDED = _build_schema_extended()


# ── Echo Chamber Guard (shared across all builders) ──────────────────


def render_past_thoughts(past_thoughts: list[dict] | None) -> list[str]:
    """Render past thoughts section. Shared by all builders.

    Returns empty list if no past thoughts. Max 3 entries.
    """
    if not past_thoughts:
        return []

    lines: list[str] = [
        "",
        "PAST THOUGHTS (your own prior outputs — do NOT repeat them. "
        "Evaluate if the situation has improved since you thought this):",
    ]
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
