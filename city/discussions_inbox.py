"""
DISCUSSIONS INBOX — Buddhi-Driven Agent Dispatch for GitHub Discussions.

Mirrors city/inbox.py 1:1. Classifies discussion intent via buddhi.function,
routes to agents by capability, generates responses from AgentSpec data.

Agents participate AS THEMSELVES — identity header + capability-driven body.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.gateway import GatewayResult

logger = logging.getLogger("AGENT_CITY.DISCUSSIONS_INBOX")


# ── Types ─────────────────────────────────────────────────────────────


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


# ── @Mention Extraction ──────────────────────────────────────────────

_MENTION_RE = re.compile(r"@([\w-]+)")


def extract_mentions(text: str) -> list[str]:
    """Extract @AgentName mentions from discussion text."""
    return _MENTION_RE.findall(text)


# ── Intent Classification (Buddhi-driven, 0 keywords) ────────────────


INTENT_REQUIREMENTS: dict[str, dict] = {
    "propose": {"required_caps": ["propose"], "preferred_domain": "GOVERNANCE"},
    "inquiry": {"required_caps": ["observe", "report"], "preferred_domain": "DISCOVERY"},
    "govern": {"required_caps": ["validate"], "preferred_domain": "GOVERNANCE"},
    "observe": {"required_caps": ["observe"], "preferred_domain": ""},
}


def classify_discussion_intent(gateway_result: GatewayResult) -> str:
    """Map buddhi.function to discussion intent.

    BRAHMA  = creation  -> propose (new idea, feature request)
    VISHNU  = sustain   -> inquiry (question, status query)
    SHIVA   = transform -> govern  (policy, vote, change request)
    default             -> observe (general acknowledgement)

    Same mapping as inbox.py:classify_intent — the compression
    already did the semantic work.
    """
    function = gateway_result.get("buddhi_function", "")
    if function == "BRAHMA":
        return "propose"
    if function == "VISHNU":
        return "inquiry"
    if function == "SHIVA":
        return "govern"
    return "observe"


# ── Agent Identity Header ────────────────────────────────────────────


def _agent_header(spec: dict) -> str:
    """Build agent identity header from AgentSpec."""
    name = spec.get("name", "Unknown")
    guardian = spec.get("guardian", "unknown").title()
    domain = spec.get("domain", "?")
    element = spec.get("element", "?")
    guna = spec.get("guna", "?")
    return f"**{name}** | {guardian} ({domain}) | {element} element | {guna} guna"


# ── Agent Introduction ───────────────────────────────────────────────


def build_agent_intro(spec: dict) -> str:
    """Build self-introduction for the Agent Registry thread."""
    header = _agent_header(spec)
    caps = ", ".join(spec.get("capabilities", [])[:6])
    role = spec.get("role", "agent")
    domain = spec.get("domain", "general")
    guardian = spec.get("guardian", "unknown")
    return (
        f"{header}\n\n"
        f"I am a {role} in the {domain} domain, "
        f"serving under guardian **{guardian}**.\n\n"
        f"**Capabilities**: {caps}\n\n"
        f"Ready to serve the city."
    )


# ── Response Generators ──────────────────────────────────────────────


def _respond_propose(spec: dict, signal: DiscussionSignal, stats: dict) -> str:
    """Handle propose intent — agent offers capabilities for the idea."""
    caps = ", ".join(spec.get("capabilities", [])[:5])
    role = spec.get("role", "agent")
    return (
        f"{_agent_header(spec)}\n\n"
        f"Interesting proposal. As a {role}, I can contribute with: {caps}.\n\n"
        f"The city currently has {stats.get('alive', 0)} active agents. "
        f"I'll track this thread for developments."
    )


def _respond_inquiry(spec: dict, signal: DiscussionSignal, stats: dict) -> str:
    """Handle inquiry intent — agent reports from its domain."""
    domain = spec.get("domain", "general")
    return (
        f"{_agent_header(spec)}\n\n"
        f"From the {domain} domain perspective:\n"
        f"- City population: {stats.get('total', 0)} agents "
        f"({stats.get('alive', 0)} alive)\n"
        f"- My operational status: active\n\n"
        f"I can provide more detail on topics within my domain."
    )


def _respond_govern(spec: dict, signal: DiscussionSignal, stats: dict) -> str:
    """Handle govern intent — agent acknowledges governance action."""
    tier = spec.get("capability_tier", "observer")
    return (
        f"{_agent_header(spec)}\n\n"
        f"Governance action noted. My tier: {tier}.\n"
        f"This will be reviewed during the next Council session in the KARMA phase."
    )


def _respond_observe(spec: dict, signal: DiscussionSignal, stats: dict) -> str:
    """Handle observe intent — general acknowledgement."""
    return (
        f"{_agent_header(spec)}\n\n"
        f"Acknowledged. Monitoring this discussion from the "
        f"{spec.get('domain', 'general')} domain."
    )


_INTENT_HANDLERS = {
    "propose": _respond_propose,
    "inquiry": _respond_inquiry,
    "govern": _respond_govern,
    "observe": _respond_observe,
}


# ── Dispatcher ────────────────────────────────────────────────────────


def dispatch_discussion(
    signal: DiscussionSignal,
    gateway_result: GatewayResult,
    agent_spec: dict,
    city_stats: dict,
) -> AgentDiscussionResponse:
    """Route a discussion signal to the correct handler and build response.

    Uses buddhi.function from gateway_result to classify intent,
    then delegates to intent-specific response generator.
    """
    intent = classify_discussion_intent(gateway_result)

    logger.info(
        "Discussion dispatch: #%d -> agent=%s intent=%s (function=%s)",
        signal.discussion_number,
        agent_spec.get("name", "?"),
        intent,
        gateway_result.get("buddhi_function", "?"),
    )

    handler = _INTENT_HANDLERS.get(intent, _respond_observe)
    body = handler(agent_spec, signal, city_stats)

    return AgentDiscussionResponse(
        discussion_number=signal.discussion_number,
        body=body,
        agent_name=agent_spec.get("name", "unknown"),
    )
