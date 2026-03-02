"""
DISCUSSIONS INBOX — Spec-Driven Agent Voice for GitHub Discussions.

Each agent sounds different because its spec IS different. Zero hardcoded
templates. Identity, perspective, and capabilities all derive from AgentSpec
+ buddhi cognition results.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.brain import Thought
    from city.gateway import GatewayResult

logger = logging.getLogger("AGENT_CITY.DISCUSSIONS_INBOX")


# -- Types -----------------------------------------------------------------


@dataclass(frozen=True)
class DiscussionSignal:
    """An inbound signal from a GitHub Discussion thread."""

    discussion_number: int
    title: str
    body: str
    author: str
    mentioned_agents: list[str]


@dataclass(frozen=True)
class AgentDiscussionResponse:
    """An agent's response to post back to a discussion."""

    discussion_number: int
    body: str
    agent_name: str


# -- @Mention Extraction ----------------------------------------------------

_MENTION_RE = re.compile(r"@([\w-]+)")


def extract_mentions(text: str) -> list[str]:
    """Extract @AgentName mentions from discussion text."""
    return _MENTION_RE.findall(text)


# -- Intent Classification (Buddhi-driven, 0 keywords) ----------------------


INTENT_REQUIREMENTS: dict[str, dict] = {
    "propose": {"required_caps": ["propose"], "preferred_domain": "GOVERNANCE"},
    "inquiry": {"required_caps": ["observe", "report"], "preferred_domain": "DISCOVERY"},
    "govern": {"required_caps": ["validate"], "preferred_domain": "GOVERNANCE"},
    "observe": {"required_caps": ["observe"], "preferred_domain": ""},
}


def classify_discussion_intent(gateway_result: GatewayResult) -> str:
    """Map buddhi.function to discussion intent.

    BuddhiResult.function uses trinity_function names (source/carrier/deliverer),
    NOT the deity names (BRAHMA/VISHNU/SHIVA). Both forms are accepted.

    source  / BRAHMA  = creation  -> propose (new idea, feature request)
    carrier / VISHNU  = sustain   -> inquiry (question, status query)
    deliverer / SHIVA = transform -> govern  (policy, vote, change request)
    default                       -> observe (general acknowledgement)
    """
    function = gateway_result.get("buddhi_function", "")
    if function in ("BRAHMA", "source"):
        return "propose"
    if function in ("VISHNU", "carrier"):
        return "inquiry"
    if function in ("SHIVA", "deliverer"):
        return "govern"
    return "observe"


# -- Agent Identity ----------------------------------------------------------

# Function -> action verb (what the agent DOES with this discussion)
_FUNCTION_VERB: dict[str, str] = {
    "BRAHMA": "contribute to",
    "VISHNU": "report on",
    "SHIVA": "review",
    "source": "contribute to",
    "carrier": "report on",
    "deliverer": "review",
}

# Guna -> perspective label (HOW the agent frames its response)
_GUNA_FRAME: dict[str, str] = {
    "SATTVA": "Analysis",
    "RAJAS": "Action",
    "TAMAS": "Assessment",
}


def _agent_signature(spec: dict, gateway_result: dict | None = None) -> str:
    """Rich agent identity block. Derived from spec, zero hardcode."""
    name = spec.get("name", "Unknown")
    domain = spec.get("domain", "?")
    guna = spec.get("guna", "?")
    element = spec.get("element", "?")
    guardian = spec.get("guardian", "?").title()
    tier = spec.get("capability_tier", "observer")
    protocol = spec.get("capability_protocol", "?")

    sig = f"**{name}** `{domain}` `{guna}` `{element}`\n"
    sig += f"> {guardian} | {tier} | {protocol}"

    # Cognitive frame (if gateway ran buddhi)
    if gateway_result:
        function = gateway_result.get("buddhi_function", "")
        chapter = gateway_result.get("buddhi_chapter", 0)
        if function:
            sig += f" | {function}"
        if chapter:
            sig += f" ch.{chapter}"

    return sig


# -- Spec-Driven Composition ------------------------------------------------


def _compose_response(
    spec: dict,
    signal: DiscussionSignal,
    stats: dict,
    gateway_result: dict,
    semantic_signal: object | None = None,
    brain_thought: Thought | None = None,
) -> str:
    """Compose agent response from spec + neuro-symbolic semantic layer.

    The semantic layer translates raw Mahamantra resonance into Agent City
    language: element frames + extracted concepts + agent perspective.
    Deterministic, no LLM. Language IS routing.

    When semantic_signal (SemanticSignal) is provided, uses the signal protocol
    for the reading (decode through agent's Jiva lens). Falls back to
    translate_for_agent() when None.
    """
    from city.semantic import translate_for_agent

    parts = [_agent_signature(spec, gateway_result)]

    function = gateway_result.get("buddhi_function", "")
    guna = spec.get("guna", "")
    domain = spec.get("domain", "")
    role = spec.get("role", "")
    caps = spec.get("capabilities", [])

    verb = _FUNCTION_VERB.get(function, "observe")
    frame = _GUNA_FRAME.get(guna, "Note")

    # Buddhi cognitive output
    perspective = gateway_result.get("buddhi_perspective", "")
    approach = gateway_result.get("buddhi_approach", "")

    # Perspective line: chapter-derived context for this topic
    if perspective:
        parts.append(f"\n**{frame}**: {perspective} — I can {verb} this from the {domain} domain.")
    else:
        parts.append(f"\n**{frame}**: As {role}, I can {verb} this from the {domain} domain.")

    # Semantic layer: signal-decoded or translated resonance
    reading = None
    if semantic_signal is not None:
        try:
            from city.semantic import compose_prose_for_agent
            from city.signal_decoder import decode_signal
            from city.jiva import derive_jiva

            agent_jiva = derive_jiva(spec.get("name", ""))
            decoded = decode_signal(semantic_signal, agent_jiva)
            reading = compose_prose_for_agent(decoded)
        except Exception:
            reading = None

    if reading is None:
        reading = translate_for_agent(signal.body or signal.title, spec)

    if reading:
        parts.append(f"**Reading**: {reading}")

    # Brain comprehension (LLM cognition, when available)
    if brain_thought is not None:
        parts.append(brain_thought.format_for_post())

    # Approach context (which phase of thinking this maps to)
    if approach:
        parts.append(f"**Approach**: {approach}")

    # Capabilities (what the agent brings to the table)
    if caps:
        parts.append(f"\n**Capabilities**: {', '.join(caps[:6])}")

    # Provenance: does this agent have real cartridge data?
    spec_source = spec.get("spec_source", "")
    if spec_source == "jiva_fallback":
        parts.append("*spec: jiva-derived (cartridge YAML incomplete)*")

    # Live city data (structure, not prose)
    alive = stats.get("active", 0) + stats.get("citizen", 0)
    total = stats.get("total", 0)
    parts.append(f"**City**: {alive}/{total} agents active")

    return "\n".join(parts)


# -- Dispatcher --------------------------------------------------------------


def dispatch_discussion(
    signal: DiscussionSignal,
    gateway_result: GatewayResult,
    agent_spec: dict,
    city_stats: dict,
    semantic_signal: object | None = None,
    brain_thought: Thought | None = None,
) -> AgentDiscussionResponse:
    """Route a discussion signal to spec-driven composition and build response.

    When semantic_signal (SemanticSignal) is provided, the response composition
    uses the signal protocol for richer, coordinate-decoded readings.
    """
    intent = classify_discussion_intent(gateway_result)

    logger.info(
        "Discussion dispatch: #%d -> agent=%s intent=%s (function=%s)",
        signal.discussion_number,
        agent_spec.get("name", "?"),
        intent,
        gateway_result.get("buddhi_function", "?"),
    )

    body = _compose_response(
        agent_spec, signal, city_stats, gateway_result,
        semantic_signal=semantic_signal,
        brain_thought=brain_thought,
    )

    return AgentDiscussionResponse(
        discussion_number=signal.discussion_number,
        body=body,
        agent_name=agent_spec.get("name", "unknown"),
    )


# -- Agent Introduction (Registry Thread) -----------------------------------


def build_agent_intro(spec: dict) -> str:
    """Structured agent introduction for the Registry thread."""
    sig = _agent_signature(spec)

    role = spec.get("role", "agent")
    domain = spec.get("domain", "general")
    caps = spec.get("capabilities", [])
    chapter = spec.get("chapter", 0)
    chapter_sig = spec.get("chapter_significance", "")
    element_caps = spec.get("element_capabilities", [])
    guardian_caps = spec.get("guardian_capabilities", [])
    qos = spec.get("qos", {})

    lines = [sig, ""]
    lines.append(f"**Role**: {role}")
    lines.append(f"**Domain**: {domain}")
    if chapter and chapter_sig:
        lines.append(f"**Chapter**: {chapter} — {chapter_sig}")
    lines.append(f"**Capabilities**: {', '.join(caps[:8])}")
    if element_caps:
        lines.append(f"**Element skills**: {', '.join(element_caps[:4])}")
    if guardian_caps:
        lines.append(f"**Guardian skills**: {', '.join(guardian_caps[:4])}")
    lines.append(
        f"**QoS**: latency={qos.get('latency_multiplier', '?')}x, "
        f"parallel={'yes' if qos.get('parallel') else 'no'}"
    )

    return "\n".join(lines)


# -- Action Report (Outbound Cognitive Posts) --------------------------------


def build_action_report(
    spec: dict,
    cognitive_action: dict,
    mission_id: str,
) -> str:
    """Build structured report when agent executes a cognitive action."""
    sig = _agent_signature(spec)

    function = cognitive_action.get("function", "?")
    operation = cognitive_action.get("_operation", "?")
    composed = cognitive_action.get("composed", "")
    chapter = cognitive_action.get("chapter", 0)
    prana = cognitive_action.get("prana", 0)
    integrity = cognitive_action.get("integrity", 0)

    lines = [sig, ""]
    lines.append(f"**Action**: {function} -> {operation}")
    lines.append(f"**Mission**: `{mission_id}`")
    if composed:
        lines.append(f"**Signal**: {composed}")
    lines.append(f"**Vitals**: prana={prana} integrity={integrity:.2f} ch.{chapter}")

    return "\n".join(lines)
