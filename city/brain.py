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
    from city.prompt_registry import PromptContext

logger = logging.getLogger("AGENT_CITY.BRAIN")

_BRAIN_TIMEOUT = 12  # seconds — OpenRouter aggregator needs headroom
_MAX_TOKENS = 1024   # enough for structured JSON from small models


# ── Typed Intent ──────────────────────────────────────────────────────


class ThoughtKind(StrEnum):
    """Typed taxonomy for brain thoughts."""

    COMPREHENSION = "comprehension"  # Phase 3: understand one input
    HEALTH_CHECK = "health_check"    # System health evaluation
    REFLECTION = "reflection"        # End-of-cycle reflection
    INSIGHT = "insight"              # 8H: synthesized insight from missions
    CRITIQUE = "critique"            # 10B: critical evaluation of system output quality


# ── Model Metabolism (Yantra Multi-Model Routing) ────────────────────


class ModelTier(StrEnum):
    """Cost-aware model tiers for cognition routing.

    Standard = DeepSeek via OpenRouter (cheap, the workhorse).
    Flash/Pro = ADDITIONAL capacity via Google free tier (direct API).

    Until Google provider supports messages + JSON mode, all tiers
    use DeepSeek. The architecture is ready — flip the models when
    Google direct is wired.

    COST RULE: OpenRouter = DeepSeek ONLY. Never route expensive
    models through OpenRouter. Flash/Pro use Google free tier or
    fall back to DeepSeek. Real money is at stake.
    """

    FLASH = "flash"        # Additional: Google free tier (routine bulk)
    STANDARD = "standard"  # Default: DeepSeek v3.2 (cheap workhorse)
    PRO = "pro"            # Additional: Google free tier (critical decisions)


# ThoughtKind → default ModelTier
_KIND_TIER: dict[str, ModelTier] = {
    "health_check": ModelTier.FLASH,
    "signal": ModelTier.FLASH,
    "comprehension": ModelTier.STANDARD,
    "reflection": ModelTier.STANDARD,
    "insight": ModelTier.STANDARD,
    "critique": ModelTier.PRO,
}

# The ONE cheap model on OpenRouter. All tiers use this until Google direct is ready.
_OPENROUTER_MODEL = "deepseek/deepseek-v3.2"

# Future Google free tier models (NOT YET ACTIVE — Google provider needs messages + JSON mode)
_GOOGLE_FLASH_MODEL = "gemini-2.0-flash"
_GOOGLE_PRO_MODEL = "gemini-1.5-pro"

# ModelTier → model string
# Currently all DeepSeek (safe, cheap). When Google direct is ready,
# Flash/Pro switch to Google free tier with DeepSeek as fallback.
_DEFAULT_TIER_MODELS: dict[ModelTier, str] = {
    ModelTier.FLASH: _OPENROUTER_MODEL,    # future: _GOOGLE_FLASH_MODEL (free)
    ModelTier.STANDARD: _OPENROUTER_MODEL,  # always DeepSeek
    ModelTier.PRO: _OPENROUTER_MODEL,       # future: _GOOGLE_PRO_MODEL (free)
}


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

        Transparent: shows what the Brain actually produced. If this
        looks bad, the fix is in the Brain's internals, not in hiding fields.
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

    8I: Unified _think() path. Each public method builds a PromptContext
    and delegates to _think(kind, ctx). No more per-method boilerplate.
    """

    def __init__(self) -> None:
        self._provider: object | None = None
        self._chamber: object | None = None  # ProviderChamber (lazy init)
        self._available: bool | None = None  # None = not checked yet
        self._tier_models: dict[ModelTier, str] = dict(_DEFAULT_TIER_MODELS)
        self._model = _OPENROUTER_MODEL  # always DeepSeek — the cheap workhorse

    @property
    def is_available(self) -> bool:
        """Whether this Brain has a working LLM provider.

        Forces provider init on first call. External code MUST use this
        instead of checking `brain is None` — the Brain object always exists
        but may be brain-dead (NoOp provider).
        """
        return self._ensure_provider()

    def retry_provider(self) -> bool:
        """Reset cached availability and re-attempt provider initialization.

        Called by the heartbeat observer when the brain is offline to check
        whether API keys have become available since the last attempt
        (e.g. secret rotation, transient env issue resolved).

        Returns True if the brain is now available.
        """
        self._available = None
        self._provider = None
        self._chamber = None
        result = self._ensure_provider()
        if result:
            logger.info("Brain: provider recovered after retry")
        else:
            logger.info("Brain: retry_provider — still offline")
        return result

    def _ensure_provider(self) -> bool:
        """Lazy init. Tries ProviderChamber first, falls back to single provider.

        Priority:
        1. ProviderChamber (real MahaCellUnified substrate, multi-provider)
        2. Single provider via factory (backward compat)
        3. Offline (NoOp)
        """
        if self._available is not None:
            return self._available
        try:
            # Try ProviderChamber first (real substrate, multi-provider)
            try:
                from steward.provider import build_chamber

                chamber = build_chamber()
                if len(chamber) > 0:
                    self._chamber = chamber
                    self._available = True
                    logger.info("Brain: ProviderChamber active (%d cells)", len(chamber))
                    return True
            except Exception as e:
                logger.debug("Brain: ProviderChamber not available: %s", e)

            # Fallback to single provider
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

    # ── Unified Think Path (8I) ────────────────────────────────────────

    def _think(
        self,
        kind: str,
        ctx: PromptContext,
        *,
        murali_phase: str = "KARMA",
        memory: object | None = None,
        user_message_override: str = "",
    ) -> Thought | None:
        """Unified cognition path. All public methods delegate here.

        1. Ensure provider available
        2. Build header → payload → schema → system prompt (via PromptRegistry)
        3. Construct messages with builder's user_message (or override)
        4. Invoke LLM and parse response
        5. Validate (buddhi gate for health/reflection)

        Returns None on any failure — caller continues deterministic path.
        """
        if not self._ensure_provider():
            return None

        from city.brain_prompt import (
            build_header,
            build_payload,
            build_schema,
            build_system_prompt,
            get_prompt_registry,
        )

        # Collect past thoughts for echo chamber guard
        past_thoughts = None
        if memory is not None and hasattr(memory, "recent"):
            past_thoughts = memory.recent(3)

        snapshot = ctx.snapshot
        heartbeat = getattr(snapshot, "venu_tick", 0) if snapshot else 0

        header = build_header(
            heartbeat,
            snapshot=snapshot,
            memory=memory,
            model=self._model,
            murali_phase=murali_phase,
        )

        # Build payload via registry (delegates to the correct builder)
        payload = build_payload(
            kind,
            snapshot=snapshot,
            agent_spec=ctx.agent_spec,
            gateway_result=ctx.gateway_result,
            kg_context=ctx.kg_context,
            signal_reading=ctx.signal_reading,
            decoded_signal=ctx.decoded_signal,
            receiver_spec=ctx.receiver_spec,
            reflection=ctx.reflection,
            outcome_diff=ctx.outcome_diff,
            field_summary=ctx.field_summary,
            past_thoughts=past_thoughts,
        )
        schema = build_schema(kind)
        system_msg = build_system_prompt(header, payload, schema)

        # User message: override or from builder
        if user_message_override:
            user_msg = user_message_override
        else:
            registry = get_prompt_registry()
            user_msg = registry.build_user_message(kind, ctx)
            if not user_msg:
                user_msg = f"Process this {kind} request."

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        thought_kind = (
            ThoughtKind(kind)
            if kind in ThoughtKind.__members__.values()
            else ThoughtKind.COMPREHENSION
        )

        # Model metabolism: select tier model based on ThoughtKind
        tier = _KIND_TIER.get(kind, ModelTier.STANDARD)
        model = self._tier_models.get(tier, self._model)
        thought = self._invoke_and_parse(messages, kind=thought_kind, model=model)

        # Fallback: if tier model failed and it wasn't standard, retry with standard
        if thought is None and model != self._model:
            logger.info(
                "Brain: %s tier (%s) failed, falling back to standard (%s)",
                tier.value, model, self._model,
            )
            thought = self._invoke_and_parse(messages, kind=thought_kind, model=self._model)

        if thought is not None:
            self._log_thought(kind, thought)

        return thought

    @staticmethod
    def _log_thought(kind: str, thought: Thought) -> None:
        """Consolidated logging for brain thoughts."""
        logger.info(
            "Brain %s: intent=%s confidence=%.2f hint=%s concepts=%s",
            kind,
            thought.intent.value,
            thought.confidence,
            thought.action_hint or "none",
            list(thought.key_concepts),
        )

    # ── Public API (backward-compatible thin wrappers) ─────────────────

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
        from city.prompt_registry import PromptContext

        ctx = PromptContext(
            snapshot=snapshot,
            agent_spec=agent_spec,
            gateway_result=gateway_result,
            kg_context=kg_context,
            signal_reading=signal_reading,
        )
        return self._think(
            "comprehension",
            ctx,
            user_message_override=f"Comprehend this discussion:\n\n{discussion_text[:2000]}",
        )

    def comprehend_signal(
        self,
        decoded_signal: object,
        receiver_spec: dict,
    ) -> Thought | None:
        """Brain comprehends why a signal resonates with this receiver."""
        from city.prompt_registry import PromptContext

        ctx = PromptContext(
            decoded_signal=decoded_signal,
            receiver_spec=receiver_spec,
        )
        return self._think("signal", ctx)

    def evaluate_health(
        self,
        snapshot: ContextSnapshot,
        *,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain evaluates system health. 1 call per KARMA, highest priority."""
        from city.prompt_registry import PromptContext

        ctx = PromptContext(snapshot=snapshot)
        return self._think("health_check", ctx, memory=memory)

    def reflect_on_cycle(
        self,
        snapshot: ContextSnapshot,
        reflection: dict,
        *,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain reflects on what happened this rotation. 1 call per MOKSHA."""
        from city.prompt_registry import PromptContext

        ctx = PromptContext(
            snapshot=snapshot,
            reflection=reflection,
            outcome_diff=reflection.get("outcome_diff"),
        )
        return self._think("reflection", ctx, murali_phase="MOKSHA", memory=memory)

    def generate_insight(
        self,
        reflection: dict,
        *,
        snapshot: ContextSnapshot | None = None,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain synthesizes batched terminal missions into a city-wide insight."""
        from city.prompt_registry import PromptContext

        ctx = PromptContext(
            snapshot=snapshot,
            reflection=reflection,
        )
        return self._think("insight", ctx, murali_phase="MOKSHA", memory=memory)

    def critique_field(
        self,
        field_summary: str,
        *,
        snapshot: ContextSnapshot | None = None,
        memory: object | None = None,
    ) -> Thought | None:
        """Brain critically evaluates the Field (system output quality).

        10B: The Brain is the Kshetrajna (Knower of the Field).
        """
        from city.prompt_registry import PromptContext

        ctx = PromptContext(
            snapshot=snapshot,
            field_summary=field_summary,
        )
        return self._think("critique", ctx, memory=memory)

    def _invoke_and_parse(
        self,
        messages: list[dict],
        *,
        kind: ThoughtKind = ThoughtKind.COMPREHENSION,
        model: str | None = None,
    ) -> Thought | None:
        """Invoke LLM with JSON mode + timeout. Parse into Thought.

        Logs failures transparently — never silent.
        """
        model = model or self._model
        try:
            if self._chamber is not None:
                # ProviderChamber: real MahaCellUnified substrate.
                # Chamber picks provider by prana order, uses cell's own model.
                response = self._chamber.invoke(  # type: ignore[union-attr]
                    messages=messages,
                    max_tokens=_MAX_TOKENS,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    timeout=_BRAIN_TIMEOUT,
                )
                if response is None:
                    logger.warning("Brain: all provider cells exhausted")
                    return None
            else:
                response = self._provider.invoke(  # type: ignore[union-attr]
                    messages=messages,
                    model=model,
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
        # Strip markdown code fences (Google Gemini wraps JSON in ```json ... ```)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            # Remove closing fence
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].rstrip()
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        # Fallback: extract first JSON object from the text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
            except (json.JSONDecodeError, TypeError) as e2:
                logger.warning("Brain JSON decode failed: %s (raw: %s)", e2, raw[:200])
                return None
        else:
            logger.warning("Brain JSON: no JSON object found (raw: %s)", raw[:200])
            return None

    # DeepSeek sometimes returns a JSON array — unwrap first dict element
    if isinstance(data, list):
        dict_item = next((item for item in data if isinstance(item, dict)), None)
        if dict_item is not None:
            data = dict_item
        elif data and isinstance(data[0], (int, float)):
            # Bare number in array (e.g. [2025.04]) — wrap as confidence
            logger.debug("Brain returned bare number list %s — wrapping", data[:3])
            data = {"confidence": data[0], "intent": "observe", "reasoning": "numeric response"}
        else:
            logger.warning("Brain JSON returned non-dict list: %s", raw[:200])
            return None

    if not isinstance(data, dict):
        logger.warning("Brain JSON returned non-dict: %s", type(data).__name__)
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
        comprehension = str(normalized.get("comprehension", ""))[:800]
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
    except Exception as e:
        # Buddhi unavailable — pass through unchanged
        logger.debug("Buddhi validation skipped: %s", e)
        return thought
