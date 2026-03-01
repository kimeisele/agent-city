"""
MISSION ROUTER — Capability-based Mission Routing + Hard Enforcement
=====================================================================

Pure function module. Scores agents against missions using their full
AgentSpec (guardian, domain, capabilities, tier, QoS) and enforces
hard capability gates. No state, no side effects.

The capability gate is UNIVERSAL — every mission type must pass it.
No bypass for dedicated processors (issue_, exec_, heal_, audit_).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger("AGENT_CITY.MISSION_ROUTER")


# ── TypedDicts ────────────────────────────────────────────────────────


class MissionRequirement(TypedDict):
    """What a mission type demands from an agent."""

    required: list[str]  # ALL must be in agent's capabilities
    preferred: list[str]  # nice-to-have (higher score)
    min_tier: str  # minimum capability_tier


class RoutingResult(TypedDict):
    """Result of routing a mission to an agent."""

    agent_name: str | None  # None = no agent qualifies
    score: float  # 0.0–1.0
    blocked: bool  # True = all agents blocked by gate
    blocked_count: int  # how many agents failed the gate
    candidates_count: int  # how many passed the gate


# ── Constants ─────────────────────────────────────────────────────────

# Mission ID prefix → required capabilities + minimum tier
MISSION_REQUIREMENTS: dict[str, MissionRequirement] = {
    "heal_": {
        "required": ["validate"],
        "preferred": ["transform", "test"],
        "min_tier": "contributor",
    },
    "audit_": {
        "required": ["audit"],
        "preferred": ["observe", "judge"],
        "min_tier": "contributor",
    },
    "improve_": {
        "required": ["propose"],
        "preferred": ["review", "modify"],
        "min_tier": "contributor",
    },
    "issue_": {
        "required": ["execute"],
        "preferred": ["dispatch", "build"],
        "min_tier": "verified",
    },
    "exec_": {
        "required": ["execute"],
        "preferred": ["dispatch", "enforce"],
        "min_tier": "verified",
    },
    "signal_": {
        "required": ["observe"],
        "preferred": ["relay", "communicate"],
        "min_tier": "observer",
    },
    "fed_": {
        "required": ["relay"],
        "preferred": ["communicate", "connect"],
        "min_tier": "contributor",
    },
}

DEFAULT_REQUIREMENT: MissionRequirement = {
    "required": ["propose"],
    "preferred": [],
    "min_tier": "observer",
}

# Tier → numeric rank for comparison
TIER_RANK: dict[str, int] = {
    "observer": 0,
    "contributor": 1,
    "verified": 2,
    "sovereign": 3,
}

# Mission prefix → preferred domain (for scoring)
_PREFIX_DOMAIN: dict[str, str] = {
    "heal_": "GOVERNANCE",
    "audit_": "GOVERNANCE",
    "improve_": "ENGINEERING",
    "issue_": "ENGINEERING",
    "exec_": "ENGINEERING",
    "signal_": "DISCOVERY",
    "fed_": "DISCOVERY",
}

# Mission prefix → preferred capability protocol (for scoring)
_PREFIX_PROTOCOL: dict[str, str] = {
    "heal_": "validate",
    "audit_": "enforce",
    "improve_": "infer",
    "issue_": "infer",
    "exec_": "infer",
    "signal_": "parse",
    "fed_": "route",
}


# ── Hard Gate ─────────────────────────────────────────────────────────


def check_capability_gate(spec: dict, requirement: MissionRequirement) -> bool:
    """Hard gate. Returns False = agent CANNOT handle this mission.

    Two checks, both must pass:
    1. Agent's capability_tier rank >= mission's min_tier rank
    2. ALL required capabilities present in agent's merged capabilities
    """
    agent_tier = spec.get("capability_tier", "observer")
    if TIER_RANK.get(agent_tier, 0) < TIER_RANK.get(requirement["min_tier"], 0):
        return False

    agent_caps = set(spec.get("capabilities", []))
    for cap in requirement["required"]:
        if cap not in agent_caps:
            return False

    return True


# ── Scoring ───────────────────────────────────────────────────────────


def score_agent_for_mission(
    spec: dict,
    mission_id: str,
    requirement: MissionRequirement,
) -> float:
    """Score 0.0–1.0. Higher = better fit.

    Called ONLY after check_capability_gate passes.
    4 weighted dimensions:
      0.3 — domain alignment
      0.4 — capability coverage (preferred caps)
      0.2 — protocol match
      0.1 — QoS bonus (SATTVA fastest)
    """
    score = 0.0
    prefix = _get_prefix(mission_id)

    # Domain alignment (0.3)
    preferred_domain = _PREFIX_DOMAIN.get(prefix, "")
    if preferred_domain and spec.get("domain") == preferred_domain:
        score += 0.3

    # Capability coverage (0.4)
    preferred = requirement["preferred"]
    if preferred:
        agent_caps = set(spec.get("capabilities", []))
        matched = sum(1 for cap in preferred if cap in agent_caps)
        score += 0.4 * (matched / len(preferred))

    # Protocol match (0.2)
    preferred_protocol = _PREFIX_PROTOCOL.get(prefix, "")
    if preferred_protocol and spec.get("capability_protocol") == preferred_protocol:
        score += 0.2

    # QoS bonus (0.1)
    qos = spec.get("qos", {})
    latency = qos.get("latency_multiplier", 1.5)
    if latency > 0:
        score += 0.1 * (1.0 / latency)

    return score


# ── Router ────────────────────────────────────────────────────────────


def route_mission(
    mission: object,
    specs: dict[str, dict],
    active_agents: set[str],
) -> RoutingResult:
    """Route one mission to the best-fit agent.

    Args:
        mission: SankalpaMission (needs .id attribute).
        specs: All agent specs {name: AgentSpec dict}.
        active_agents: Set of currently active agent names.

    Returns:
        RoutingResult with best agent, score, or blocked=True.
    """
    mission_id = getattr(mission, "id", str(mission))
    requirement = get_requirement(mission_id)

    candidates: list[tuple[str, float]] = []
    blocked_count = 0

    for name, spec in specs.items():
        if name not in active_agents:
            continue

        if not check_capability_gate(spec, requirement):
            blocked_count += 1
            continue

        score = score_agent_for_mission(spec, mission_id, requirement)
        candidates.append((name, score))

    if not candidates:
        return RoutingResult(
            agent_name=None,
            score=0.0,
            blocked=True,
            blocked_count=blocked_count,
            candidates_count=0,
        )

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_name, best_score = candidates[0]

    return RoutingResult(
        agent_name=best_name,
        score=best_score,
        blocked=False,
        blocked_count=blocked_count,
        candidates_count=len(candidates),
    )


def authorize_mission(
    mission_id: str,
    specs: dict[str, dict],
    active_agents: set[str],
) -> bool:
    """Universal authorization gate for dedicated processors.

    Returns True if AT LEAST ONE active agent passes the capability
    gate for this mission type. Used by _process_issue_missions()
    and heal loop to enforce capability requirements before system
    services execute.

    The city won't attempt operations unless citizens have the
    required capabilities.
    """
    requirement = get_requirement(mission_id)

    for name, spec in specs.items():
        if name not in active_agents:
            continue
        if check_capability_gate(spec, requirement):
            return True

    return False


# ── Helpers ───────────────────────────────────────────────────────────


def get_requirement(mission_id: str) -> MissionRequirement:
    """Get the MissionRequirement for a mission ID (prefix lookup)."""
    for prefix, req in MISSION_REQUIREMENTS.items():
        if mission_id.startswith(prefix):
            return req
    return DEFAULT_REQUIREMENT


def _get_prefix(mission_id: str) -> str:
    """Extract the prefix (e.g. 'exec_') from a mission ID."""
    for prefix in MISSION_REQUIREMENTS:
        if mission_id.startswith(prefix):
            return prefix
    return ""
