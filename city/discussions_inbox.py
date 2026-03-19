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
    cartridge_cognition: dict | None = None,
) -> str | None:
    """Compose agent response as spec-driven prose.

    Every agent produces different output because every spec IS different.
    Uses: guardian_capabilities, element_capabilities, capability_protocol,
    chapter_significance, element, style, role, domain, guna.

    9A: Returns None if brain_thought is None — fail closed.
    The semantic translation layer is NOT an LLM; it must not post alone.
    """
    # MicroBrain bypass: if the agent already THOUGHT and has a response,
    # use it directly. The MicroBrain IS the cognition — it doesn't need
    # the CityBrain compose pipeline.
    if (
        cartridge_cognition is not None
        and cartridge_cognition.get("decision_mode") == "micro_brain"
        and cartridge_cognition.get("response_text")
    ):
        agent_name = spec.get("name", "Unknown")
        response_text = cartridge_cognition["response_text"]
        logger.info(
            "COMPOSE: MicroBrain response from %s (confidence=%.2f)",
            agent_name,
            cartridge_cognition.get("confidence", 0),
        )
        return f"**{agent_name}** — {response_text}"

    # 9A: Fail Closed — no Brain cognition AND no MicroBrain means no post
    if brain_thought is None:
        logger.debug(
            "COMPOSE: Suppressed post for %s — Brain offline (fail closed)",
            spec.get("name", "?"),
        )
        return None
    name = spec.get("name", "Unknown")
    domain = spec.get("domain", "general")
    role = spec.get("role", "agent")
    guna = spec.get("guna", "")
    element = spec.get("element", "")
    protocol = spec.get("capability_protocol", "")
    guardian_caps = spec.get("guardian_capabilities", [])
    element_caps = spec.get("element_capabilities", [])
    chapter_sig = spec.get("chapter_significance", "")
    style = spec.get("style", "")

    function = gateway_result.get("buddhi_function", "")
    verb = _FUNCTION_VERB.get(function, "observe")
    frame = _GUNA_FRAME.get(guna, "Note")

    # Identity line
    parts = [f"**{name}** — {role} ({domain})"]

    # Semantic translation (translate_for_agent) REMOVED from external surfaces.
    # It produces Mahamantra resonance output ("devotional service, regulations
    # of the scriptures") which is for INTERNAL agent-to-agent communication,
    # not for Discussion comments that humans and external agents read.
    # MicroBrain responses go through the compose gate above (line ~157).
    # This path uses clean spec-derived text only.
    if protocol and element:
        parts.append(
            f"\n**{frame}**: `{element}` · `{protocol}`"
            f" — I can {verb} this from the {domain} perspective."
        )
    else:
        parts.append(f"\n**{frame}**: I can {verb} this from the {domain} perspective.")

    # Capabilities block: what this agent specifically brings
    if guardian_caps or element_caps:
        skills = []
        if guardian_caps:
            skills.append(f"**Specialization**: {', '.join(guardian_caps[:3])}")
        if element_caps:
            skills.append(f"**Base skills**: {', '.join(element_caps[:3])}")
        parts.append("\n" + " | ".join(skills))

    # Chapter knowledge (unique per agent)
    if chapter_sig:
        parts.append(f"*Drawing from: {chapter_sig}*")

    # 7A-4: Cartridge cognitive output (agent-specific process() result)
    if cartridge_cognition and isinstance(cartridge_cognition, dict):
        cog_fn = cartridge_cognition.get("function", "")
        cog_approach = cartridge_cognition.get("approach", "")
        cog_status = cartridge_cognition.get("status", "")
        if cog_fn or cog_approach:
            cog_parts = []
            if cog_fn:
                cog_parts.append(f"cognitive function: {cog_fn}")
            if cog_approach:
                cog_parts.append(f"approach: {cog_approach}")
            parts.append(f"\n> {' | '.join(cog_parts)}")

    # Brain comprehension (LLM cognition, when available)
    if brain_thought is not None:
        parts.append(brain_thought.format_for_post())

    # 7D-2: Routing transparency — why this agent was chosen
    routing_score = gateway_result.get("routing_score")
    routing_intent = gateway_result.get("routing_intent", "")
    if routing_score is not None:
        parts.append(f"\n*Routed: score={routing_score}, intent={routing_intent}*")

    # City stats (concise)
    alive = stats.get("active", 0) + stats.get("citizen", 0)
    total = stats.get("total", 0)
    parts.append(f"*{alive}/{total} agents active*")

    return "\n".join(parts)


# -- Dispatcher --------------------------------------------------------------


def dispatch_discussion(
    signal: DiscussionSignal,
    gateway_result: GatewayResult,
    agent_spec: dict,
    city_stats: dict,
    semantic_signal: object | None = None,
    brain_thought: Thought | None = None,
    cartridge_cognition: dict | None = None,
) -> AgentDiscussionResponse | None:
    """Route a discussion signal to spec-driven composition and build response.

    When semantic_signal (SemanticSignal) is provided, the response composition
    uses the signal protocol for richer, coordinate-decoded readings.
    When cartridge_cognition is provided, the agent's Cartridge process() output
    is woven into the response for agent-specific cognitive framing.

    9A: Returns None if Brain is offline (fail closed).
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
        cartridge_cognition=cartridge_cognition,
    )

    # 9A: Fail closed — no body means Brain was offline
    if body is None:
        return None

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


# Internal operation names → human-readable descriptions
_OPERATION_PROSE: dict[str, str] = {
    "council_propose": "submitted a governance proposal",
    "create_mission": "created a new mission",
    "emit_observation": "shared an observation",
    "nadi_dispatch": "relayed a signal to other agents",
    "trigger_audit": "triggered a code audit",
    "trigger_heal": "initiated a healing action",
}


def build_action_report(
    spec: dict,
    cognitive_action: dict,
    mission_id: str,
) -> str:
    """Build human-readable report when agent executes a cognitive action.

    No raw internal state. No word-salad signals. Just clear prose
    describing what the agent did and why.
    """
    name = spec.get("name", "Unknown")
    domain = spec.get("domain", "general")
    role = spec.get("role", "agent")

    operation = cognitive_action.get("_operation", "")
    action_desc = _OPERATION_PROSE.get(operation, f"performed action: {operation}")
    mission_short = mission_id.replace("_", " ").replace("mission ", "")

    lines = [
        f"**{name}** ({role}, {domain}) {action_desc}.",
        f"Mission: *{mission_short}*",
    ]

    return "\n".join(lines)
