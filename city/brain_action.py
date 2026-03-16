"""
BRAIN ACTION — Typed Vocabulary for Brain Intent→Execution Bridge.

Schritt 2: Neurosymbolische Brücke. Replaces free-form action_hint strings
with typed, validated, machine-parseable BrainActions.

action_hint string "flag_bottleneck:engineering" becomes:
  BrainAction(verb=ActionVerb.FLAG_BOTTLENECK, target="engineering")

ActionVerb enum is THE vocabulary. Nothing the Brain says can bypass it.
If it's not in the enum, it doesn't execute.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.reactor import CityIntent

logger = logging.getLogger("AGENT_CITY.BRAIN_ACTION")


# ── ActionVerb: The Complete Vocabulary ──────────────────────────────
# Every verb the Brain is allowed to speak. If it's not here, it's mute.
# Derived from guardian capability_protocols: parse → validate → infer → route → enforce


class ActionVerb(StrEnum):
    """Typed vocabulary for Brain action_hints.

    Organized by Guardian capability_protocol layer:
      parse:    OBSERVE (read-only, no mutation)
      validate: FLAG_BOTTLENECK, CHECK_HEALTH (detect, report)
      infer:    INVESTIGATE, CREATE_MISSION (propose new work)
      route:    ASSIGN_AGENT, ESCALATE (redirect to entity)
      enforce:  RETRACT, QUARANTINE (mutate state, highest authority)
    """

    # parse — read-only
    RUN_STATUS = "run_status"

    # validate — detect + report
    FLAG_BOTTLENECK = "flag_bottleneck"
    CHECK_HEALTH = "check_health"

    # infer — propose new work
    INVESTIGATE = "investigate"
    CREATE_MISSION = "create_mission"

    # route — redirect to entity
    ASSIGN_AGENT = "assign_agent"
    ESCALATE = "escalate"

    # enforce — mutate state (requires highest confidence)
    RETRACT = "retract"
    QUARANTINE = "quarantine"


# ── Authority Tiers ──────────────────────────────────────────────────
# Maps verbs to minimum confidence and authorization level.
# parse/validate = always allowed. infer = needs citizen. enforce = needs operator.

class AuthTier(StrEnum):
    """Authorization tier for action execution."""

    PUBLIC = "public"        # Anyone can trigger (read-only)
    CITIZEN = "citizen"      # Requires citizen or operator
    OPERATOR = "operator"    # Requires operator (state-mutating)


_VERB_AUTH: dict[ActionVerb, AuthTier] = {
    ActionVerb.RUN_STATUS: AuthTier.PUBLIC,
    ActionVerb.FLAG_BOTTLENECK: AuthTier.PUBLIC,
    ActionVerb.CHECK_HEALTH: AuthTier.PUBLIC,
    ActionVerb.INVESTIGATE: AuthTier.CITIZEN,
    ActionVerb.CREATE_MISSION: AuthTier.CITIZEN,
    ActionVerb.ASSIGN_AGENT: AuthTier.CITIZEN,
    ActionVerb.ESCALATE: AuthTier.CITIZEN,
    ActionVerb.RETRACT: AuthTier.OPERATOR,
    ActionVerb.QUARANTINE: AuthTier.OPERATOR,
}

# Minimum confidence for enforcement verbs (retract/quarantine)
_ENFORCE_MIN_CONFIDENCE = 0.7

# Verbs that are read-only (no state mutation)
READ_ONLY_VERBS: frozenset[ActionVerb] = frozenset({
    ActionVerb.RUN_STATUS,
    ActionVerb.CHECK_HEALTH,
})


# ── BrainAction: Parsed, Validated Action ────────────────────────────


@dataclass(frozen=True)
class BrainAction:
    """Typed, validated action parsed from action_hint string.

    Immutable. Machine-parseable. Bridges Brain → CityReactor.
    """

    verb: ActionVerb
    target: str = ""          # Domain, topic, agent_name, comment_id, etc.
    detail: str = ""          # Additional info (task description for assign_agent)
    source_confidence: float = 0.0  # From the originating Thought

    @property
    def auth_tier(self) -> AuthTier:
        """Required authorization tier for this action."""
        return _VERB_AUTH.get(self.verb, AuthTier.CITIZEN)

    @property
    def is_read_only(self) -> bool:
        """True if this action doesn't mutate state."""
        return self.verb in READ_ONLY_VERBS

    @property
    def is_enforcement(self) -> bool:
        """True if this is a state-mutating enforcement action."""
        return self.auth_tier == AuthTier.OPERATOR

    @property
    def confidence_sufficient(self) -> bool:
        """True if source confidence meets the verb's threshold."""
        if self.is_enforcement:
            return self.source_confidence >= _ENFORCE_MIN_CONFIDENCE
        return True

    def to_city_intent_signal(self) -> str:
        """Convert to CityIntent signal string for CityAttention routing.

        Format: "brain:{verb}" — distinct namespace from reactor pain signals.
        """
        return f"brain:{self.verb.value}"

    def to_city_intent(self, source: str = "brain", **extra_context) -> "CityIntent":
        """Convert to a CityIntent for unified executor dispatch.

        Schritt 6B: Bridges BrainAction → CityIntent → CityIntentExecutor.
        """
        from city.reactor import CityIntent
        ctx = {
            "target": self.target,
            "detail": self.detail,
            "source": source,
            "confidence": self.source_confidence,
        }
        ctx.update(extra_context)
        return CityIntent(
            signal=self.to_city_intent_signal(),
            priority="high" if self.is_enforcement else "normal",
            context=ctx,
        )

    def to_ops_string(self, context_suffix: str = "") -> str:
        """Format for operations log."""
        parts = [f"brain_action:{self.verb.value}"]
        if self.target:
            parts.append(self.target[:40])
        if context_suffix:
            parts.append(context_suffix)
        return ":".join(parts)


# ── ActionParser: String → BrainAction ───────────────────────────────


def parse_action_hint(
    hint: str,
    *,
    confidence: float = 0.0,
) -> BrainAction | None:
    """Parse a free-form action_hint string into a typed BrainAction.

    Returns None if:
      - hint is empty
      - verb is not in ActionVerb vocabulary (unknown = rejected)

    The Brain can only speak words we understand. Everything else is silence.
    """
    if not hint or not hint.strip():
        return None

    hint = hint.strip()

    # Special case: bare verb with no colon
    if hint == "run_status":
        return BrainAction(
            verb=ActionVerb.RUN_STATUS,
            source_confidence=confidence,
        )

    # Standard format: "verb:target" or "verb:target:detail"
    if ":" not in hint:
        # Try as bare verb
        try:
            verb = ActionVerb(hint)
            return BrainAction(verb=verb, source_confidence=confidence)
        except ValueError:
            logger.debug("Unknown action_hint verb: %s", hint[:40])
            return None

    parts = hint.split(":", 1)
    verb_str = parts[0].strip()
    remainder = parts[1].strip() if len(parts) > 1 else ""

    try:
        verb = ActionVerb(verb_str)
    except ValueError:
        logger.debug("Unknown action_hint verb: %s", verb_str[:40])
        return None

    # assign_agent has special format: "assign_agent:agent_name:task"
    if verb == ActionVerb.ASSIGN_AGENT and ":" in remainder:
        agent_parts = remainder.split(":", 1)
        return BrainAction(
            verb=verb,
            target=agent_parts[0].strip(),
            detail=agent_parts[1].strip() if len(agent_parts) > 1 else "",
            source_confidence=confidence,
        )

    return BrainAction(
        verb=verb,
        target=remainder,
        source_confidence=confidence,
    )


# ── CityAttention Integration ────────────────────────────────────────
# Signal names for Brain-originated intents, registered in CityAttention.

BRAIN_INTENT_SIGNALS: dict[str, str] = {
    f"brain:{verb.value}": f"handle_brain_{verb.value}"
    for verb in ActionVerb
}
