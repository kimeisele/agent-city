"""
CITY DIAGNOSTICS — GAD-000 Introspection Service
==================================================

Pure prediction. Zero side effects. Calls the SAME functions the live
pipeline calls, but returns structured dicts instead of mutating state.

Discoverable: capabilities() lists all diagnostic operations
Observable:   stats() shows diagnostic usage counters
Parseable:    structured dict returns (no prose)
Composable:   callable from any phase, CLI, or test
Idempotent:   pure prediction, zero side effects

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from city.discussions_inbox import (
    DiscussionSignal,
    INTENT_REQUIREMENTS,
    _compose_response,
    classify_discussion_intent,
)

logger = logging.getLogger("AGENT_CITY.DIAGNOSTICS")


# ── Pure Scoring Functions ───────────────────────────────────────────


def score_agent_for_discussion(
    spec: dict,
    intent: str,
    discussion_text: str = "",
) -> float:
    """Score an agent for a discussion intent. Pure function.

    Shared by KARMA routing and diagnostics prediction.
    4 weighted dimensions (neuro-symbolic):
      0.3 — domain alignment
      0.3 — capability coverage (required_caps)
      0.2 — semantic affinity (WordNet graph distance to discussion text)
      0.2 — QoS bonus (lower latency = higher score)
    """
    reqs = INTENT_REQUIREMENTS.get(intent, INTENT_REQUIREMENTS["observe"])
    required_caps = set(reqs.get("required_caps", []))
    preferred_domain = reqs.get("preferred_domain", "")

    score = 0.0
    if preferred_domain and spec.get("domain") == preferred_domain:
        score += 0.3

    agent_caps = set(spec.get("capabilities", []))
    if required_caps:
        matched = sum(1 for c in required_caps if c in agent_caps)
        score += 0.3 * (matched / len(required_caps))

    # Semantic affinity: agent's pre-computed affinity vs discussion text
    if discussion_text:
        semantic = spec.get("semantic_affinity", {})
        if semantic:
            # Score how well this agent's semantic profile matches the text
            # by checking which domain keywords appear in the discussion
            text_lower = discussion_text.lower()
            max_affinity = 0.0
            for domain_key, affinity_score in semantic.items():
                # Check if any domain keyword tokens appear in discussion
                from city.guardian_spec import _DOMAIN_KEYWORDS

                keywords = _DOMAIN_KEYWORDS.get(domain_key, "").split()
                if any(kw in text_lower for kw in keywords):
                    max_affinity = max(max_affinity, affinity_score)
            score += 0.2 * max_affinity

    qos = spec.get("qos", {})
    latency = qos.get("latency_multiplier", 1.5)
    if latency > 0:
        score += 0.2 * (1.0 / latency)

    return round(score, 3)


def eligible_intents_for_agent(spec: dict) -> list[str]:
    """Which discussion intents can this agent handle?"""
    from city.mission_router import check_capability_gate

    eligible = []
    for intent, reqs in INTENT_REQUIREMENTS.items():
        gate_req = {
            "required": reqs.get("required_caps", []),
            "preferred": [],
            "min_tier": "contributor",
        }
        if check_capability_gate(spec, gate_req):
            eligible.append(intent)
    return eligible


# ── The Service ──────────────────────────────────────────────────────


@dataclass
class CityDiagnostics:
    """GAD-000: City introspection service.

    Discoverable: capabilities() lists all diagnostic operations
    Observable:   stats() shows diagnostic usage counters
    Parseable:    structured dict returns (no prose)
    Composable:   callable from any phase, CLI, or test
    Idempotent:   pure prediction, zero side effects
    """

    _gateway: object  # CityGateway
    _factory: object  # CartridgeFactory
    _pokedex: object  # Pokedex
    _ops: dict = field(default_factory=lambda: {"predicts": 0, "inspects": 0, "traces": 0})

    def predict_discussion(self, text: str, agent_name: str | None = None) -> dict:
        """Predict discussion response for an input text.

        Uses: gateway.process(), classify_discussion_intent(),
        _compose_response(), score_agent_for_discussion() logic.

        If agent_name given, composes for that agent only.
        If None, composes for ALL agents + shows routing scores.
        """
        gateway_result = self._gateway.process(text, "discussion")
        intent = classify_discussion_intent(gateway_result)
        signal = DiscussionSignal(0, "[predict]", text, "diagnostics", [])
        city_stats = self._pokedex.stats()

        agents = []
        for name in self._factory.list_generated():
            spec = self._factory.get_spec(name)
            if spec is None:
                continue
            body = _compose_response(spec, signal, city_stats, gateway_result)
            score = score_agent_for_discussion(spec, intent, text)
            agents.append({
                "name": name,
                "domain": spec.get("domain"),
                "guna": spec.get("guna"),
                "guardian": spec.get("guardian"),
                "tier": spec.get("capability_tier"),
                "score": score,
                "response": body,
            })

        agents.sort(key=lambda a: a["score"], reverse=True)

        if agent_name:
            agents = [a for a in agents if a["name"] == agent_name]

        self._ops["predicts"] += 1
        return {
            "input": text,
            "gateway": {
                "buddhi_function": gateway_result["buddhi_function"],
                "buddhi_chapter": gateway_result["buddhi_chapter"],
                "buddhi_mode": gateway_result["buddhi_mode"],
                "seed": gateway_result["seed"],
            },
            "intent": intent,
            "city_stats": city_stats,
            "agents": agents,
            "best_agent": agents[0]["name"] if agents else None,
        }

    def inspect_agent(self, name: str) -> dict:
        """Full agent introspection from Jiva -> Spec -> Capabilities."""
        spec = self._factory.get_spec(name)
        if spec is None:
            # Try generating
            self._factory.generate(name)
            spec = self._factory.get_spec(name)
        if spec is None:
            return {"error": f"agent {name} not found"}

        cell = self._pokedex.get_cell(name)

        self._ops["inspects"] += 1
        return {
            "name": name,
            "spec": dict(spec),
            "cell": {
                "prana": cell.prana if cell else 0,
                "is_alive": cell.is_alive if cell else False,
                "integrity": cell.integrity if cell else 0,
            } if cell else None,
            "routing": {
                "eligible_intents": eligible_intents_for_agent(spec),
                "tier": spec.get("capability_tier"),
                "caps": spec.get("capabilities"),
            },
        }

    def trace_input(self, text: str) -> dict:
        """Trace gateway processing for any input text."""
        gateway_result = self._gateway.process(text, "diagnostic")
        self._ops["traces"] += 1
        return dict(gateway_result)

    def inspect_all(self) -> dict:
        """All agents at a glance."""
        agents = []
        for name in self._factory.list_generated():
            spec = self._factory.get_spec(name)
            if spec is None:
                continue
            cell = self._pokedex.get_cell(name)
            agents.append({
                "name": name,
                "domain": spec.get("domain"),
                "guna": spec.get("guna"),
                "guardian": spec.get("guardian"),
                "element": spec.get("element"),
                "tier": spec.get("capability_tier"),
                "caps": spec.get("capabilities"),
                "alive": cell.is_alive if cell else False,
                "prana": cell.prana if cell else 0,
            })
        return {"agents": agents, "count": len(agents)}

    @staticmethod
    def capabilities() -> list[dict]:
        return [
            {"op": "predict_discussion", "phase": "any", "idempotent": True},
            {"op": "inspect_agent", "phase": "any", "idempotent": True},
            {"op": "trace_input", "phase": "any", "idempotent": True},
            {"op": "inspect_all", "phase": "any", "idempotent": True},
        ]

    def stats(self) -> dict:
        return dict(self._ops)
