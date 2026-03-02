"""
BRAIN IN A JAR — LLM Cognition Organ for Agent City.

The brain READS, UNDERSTANDS, and THINKS. It does NOT act.
It does NOT generate content. It does NOT write posts.

Input: structured context (signals, discussions, agent spec, KG).
Output: structured cognition (comprehension, classification, reasoning).

Architecture builds the prompt. Zero hardcoded system prompts.
JSON Structured Output enforced via API (no text parsing).
12s timeout — OpenRouter aggregator needs headroom.

Model: deepseek/deepseek-v3.2 via OpenRouter (config/llm.yaml).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

logger = logging.getLogger("AGENT_CITY.BRAIN")

_BRAIN_TIMEOUT = 12  # seconds — OpenRouter aggregator needs headroom
_MAX_TOKENS = 512    # room for proper JSON with all fields


# ── Typed Intent ──────────────────────────────────────────────────────


class BrainIntent(StrEnum):
    """Cognitive intent classification. Deterministic vocabulary."""

    PROPOSE = "propose"    # New idea, feature, creation
    INQUIRY = "inquiry"    # Question, status query, information request
    GOVERN = "govern"      # Policy, vote, change request, review
    OBSERVE = "observe"    # General acknowledgement, monitoring
    CONNECT = "connect"    # Introduction, linking agents/domains


# ── Key Aliases (model says "understanding", we normalize) ────────────

_KEY_ALIASES: dict[str, str] = {
    # comprehension aliases
    "understanding": "comprehension",
    "summary": "comprehension",
    "analysis": "comprehension",
    "insight": "comprehension",
    # intent aliases
    "type": "intent",
    "action": "intent",
    "category": "intent",
    # domain_relevance aliases
    "domain": "domain_relevance",
    "relevance": "domain_relevance",
    "area": "domain_relevance",
    # key_concepts aliases
    "concepts": "key_concepts",
    "keywords": "key_concepts",
    "topics": "key_concepts",
    "tags": "key_concepts",
    # confidence aliases
    "score": "confidence",
    "certainty": "confidence",
}

_CANONICAL_KEYS = {"comprehension", "intent", "domain_relevance", "key_concepts", "confidence"}


def _normalize_keys(data: dict) -> dict:
    """Normalize aliased keys to canonical Thought field names."""
    normalized: dict = {}
    for key, value in data.items():
        canonical = _KEY_ALIASES.get(key, key)
        # First canonical hit wins (don't overwrite)
        if canonical in _CANONICAL_KEYS and canonical not in normalized:
            normalized[canonical] = value
    return normalized


def _normalize_intent(raw: str) -> BrainIntent:
    """Normalize raw intent string to BrainIntent enum. Defaults to OBSERVE."""
    cleaned = raw.strip().lower()
    try:
        return BrainIntent(cleaned)
    except ValueError:
        # Fuzzy match: "proposing" → PROPOSE, "question" → INQUIRY
        _INTENT_FUZZY: dict[str, BrainIntent] = {
            "create": BrainIntent.PROPOSE,
            "suggest": BrainIntent.PROPOSE,
            "proposing": BrainIntent.PROPOSE,
            "question": BrainIntent.INQUIRY,
            "ask": BrainIntent.INQUIRY,
            "query": BrainIntent.INQUIRY,
            "review": BrainIntent.GOVERN,
            "validate": BrainIntent.GOVERN,
            "policy": BrainIntent.GOVERN,
            "monitor": BrainIntent.OBSERVE,
            "watch": BrainIntent.OBSERVE,
            "report": BrainIntent.OBSERVE,
            "introduce": BrainIntent.CONNECT,
            "link": BrainIntent.CONNECT,
            "bridge": BrainIntent.CONNECT,
        }
        return _INTENT_FUZZY.get(cleaned, BrainIntent.OBSERVE)


# ── Thought (frozen, serializable, postable) ─────────────────────────


@dataclass(frozen=True)
class Thought:
    """Structured cognition output. NOT content. NOT prose.

    Serializable (to_dict), postable (format_for_post), transparent.
    """

    comprehension: str           # What the brain understood (1-2 sentences)
    intent: BrainIntent          # Typed intent classification
    domain_relevance: str        # Which city domain this touches
    key_concepts: tuple[str, ...]  # Extracted concepts (max 5, immutable)
    confidence: float            # 0.0-1.0

    def to_dict(self) -> dict[str, object]:
        """Serialize thought for storage, logging, feedback loops."""
        return {
            "comprehension": self.comprehension,
            "intent": self.intent.value,
            "domain_relevance": self.domain_relevance,
            "key_concepts": list(self.key_concepts),
            "confidence": self.confidence,
        }

    def format_for_post(self) -> str:
        """Format thought as structured text for discussion posting.

        This is the feedback loop entry point: posted thoughts become
        discussion content that can be scanned → comprehended → reacted to.
        """
        lines: list[str] = []
        if self.comprehension:
            lines.append(f"**Comprehension**: {self.comprehension}")
        if self.key_concepts:
            lines.append(f"**Concepts**: {', '.join(self.key_concepts)}")
        lines.append(
            f"**Intent**: {self.intent.value} "
            f"(confidence: {self.confidence:.0%})"
        )
        if self.domain_relevance:
            lines.append(f"**Domain**: {self.domain_relevance}")
        return "\n".join(lines)


# ── Protocol (typed interface for DI) ─────────────────────────────────


@runtime_checkable
class BrainProtocol(Protocol):
    """Protocol for brain cognition. Used for type-safe DI."""

    def comprehend_discussion(
        self,
        discussion_text: str,
        agent_spec: dict,
        gateway_result: dict,
        kg_context: str = "",
        signal_reading: str = "",
    ) -> Thought | None: ...

    def comprehend_signal(
        self,
        decoded_signal: object,
        receiver_spec: dict,
    ) -> Thought | None: ...


# ── CityBrain Implementation ─────────────────────────────────────────


class CityBrain:
    """Read-only LLM cognition. Receives context, returns structured thought.

    The brain is a jar. It has no hands, no mouth, no network access.
    It receives structured input and returns structured output.
    The architecture decides what to DO with the output.
    """

    def __init__(self) -> None:
        self._provider: object | None = None
        self._available: bool | None = None  # None = not checked yet
        self._model = "deepseek/deepseek-v3.2"

    def _ensure_provider(self) -> bool:
        """Lazy init. Returns False if no LLM available."""
        if self._available is not None:
            return self._available
        try:
            from vibe_core.runtime.providers.factory import get_llm_provider
            from vibe_core.runtime.providers.base import NoOpProvider

            provider = get_llm_provider()
            if isinstance(provider, NoOpProvider):
                logger.info("Brain: NoOpProvider detected — cognition offline")
                self._available = False
                return False
            self._provider = provider
            self._available = True
            logger.info("Brain: provider ready (%s)", type(provider).__name__)
            return True
        except Exception as e:
            logger.warning("Brain: provider init failed: %s", e)
            self._available = False
            return False

    def comprehend_discussion(
        self,
        discussion_text: str,
        agent_spec: dict,
        gateway_result: dict,
        kg_context: str = "",
        signal_reading: str = "",
    ) -> Thought | None:
        """Brain comprehends a discussion. Returns understanding, not content.

        Returns None if: LLM unavailable, timeout, or parse failure.
        Caller continues with deterministic path on None.
        """
        if not self._ensure_provider():
            return None

        # Build context-driven messages (architecture = prompt)
        system_parts: list[str] = []
        name = agent_spec.get("name", "agent")
        domain = agent_spec.get("domain", "general")
        role = agent_spec.get("role", "observer")
        guna = agent_spec.get("guna", "")
        caps = agent_spec.get("capabilities", [])

        system_parts.append(
            f"You are the cognition layer for {name}, a {role} in the {domain} domain."
        )
        if guna:
            system_parts.append(f"Cognitive mode: {guna}.")
        if caps:
            system_parts.append(f"Capabilities: {', '.join(caps[:5])}.")

        function = gateway_result.get("buddhi_function", "")
        approach = gateway_result.get("buddhi_approach", "")
        if function:
            system_parts.append(f"Cognitive frame: {function} ({approach}).")
        if kg_context:
            system_parts.append(f"Domain knowledge: {kg_context[:500]}")
        if signal_reading:
            system_parts.append(f"Semantic reading: {signal_reading[:300]}")

        system_parts.append(
            "Respond with JSON: "
            '{"comprehension": "1-2 sentence understanding", '
            '"intent": "propose|inquiry|govern|observe|connect", '
            '"domain_relevance": "which domain this touches", '
            '"key_concepts": ["up to 5 concepts"], '
            '"confidence": 0.0 to 1.0}'
        )

        messages = [
            {"role": "system", "content": " ".join(system_parts)},
            {"role": "user", "content": f"Comprehend this discussion:\n\n{discussion_text[:2000]}"},
        ]

        thought = self._invoke_and_parse(messages)
        if thought is not None:
            logger.info(
                "Brain comprehended discussion: intent=%s confidence=%.2f "
                "concepts=%s domain=%s",
                thought.intent.value,
                thought.confidence,
                list(thought.key_concepts),
                thought.domain_relevance,
            )
        return thought

    def comprehend_signal(
        self,
        decoded_signal: object,
        receiver_spec: dict,
    ) -> Thought | None:
        """Brain comprehends why a signal resonates with this receiver.

        Returns None if unavailable. Used for medium-affinity signals (0.3-0.8)
        where the deterministic layer can route but can't fully understand.
        """
        if not self._ensure_provider():
            return None

        domain = receiver_spec.get("domain", "general")
        role = receiver_spec.get("role", "observer")

        # Extract signal data
        concepts = list(getattr(decoded_signal, "resonant_concepts", ()))[:5]
        transitions = list(getattr(decoded_signal, "element_transitions", ()))[:3]
        sender = getattr(
            getattr(decoded_signal, "signal", None), "sender_name", "unknown"
        )
        affinity = getattr(decoded_signal, "affinity", 0)

        system_msg = (
            f"You are cognition for a {role} in {domain}. "
            f"A signal arrived from {sender} (affinity={affinity:.2f}). "
            f"Concepts: {', '.join(concepts)}. Transitions: {', '.join(transitions)}. "
            "Respond with JSON: "
            '{"comprehension": "1-2 sentence understanding", '
            '"intent": "propose|inquiry|govern|observe|connect", '
            '"domain_relevance": "which domain", '
            '"key_concepts": ["up to 5"], "confidence": 0.0 to 1.0}'
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": "What does this signal mean for this agent?"},
        ]

        thought = self._invoke_and_parse(messages)
        if thought is not None:
            logger.info(
                "Brain comprehended signal from %s: intent=%s confidence=%.2f",
                sender,
                thought.intent.value,
                thought.confidence,
            )
        return thought

    def _invoke_and_parse(self, messages: list[dict]) -> Thought | None:
        """Invoke LLM with JSON mode + timeout. Parse into Thought.

        Logs failures transparently — never silent.
        """
        try:
            response = self._provider.invoke(  # type: ignore[union-attr]
                messages=messages,
                model=self._model,
                max_tokens=_MAX_TOKENS,
                temperature=0.3,
                max_retries=2,
                response_format={"type": "json_object"},
                timeout=_BRAIN_TIMEOUT,
            )
            raw = response.content
            logger.debug("Brain raw response: %s", raw[:500])
            return _parse_json_thought(raw)
        except TimeoutError as e:
            logger.warning(
                "Brain timeout after %ds: %s — deterministic path continues",
                _BRAIN_TIMEOUT,
                e,
            )
            return None
        except Exception as e:
            logger.warning(
                "Brain invoke failed (%s): %s — deterministic path continues",
                type(e).__name__,
                e,
            )
            return None


# ── JSON Parsing (module-level, testable) ─────────────────────────────


def _parse_json_thought(raw: str) -> Thought | None:
    """Parse JSON structured output into Thought.

    Key normalization: model says "understanding" → we map to "comprehension".
    Intent normalization: model says "question" → we map to BrainIntent.INQUIRY.
    Returns None on parse failure (logged, never silent).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Brain JSON decode failed: %s (raw: %s)", e, raw[:200])
        return None

    # Normalize aliased keys
    normalized = _normalize_keys(data)

    try:
        # Extract with defaults
        comprehension = str(normalized.get("comprehension", ""))[:300]
        raw_intent = str(normalized.get("intent", "observe"))
        intent = _normalize_intent(raw_intent)
        domain_relevance = str(normalized.get("domain_relevance", ""))[:200]

        raw_concepts = normalized.get("key_concepts", [])
        if isinstance(raw_concepts, list):
            key_concepts = tuple(str(c) for c in raw_concepts[:5])
        else:
            key_concepts = ()

        raw_confidence = normalized.get("confidence", 0.5)
        confidence = min(1.0, max(0.0, float(raw_confidence)))

        return Thought(
            comprehension=comprehension,
            intent=intent,
            domain_relevance=domain_relevance,
            key_concepts=key_concepts,
            confidence=confidence,
        )
    except (TypeError, ValueError) as e:
        logger.warning("Brain thought construction failed: %s", e)
        return None
