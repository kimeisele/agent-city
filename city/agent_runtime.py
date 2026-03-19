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

# Confidence thresholds for the decision gate
_HIGH_CONFIDENCE = 0.7   # Above: trust deterministic handler
_LOW_CONFIDENCE = 0.3    # Below: definitely use MicroBrain


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

        # 1. PERCEIVE
        domain = getattr(self.cartridge, "domain", "general")
        capabilities = getattr(self.cartridge, "capabilities", [])

        # 2. DECIDE — confidence gate
        confidence_key = f"{self.name}:{intent}"
        confidence = 0.5
        if hasattr(self.learning, "get_confidence"):
            confidence = self.learning.get_confidence(confidence_key, "handle")

        # High confidence: deterministic handler (the 24 elements)
        if confidence >= _HIGH_CONFIDENCE:
            return self._deterministic(task_text, intent, confidence)

        # Low confidence or novel: try MicroBrain (the 25th element)
        if self.micro_brain is not None and confidence < _HIGH_CONFIDENCE:
            thought = self.micro_brain.think(
                agent_name=self.name,
                agent_domain=domain,
                task_text=task_text,
                capabilities=capabilities,
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

        Maps MicroBrain action verbs to ActionVerb enum.
        Returns None if the action doesn't map to a known verb.
        """
        try:
            from city.brain_action import ActionVerb, BrainAction

            verb_map = {
                "create_mission": ActionVerb.CREATE_MISSION,
                "flag_bottleneck": ActionVerb.FLAG_BOTTLENECK,
                "investigate": ActionVerb.INVESTIGATE,
                "check_health": ActionVerb.CHECK_HEALTH,
                "escalate": ActionVerb.ESCALATE,
                "assign_agent": ActionVerb.ASSIGN_AGENT,
            }
            verb = verb_map.get(thought.action)
            if verb is None:
                return None
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
