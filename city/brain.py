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
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from city.brain_context import ContextSnapshot

logger = logging.getLogger("AGENT_CITY.BRAIN")

_BRAIN_TIMEOUT = 12  # seconds — OpenRouter aggregator needs headroom
_MAX_TOKENS = 512    # room for proper JSON with all fields


# ── Typed Intent ──────────────────────────────────────────────────────


class ThoughtKind(StrEnum):
    """Typed taxonomy for brain thoughts."""

    COMPREHENSION = "comprehension"  # Phase 3: understand one input
    HEALTH_CHECK = "health_check"    # System health evaluation
    REFLECTION = "reflection"        # End-of-cycle reflection
    INSIGHT = "insight"              # 8H: synthesized insight from missions


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
    # action_hint aliases ("action" already maps to intent — don't overwrite)
    "suggestion": "action_hint",
    "hint": "action_hint",
    # evidence aliases
    "reasoning": "evidence",
    "observations": "evidence",
}

_CANONICAL_KEYS = {
    "comprehension", "intent", "domain_relevance", "key_concepts",
    "confidence", "action_hint", "evidence",
}


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

    comprehension: str = ""                          # What the brain understood
    intent: BrainIntent = BrainIntent.OBSERVE        # Typed intent classification
    domain_relevance: str = ""                       # Which city domain this touches
    key_concepts: tuple[str, ...] = ()               # Extracted concepts (max 5)
    confidence: float = 0.5                          # 0.0-1.0
    kind: ThoughtKind = ThoughtKind.COMPREHENSION    # Thought taxonomy
    action_hint: str = ""                            # Structured hint (see vocab below)
    evidence: tuple[str, ...] = ()                   # Supporting data (max 3 refs)

    # action_hint vocabulary:
    #   "" — no action suggested
    #   "flag_bottleneck:<domain>" — something is stuck
    #   "investigate:<topic>" — needs deeper look
    #   "create_mission:<description>" — suggest new Sankalpa mission

    def to_dict(self) -> dict[str, object]:
        """Serialize thought for storage, logging, feedback loops."""
        d: dict[str, object] = {
            "comprehension": self.comprehension,
            "intent": self.intent.value,
            "domain_relevance": self.domain_relevance,
            "key_concepts": list(self.key_concepts),
            "confidence": self.confidence,
            "kind": self.kind.value,
        }
        if self.action_hint:
            d["action_hint"] = self.action_hint
        if self.evidence:
            d["evidence"] = list(self.evidence)
        return d

    def format_for_post(self) -> str:
        """Format thought as structured text for discussion posting.

        This is the feedback loop entry point: posted thoughts become
        discussion content that can be scanned → comprehended → reacted to.
        """
        lines: list[str] = []
        if self.kind != ThoughtKind.COMPREHENSION:
            lines.append(f"**Kind**: {self.kind.value}")
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
        if self.action_hint:
            lines.append(f"**Action**: {self.action_hint}")
        if self.evidence:
            lines.append(f"**Evidence**: {'; '.join(self.evidence)}")
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
        snapshot: ContextSnapshot | None = None,
    ) -> Thought | None: ...

    def comprehend_signal(
        self,
        decoded_signal: object,
        receiver_spec: dict,
    ) -> Thought | None: ...

    def evaluate_health(
        self,
        snapshot: ContextSnapshot,
        *,
        memory: object | None = None,
    ) -> Thought | None: ...

    def reflect_on_cycle(
        self,
        snapshot: ContextSnapshot,
        reflection: dict,
        *,
        memory: object | None = None,
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
        snapshot: ContextSnapshot | None = None,
    ) -> Thought | None:
        """Brain comprehends a discussion. Returns understanding, not content.

        Returns None if: LLM unavailable, timeout, or parse failure.
        Caller continues with deterministic path on None.
        """
        if not self._ensure_provider():
            return None

        from city.brain_prompt import (
            build_header,
            build_payload,
            build_schema,
            build_system_prompt,
        )

        header = build_header(
            0, model=self._model, murali_phase="KARMA", snapshot=snapshot,
        )
        payload = build_payload(
            "comprehension",
            snapshot=snapshot,
            agent_spec=agent_spec,
            gateway_result=gateway_result,
            kg_context=kg_context,
            signal_reading=signal_reading,
        )
        schema = build_schema("comprehension")
        system_msg = build_system_prompt(header, payload, schema)

        messages = [
            {"role": "system", "content": system_msg},
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

        from city.brain_prompt import (
            build_header,
            build_payload,
            build_schema,
            build_system_prompt,
        )

        header = build_header(0, model=self._model, murali_phase="KARMA")
        payload = build_payload(
            "signal",
            decoded_signal=decoded_signal,
            receiver_spec=receiver_spec,
        )
        schema = build_schema("signal")
        system_msg = build_system_prompt(header, payload, schema)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": "What does this signal mean for this agent?"},
        ]

        thought = self._invoke_and_parse(messages)
        if thought is not None:
            logger.info(
                "Brain comprehended signal: intent=%s confidence=%.2f",
                thought.intent.value,
                thought.confidence,
            )
        return thought

    def evaluate_health(
        self,
        snapshot: ContextSnapshot,
        *,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain evaluates system health. 1 call per KARMA, highest priority."""
        if not self._ensure_provider():
            return None

        from city.brain_prompt import (
            build_header,
            build_payload,
            build_schema,
            build_system_prompt,
        )

        # Collect past thoughts for echo chamber guard
        past_thoughts = None
        if memory is not None and hasattr(memory, "recent"):
            past_thoughts = memory.recent(3)

        header = build_header(
            getattr(snapshot, "venu_tick", 0),
            snapshot=snapshot,
            memory=memory,
            model=self._model,
            murali_phase="KARMA",
        )
        payload = build_payload(
            "health_check",
            snapshot=snapshot,
            past_thoughts=past_thoughts,
        )
        schema = build_schema("health_check")
        system_msg = build_system_prompt(header, payload, schema)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": "Evaluate the current system health."},
        ]

        thought = self._invoke_and_parse(
            messages, kind=ThoughtKind.HEALTH_CHECK,
        )
        if thought is not None:
            logger.info(
                "Brain health check: intent=%s confidence=%.2f hint=%s",
                thought.intent.value,
                thought.confidence,
                thought.action_hint or "none",
            )
        return thought

    def reflect_on_cycle(
        self,
        snapshot: ContextSnapshot,
        reflection: dict,
        *,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain reflects on what happened this rotation. 1 call per MOKSHA."""
        if not self._ensure_provider():
            return None

        from city.brain_prompt import (
            build_header,
            build_payload,
            build_schema,
            build_system_prompt,
        )

        # Collect past thoughts for echo chamber guard
        past_thoughts = None
        if memory is not None and hasattr(memory, "recent"):
            past_thoughts = memory.recent(3)

        header = build_header(
            getattr(snapshot, "venu_tick", 0),
            snapshot=snapshot,
            memory=memory,
            model=self._model,
            murali_phase="MOKSHA",
        )
        payload = build_payload(
            "reflection",
            snapshot=snapshot,
            reflection=reflection,
            outcome_diff=reflection.get("outcome_diff"),
            past_thoughts=past_thoughts,
        )
        schema = build_schema("reflection")
        system_msg = build_system_prompt(header, payload, schema)

        # Summarize reflection dict for user message
        user_parts: list[str] = ["Reflect on this MURALI rotation:"]
        if reflection.get("learning_stats"):
            ls = reflection["learning_stats"]
            user_parts.append(
                f"Learning: {ls.get('synapses', 0)} synapses, "
                f"decayed={ls.get('decayed', 0)}, trimmed={ls.get('trimmed', 0)}."
            )
        if reflection.get("immune_stats"):
            ims = reflection["immune_stats"]
            user_parts.append(
                f"Immune: {ims.get('heals_attempted', 0)} heals, "
                f"{ims.get('heals_succeeded', 0)} succeeded."
            )
        if reflection.get("mission_results_terminal"):
            user_parts.append(
                f"Missions completed: {len(reflection['mission_results_terminal'])}."
            )
        events = reflection.get("events_since_last", 0)
        if events:
            user_parts.append(f"Events this rotation: {events}.")

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": " ".join(user_parts)},
        ]

        thought = self._invoke_and_parse(
            messages, kind=ThoughtKind.REFLECTION,
        )
        if thought is not None:
            logger.info(
                "Brain reflection: intent=%s confidence=%.2f hint=%s",
                thought.intent.value,
                thought.confidence,
                thought.action_hint or "none",
            )
        return thought

    def generate_insight(
        self,
        reflection: dict,
        *,
        snapshot: ContextSnapshot | None = None,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain synthesizes batched terminal missions into a city-wide insight.

        Persona: city synthesizer (Mayor/System), not individual agent.
        Returns None if LLM unavailable or no missions to synthesize.
        Caller MUST gate on non-empty terminal missions before calling.
        """
        if not self._ensure_provider():
            return None

        from city.brain_prompt import (
            build_header,
            build_payload,
            build_schema,
            build_system_prompt,
        )

        past_thoughts = None
        if memory is not None and hasattr(memory, "recent"):
            past_thoughts = memory.recent(3)

        header = build_header(
            getattr(snapshot, "venu_tick", 0) if snapshot else 0,
            snapshot=snapshot,
            memory=memory,
            model=self._model,
            murali_phase="MOKSHA",
        )
        payload = build_payload(
            "insight",
            snapshot=snapshot,
            reflection=reflection,
            past_thoughts=past_thoughts,
        )
        schema = build_schema("insight")
        system_msg = build_system_prompt(header, payload, schema)

        missions = reflection.get("mission_results_terminal", [])
        user_msg = (
            f"Synthesize an insight from {len(missions)} completed missions "
            f"this cycle. What did the city learn?"
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        thought = self._invoke_and_parse(messages, kind=ThoughtKind.INSIGHT)
        if thought is not None:
            logger.info(
                "Brain insight: intent=%s confidence=%.2f concepts=%s",
                thought.intent.value,
                thought.confidence,
                list(thought.key_concepts),
            )
        return thought

    def _invoke_and_parse(
        self,
        messages: list[dict],
        *,
        kind: ThoughtKind = ThoughtKind.COMPREHENSION,
    ) -> Thought | None:
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
            thought = _parse_json_thought(raw, kind=kind)
            if thought is not None and kind in (
                ThoughtKind.HEALTH_CHECK,
                ThoughtKind.REFLECTION,
            ):
                thought = _buddhi_validate(thought)
            return thought
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


def _parse_json_thought(
    raw: str,
    *,
    kind: ThoughtKind = ThoughtKind.COMPREHENSION,
) -> Thought | None:
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

    # Also pass through canonical keys that _normalize_keys doesn't touch
    # (action_hint, evidence from the raw data if present)
    for key in ("action_hint", "evidence", "kind"):
        if key in data and key not in normalized:
            normalized[key] = data[key]

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

        # New fields (Phase 4)
        action_hint = str(normalized.get("action_hint", ""))[:200]
        raw_evidence = normalized.get("evidence", [])
        if isinstance(raw_evidence, list):
            evidence = tuple(str(e)[:100] for e in raw_evidence[:3])
        else:
            evidence = ()

        # Kind from JSON overrides caller default (for roundtrip fidelity)
        raw_kind = normalized.get("kind", kind.value if isinstance(kind, ThoughtKind) else kind)
        try:
            thought_kind = ThoughtKind(raw_kind)
        except (ValueError, KeyError):
            thought_kind = kind

        return Thought(
            comprehension=comprehension,
            intent=intent,
            domain_relevance=domain_relevance,
            key_concepts=key_concepts,
            confidence=confidence,
            kind=thought_kind,
            action_hint=action_hint,
            evidence=evidence,
        )
    except (TypeError, ValueError) as e:
        logger.warning("Brain thought construction failed: %s", e)
        return None


# ── Buddhi Validation Gate (Fix #4: Cognitive Dissonance) ─────────────

# Intent → expected buddhi function alignment
_INTENT_BUDDHI_MAP: dict[str, tuple[str, ...]] = {
    "propose": ("BRAHMA", "source"),
    "inquiry": ("VISHNU", "carrier"),
    "govern": ("SHIVA", "deliverer"),
    "observe": (),          # any function is fine
    "connect": ("VISHNU", "carrier"),
}

_BUDDHI_PENALTY = 0.7


def _buddhi_validate(thought: Thought) -> Thought:
    """Soft validation: adjust confidence based on buddhi alignment.

    If intent and buddhi function disagree, this is a Cognitive Dissonance
    anomaly. Instead of silently suppressing (Fix #4), we:
    1. Log the dissonance explicitly as an anomaly
    2. Apply a soft penalty (× 0.7) to confidence
    3. Add "cognitive_dissonance" to evidence so it flows into memory

    Returns original thought if buddhi unavailable or intent is OBSERVE.
    """
    # OBSERVE always passes — no expected alignment
    if thought.intent is BrainIntent.OBSERVE:
        return thought

    expected = _INTENT_BUDDHI_MAP.get(thought.intent.value, ())
    if not expected:
        return thought

    # Try to get buddhi reading from the thought's domain context
    try:
        from vibe_core.mahamantra.substrate.buddhi import get_buddhi

        buddhi = get_buddhi()
        cognition = buddhi.think(thought.comprehension)
        actual_function = getattr(cognition, "function", "")

        if actual_function not in expected:
            # Cognitive Dissonance detected — log as anomaly, don't suppress
            penalized_confidence = round(thought.confidence * _BUDDHI_PENALTY, 4)
            logger.warning(
                "Brain COGNITIVE DISSONANCE: intent=%s expects %s, "
                "buddhi says %s. Confidence %.2f → %.2f. "
                "Tracking as anomaly for future cycles.",
                thought.intent.value,
                expected,
                actual_function,
                thought.confidence,
                penalized_confidence,
            )
            # Build new evidence tuple with dissonance flag
            dissonance_note = (
                f"cognitive_dissonance:intent={thought.intent.value}"
                f":buddhi={actual_function}"
            )
            new_evidence = thought.evidence + (dissonance_note,)
            return Thought(
                comprehension=thought.comprehension,
                intent=thought.intent,
                domain_relevance=thought.domain_relevance,
                key_concepts=thought.key_concepts,
                confidence=penalized_confidence,
                kind=thought.kind,
                action_hint=thought.action_hint,
                evidence=new_evidence[:3],  # cap at 3
            )

        return thought
    except Exception:
        # Buddhi unavailable — pass through unchanged
        return thought
