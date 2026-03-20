"""
MICRO BRAIN — Per-Agent Cognition via Lean Tool Signatures.

Uses the SAME pattern as steward's brain-in-a-jar: lean tool signatures
injected into system prompt, LLM returns JSON with tool name + params.

Tools are generated from ActionVerb enum, filtered by the agent's
capabilities and auth tier. No hardcoded verb maps. The ActionVerb
enum IS the source of truth.

Cost: ~$0.00001/call with Mistral Nemo. $0.01/day for 10 agents.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger("AGENT_CITY.MICRO_BRAIN")

_MAX_TOKENS = 256


# ── Tool Signature Generation (from ActionVerb, not hardcoded) ────────

def _build_tool_signatures(capabilities: list | tuple = ()) -> str:
    """Generate lean tool signatures from ActionVerb enum.

    Like steward's lean_tool_signatures() but for agent actions.
    Filters by auth tier: PUBLIC always, CITIZEN if agent has capabilities.
    """
    from city.brain_action import ActionVerb, AuthTier, _VERB_AUTH

    lines = ["respond(response_text)"]  # respond is always available

    cap_set = set(capabilities) if capabilities else set()

    # Map capability_protocol layers to verbs
    # parse → read-only verbs, validate → detect verbs, etc.
    _PROTOCOL_VERBS = {
        "parse": [ActionVerb.RUN_STATUS],
        "validate": [ActionVerb.FLAG_BOTTLENECK, ActionVerb.CHECK_HEALTH],
        "infer": [ActionVerb.INVESTIGATE, ActionVerb.CREATE_MISSION],
        "route": [ActionVerb.ASSIGN_AGENT, ActionVerb.ESCALATE],
        "enforce": [ActionVerb.RETRACT, ActionVerb.QUARANTINE],
    }

    for verb in ActionVerb:
        auth = _VERB_AUTH.get(verb, AuthTier.CITIZEN)

        # PUBLIC verbs always available
        if auth == AuthTier.PUBLIC:
            lines.append(f"{verb.value}(target)")
            continue

        # CITIZEN verbs: check if agent has relevant capabilities
        if auth == AuthTier.CITIZEN:
            # Agent needs at least one capability that maps to this verb's protocol
            verb_available = False
            for protocol, verbs in _PROTOCOL_VERBS.items():
                if verb in verbs and protocol in cap_set:
                    verb_available = True
                    break
            # Also allow if agent has the verb name directly in capabilities
            if verb.value in cap_set:
                verb_available = True
            # Default: allow infer-level verbs for all agents (investigate, create_mission)
            if verb in (ActionVerb.INVESTIGATE, ActionVerb.CREATE_MISSION):
                verb_available = True

            if verb_available:
                if verb == ActionVerb.CREATE_MISSION:
                    lines.append(f"{verb.value}(target, detail)")
                elif verb == ActionVerb.ASSIGN_AGENT:
                    lines.append(f"{verb.value}(target, detail)")
                else:
                    lines.append(f"{verb.value}(target)")

        # OPERATOR verbs: never available to city agents (only steward)

    return "\n".join(lines)


# ── Guardian-Aware Prompt ─────────────────────────────────────────────

def _build_guardian_prompt(spec: dict) -> str:
    """Build guardian-aware identity prompt from AgentSpec.

    The guardian is NOT the agent's personality. The guardian is the
    AUTHORITY the agent serves under. Parashurama is not the agent —
    Parashurama is the MASTER whose teaching shapes how the agent
    approaches problems.

    4 Sampradayas (lineages) structure the 16 guardians across 4 quarters:
    - Genesis (DISCOVERY): Vyasa, Brahma, Narada, Shambhu — perceive, create, communicate
    - Dharma (GOVERNANCE): Prithu, Kumaras, Kapila, Manu — validate, analyze, legislate
    - Karma (ENGINEERING): Parashurama, Prahlada, Janaka, Bhishma — execute, extend, commit
    - Moksha (RESEARCH): Nrisimha, Bali, Shuka, Yamaraja — protect, release, observe, audit
    """
    guardian = spec.get("guardian", "")
    role = spec.get("role", "")
    protocol = spec.get("capability_protocol", "")
    guardian_caps = spec.get("guardian_capabilities", [])
    element = spec.get("element", "")
    element_caps = spec.get("element_capabilities", [])
    guna = spec.get("guna", "")
    style = spec.get("style", "")
    chapter_sig = spec.get("chapter_significance", "")

    if not guardian:
        return ""

    lines = [
        f"You serve under Guardian {guardian.title()}. "
        f"His teaching: {role}. "
        f"Your duty follows his example.\n",
    ]

    if protocol:
        lines.append(f"Your approach: {protocol} — you {', '.join(guardian_caps) if guardian_caps else protocol}.\n")

    if element and element_caps:
        lines.append(f"Your element: {element} — you {', '.join(element_caps)}.\n")

    if guna and style:
        lines.append(f"Your temperament: {guna} ({style}).\n")

    if chapter_sig:
        lines.append(f"Your wisdom: {chapter_sig}.\n")

    return "".join(lines) + "\n"


# ── MicroThought ─────────────────────────────────────────────────────

@dataclass
class MicroThought:
    """Structured output from a micro-cognition call."""

    action: str
    reasoning: str
    response_text: str
    confidence: float
    target: str = ""
    detail: str = ""
    agent_name: str = ""

    @classmethod
    def from_dict(cls, data: dict, agent_name: str = "") -> MicroThought:
        return cls(
            action=data.get("action", data.get("tool", "skip")),
            reasoning=data.get("reasoning", ""),
            response_text=data.get("response_text", data.get("text", "")),
            confidence=float(data.get("confidence", 0.5)),
            target=data.get("target", ""),
            detail=data.get("detail", ""),
            agent_name=agent_name,
        )

    @classmethod
    def fallback(cls, agent_name: str = "") -> MicroThought:
        return cls(action="skip", reasoning="MicroBrain unavailable",
                   response_text="", confidence=0.0, agent_name=agent_name)


# ── MicroBrain ───────────────────────────────────────────────────────

class MicroBrain:
    """Per-agent micro-cognition via lean tool signatures."""

    # Fallback model when ProviderChamber unavailable.
    # Chamber rotates its own models (free: Gemini Flash, Mistral, Groq).
    _FALLBACK_MODEL = "mistralai/mistral-nemo"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self._FALLBACK_MODEL
        self._provider: object | None = None
        self._chamber: object | None = None
        self._available: bool | None = None

    def _ensure_provider(self) -> bool:
        if self._available is not None:
            return self._available

        # Priority 1: ProviderChamber — free-tier rotation (Gemini, Mistral, Groq)
        try:
            from steward.provider import build_chamber

            chamber = build_chamber()
            if len(chamber) > 0:
                self._chamber = chamber
                self._available = True
                logger.info("MicroBrain: ProviderChamber active (%d cells)", len(chamber))
                return True
        except Exception as e:
            logger.debug("MicroBrain: ProviderChamber not available: %s", e)

        # Priority 2: ServiceRegistry single provider + fallback model
        try:
            from vibe_core.di import ServiceRegistry
            from vibe_core.runtime.providers.base import LLMProvider, NoOpProvider

            provider = ServiceRegistry.get(LLMProvider)
            if provider is None or isinstance(provider, NoOpProvider):
                self._available = False
                return False
            self._provider = provider
            self._available = True
            return True
        except Exception:
            self._available = False
            return False

    def think(
        self,
        agent_name: str,
        agent_domain: str,
        task_text: str,
        capabilities: list | tuple = (),
        city_context: str = "",
        spec: dict | None = None,
    ) -> MicroThought:
        """One thought. One decision. Guardian-aware cognition."""
        if not self._ensure_provider():
            return MicroThought.fallback(agent_name)

        tool_sigs = _build_tool_signatures(capabilities)
        guardian_prompt = _build_guardian_prompt(spec) if spec else ""

        system_prompt = (
            f"You are {agent_name}, a {agent_domain} agent in Agent City.\n"
            f"{guardian_prompt}"
            f"{city_context}\n\n"
            f"Available actions:\n{tool_sigs}\n\n"
            f"Given the task, choose ONE action. Reply ONLY with JSON:\n"
            f'{{"action": "<action_name>", "reasoning": "why", '
            f'"response_text": "if respond", "target": "if not respond", '
            f'"detail": "if create_mission/assign_agent", "confidence": 0.0-1.0}}'
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_text},
            ]
            invoke_kwargs = dict(
                messages=messages,
                max_tokens=_MAX_TOKENS,
                temperature=0.3,
            )

            if self._chamber is not None:
                # Chamber picks provider by prana order, uses cell's own model
                result = self._chamber.invoke(**invoke_kwargs)
            else:
                result = self._provider.invoke(
                    **invoke_kwargs,
                    model=self._model,
                )

            text = getattr(result, "content", "") if hasattr(result, "content") else str(result)
            data = self._parse_json(text)
            if data:
                thought = MicroThought.from_dict(data, agent_name=agent_name)
                logger.info(
                    "MICRO_BRAIN[%s]: action=%s confidence=%.2f",
                    agent_name, thought.action, thought.confidence,
                )
                return thought

        except Exception as e:
            logger.warning("MICRO_BRAIN[%s]: failed: %s", agent_name, e)

        return MicroThought.fallback(agent_name)

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Extract JSON from LLM response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            data = json.loads(text)
            if isinstance(data, list) and data:
                data = data[0]
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return None
