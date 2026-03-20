"""
AGENT RUNTIME — The 6-Step Cognitive Loop.

The cartridge defines WHAT the agent knows (domain, capabilities, guardian).
The runtime defines HOW the agent behaves (perceive → decide → act → verify → learn).

The runtime wraps existing pieces into a closed loop:
- CityLearning (Hebbian weights) → decision gate
- CartridgeFactory (agent spec) → deterministic handler
- MicroBrain (cheap LLM) → novel situation handler
- Outcome recording → weight adjustment → adaptation

Without the runtime, agents are static function calls.
With the runtime, agents LEARN from their actions.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.AGENT_RUNTIME")

# Default confidence thresholds
_DEFAULT_HIGH = 0.7
_DEFAULT_LOW = 0.3

# Guardian capability_protocol → confidence bias
# enforce-agents ACT faster (lower threshold to go deterministic)
# parse-agents OBSERVE longer (higher threshold, more MicroBrain thinking)
# infer-agents ANALYZE (balanced)
# route-agents DELEGATE (moderate, lean toward action)
# validate-agents CHECK (balanced)
_PROTOCOL_CONFIDENCE_BIAS: dict[str, tuple[float, float]] = {
    "enforce": (0.55, 0.2),   # Act fast. Low bar for deterministic. Warriors.
    "route": (0.6, 0.25),     # Lean toward action. Connectors.
    "infer": (0.7, 0.3),      # Balanced. Default thinkers.
    "validate": (0.7, 0.35),  # Careful. Need more evidence before acting.
    "parse": (0.8, 0.4),      # Observe longest. Highest bar for deterministic.
}


@dataclass
class AgentRuntime:
    """Cognitive loop for a city agent.

    The bridge between cartridge (identity) and action (behavior).
    Each agent gets a runtime instance during KARMA phase.

    Usage:
        runtime = AgentRuntime(name="sys_analyst", cartridge=cartridge,
                               learning=city_learning)
        result = runtime.process("How does immigration work?", ctx)
    """

    name: str
    cartridge: object  # from CartridgeFactory — has .process(), .domain, .capabilities
    learning: object  # CityLearning — Hebbian weights
    micro_brain: object | None = None  # MicroBrain — cheap LLM for novel tasks
    _call_count: int = field(default=0, init=False)

    def process(self, task_text: str, intent: str = "response") -> dict:
        """The 6-step cognitive loop.

        1. PERCEIVE — extract context from task
        2. DECIDE — confidence gate (deterministic vs MicroBrain)
        3. ACT — generate response via chosen path
        4. Return result (verification + learning happen in caller)

        Returns dict with: response_text, decision_mode, confidence, agent_name
        """
        self._call_count += 1

        # 1. PERCEIVE — extract context + browse URLs if present
        domain = getattr(self.cartridge, "domain", "general")
        capabilities = getattr(self.cartridge, "capabilities", [])
        protocol = getattr(self.cartridge, "capability_protocol", "infer")

        # Browser as 6th sense: if task contains URLs, READ them
        # Filter: never browse our own repo URLs (templates contain these)
        browser_context = ""
        try:
            from city.browser_factory import extract_urls, browse_url

            _OWN_URLS = ("kimeisele/agent-city/issues", "kimeisele/agent-city/discussions")
            urls = [u for u in extract_urls(task_text)
                    if not any(own in u for own in _OWN_URLS)]
            if urls:
                page_data = browse_url(urls[0])
                if page_data:
                    browser_context = (
                        f"\n[Browsed {page_data['url']}]: "
                        f"{page_data['title']} — {page_data['content_text'][:300]}"
                    )
        except Exception:
            pass

        # Guardian-derived confidence thresholds
        # enforce-agents ACT fast (0.55). parse-agents OBSERVE long (0.8).
        # This is the 24 elements making the decision, not the LLM.
        high_threshold, low_threshold = _PROTOCOL_CONFIDENCE_BIAS.get(
            protocol, (_DEFAULT_HIGH, _DEFAULT_LOW)
        )

        # 2. DECIDE — confidence gate (guardian-biased)
        confidence_key = f"{self.name}:{intent}"
        confidence = 0.5
        if hasattr(self.learning, "get_confidence"):
            confidence = self.learning.get_confidence(confidence_key, "handle")

        # High confidence: deterministic handler (the 24 elements)
        if confidence >= high_threshold:
            return self._deterministic(task_text, intent, confidence)

        # Low confidence or novel: try MicroBrain (the 25th element)
        if self.micro_brain is not None and confidence < high_threshold:
            # Pass full spec so MicroBrain knows the guardian's teaching
            spec = {}
            if hasattr(self.cartridge, "__dict__"):
                spec = {k: getattr(self.cartridge, k, "") for k in
                        ("guardian", "role", "capability_protocol", "guardian_capabilities",
                         "element", "element_capabilities", "guna", "style", "chapter_significance")
                        if hasattr(self.cartridge, k)}
            thought = self.micro_brain.think(
                agent_name=self.name,
                agent_domain=domain,
                task_text=task_text,
                capabilities=capabilities,
                city_context=browser_context,
                spec=spec,
            )
            if thought.action != "skip" and thought.confidence > 0.3:
                result = {
                    "agent_name": self.name,
                    "response_text": thought.response_text,
                    "action": thought.action,
                    "reasoning": thought.reasoning,
                    "target": thought.target,
                    "detail": thought.detail,
                    "decision_mode": "micro_brain",
                    "confidence": thought.confidence,
                }
                # Non-respond actions → execute through BrainAction pipeline
                if thought.action != "respond":
                    result["brain_action"] = self._to_brain_action(thought)
                return result

        # Fallback: deterministic (always works, no LLM needed)
        return self._deterministic(task_text, intent, confidence)

    def _deterministic(self, task_text: str, intent: str, confidence: float) -> dict:
        """Deterministic path — cartridge.process() with agent identity."""
        result = {}
        if hasattr(self.cartridge, "process"):
            try:
                result = self.cartridge.process(task_text)
                if not isinstance(result, dict):
                    result = {"raw": str(result)}
            except Exception as e:
                logger.debug("Cartridge process failed for %s: %s", self.name, e)
                result = {}

        result["agent_name"] = self.name
        result["decision_mode"] = "deterministic"
        result["confidence"] = confidence
        return result

    @staticmethod
    def _to_brain_action(thought: object) -> object | None:
        """Convert MicroThought to BrainAction for IntentExecutor dispatch.

        Uses ActionVerb enum directly — no hardcoded map. If the action
        string IS a valid ActionVerb value, it becomes a BrainAction.
        """
        try:
            from city.brain_action import ActionVerb, BrainAction

            # ActionVerb values ARE the action strings (StrEnum)
            try:
                verb = ActionVerb(thought.action)
            except ValueError:
                return None  # Not a known verb (e.g. "respond", "skip")

            return BrainAction(
                verb=verb,
                target=thought.target,
                detail=thought.detail or thought.reasoning,
                source_confidence=thought.confidence,
            )
        except Exception:
            return None

    def record_outcome(self, intent: str, success: bool) -> float:
        """Step 5+6: Learn from action outcome.

        Call this AFTER the action has been taken and we know if it worked.
        Returns updated weight.
        """
        if not hasattr(self.learning, "record_outcome"):
            return 0.5
        key = f"{self.name}:{intent}"
        weight = self.learning.record_outcome(key, "handle", success)
        logger.info(
            "RUNTIME[%s]: outcome %s for %s → weight=%.2f",
            self.name, "success" if success else "failure", intent, weight,
        )
        return weight
