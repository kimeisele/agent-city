"""
MICRO BRAIN — Per-Agent Cognition at $0.00001/call.

NOT the CityBrain. CityBrain is the shared city organ for critical
decisions (health, reflection, comprehension). Expensive. Full context.

MicroBrain is per-agent, per-task. Cheapest available model.
Short context. One decision per call. JSON structured output.

Uses the SAME provider infrastructure as CityBrain (OpenRouter via
ServiceRegistry) but with a cheaper model and tiny token budget.

Cost: ~$0.00001/call with Mistral Nemo. $0.01/day for 10 agents.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger("AGENT_CITY.MICRO_BRAIN")

# Cheapest usable models on OpenRouter (sorted by cost)
_CHEAP_MODELS = [
    "mistralai/mistral-nemo",       # $0.02/M prompt — good JSON output
    "meta-llama/llama-3.1-8b-instruct",  # $0.02/M — solid reasoning
    "deepseek/deepseek-chat",       # $0.14/M — fallback, best quality
]

_MAX_TOKENS = 256  # Tiny output — one decision, not an essay


@dataclass
class MicroThought:
    """Structured output from a micro-cognition call."""

    action: str  # what to do: "respond", "create_mission", "escalate", "skip", etc.
    reasoning: str  # why (1-2 sentences)
    response_text: str  # the actual response if action=respond
    confidence: float  # 0.0-1.0
    target: str = ""  # what/who this is about (for non-respond actions)
    detail: str = ""  # task description (for create_mission)
    agent_name: str = ""

    @classmethod
    def from_dict(cls, data: dict, agent_name: str = "") -> MicroThought:
        return cls(
            action=data.get("action", "skip"),
            reasoning=data.get("reasoning", ""),
            response_text=data.get("response_text", ""),
            confidence=float(data.get("confidence", 0.5)),
            target=data.get("target", ""),
            detail=data.get("detail", ""),
            agent_name=agent_name,
        )

    @classmethod
    def fallback(cls, agent_name: str = "") -> MicroThought:
        return cls(action="skip", reasoning="MicroBrain unavailable",
                   response_text="", confidence=0.0, agent_name=agent_name)


class MicroBrain:
    """Per-agent micro-cognition. One thought per task."""

    def __init__(self, model: str = "") -> None:
        self._model = model or _CHEAP_MODELS[0]
        self._provider: object | None = None
        self._available: bool | None = None

    def _ensure_provider(self) -> bool:
        if self._available is not None:
            return self._available
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
    ) -> MicroThought:
        """One thought. One decision. ~$0.00001.

        Returns MicroThought with action decision. Falls back to
        MicroThought.fallback() if LLM unavailable.
        """
        if not self._ensure_provider():
            return MicroThought.fallback(agent_name)

        system_prompt = (
            f"You are {agent_name}, a {agent_domain} agent in Agent City.\n"
            f"Capabilities: {', '.join(capabilities) if capabilities else 'general'}.\n"
            f"{city_context}\n\n"
            f"Given a task, decide what to do. You have these ACTIONS:\n"
            f"- respond: answer the question directly\n"
            f"- create_mission: create a task for someone to work on (include target and detail)\n"
            f"- flag_bottleneck: report a problem you noticed (include target)\n"
            f"- investigate: you need more information before acting\n"
            f"- check_health: evaluate system health\n"
            f"- escalate: this is beyond your capability, pass it up\n"
            f"- skip: nothing to do\n\n"
            f"Respond with JSON:\n"
            f'{{"action": "respond|create_mission|flag_bottleneck|investigate|check_health|escalate|skip", '
            f'"reasoning": "1-2 sentences why", '
            f'"response_text": "your response if action=respond", '
            f'"target": "what/who this is about if action!=respond", '
            f'"detail": "task description if action=create_mission", '
            f'"confidence": 0.0-1.0}}'
        )

        try:
            result = self._provider.invoke(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_text},
                ],
                max_tokens=_MAX_TOKENS,
                temperature=0.3,
                model=self._model,
            )

            # Parse LLMResponse
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
        """Extract JSON from LLM response. Handles markdown fences."""
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
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return None
