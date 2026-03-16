"""
CIVIC PROTOCOL — Declarative Governance Language for Agent City.

Replaces imperative if/else logic with rule-based governance.
Rules are evaluated deterministically, no hardcoded conditions.

Structure:
- CivicRule: WHEN condition THEN action WITH constraints
- CivicContext: System state snapshot for rule evaluation  
- CivicEngine: Rule registry + deterministic evaluation

This is the machine language for autonomous governance.
No LLM required for rule evaluation — pure deterministic logic.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("AGENT_CITY.CIVIC_PROTOCOL")

# ── Rule Structure ───────────────────────────────────────────────────────


class CivicCondition(str, Enum):
    """Deterministic condition types for governance rules."""

    # Economic conditions
    AVG_PRANA_BELOW = "avg_prana_below"
    TOTAL_PRANA_BELOW = "total_prana_below"
    DORMANT_ABOVE = "dormant_above"
    TREASURY_BELOW = "treasury_below"

    # System conditions
    BRAIN_OFFLINE = "brain_offline"
    AGENT_COUNT_BELOW = "agent_count_below"
    THREADS_UNANSWERED_ABOVE = "threads_unanswered_above"
    FEDERATION_DEGRADED = "federation_degraded"

    # Governance conditions
    PROPOSAL_PENDING_ABOVE = "proposal_pending_above"
    COUNCIL_SEATS_EMPTY = "council_seats_empty"
    ELECTION_DUE = "election_due"

    # Time-based conditions
    HEARTBEAT_MODULO = "heartbeat_modulo"
    TIME_SINCE_LAST_POST_HOURS = "time_since_last_post_hours"


class CivicAction(str, Enum):
    """Deterministic actions for governance rules."""

    # Posting actions
    POST_CITY_REPORT = "post_city_report"
    POST_HEALTH_DIAGNOSTIC = "post_health_diagnostic"
    POST_ELECTION_NOTICE = "post_election_notice"
    POST_REFERENDUM = "post_referendum"

    # Governance actions
    TRIGGER_ELECTION = "trigger_election"
    ESCALATE_TO_COUNCIL = "escalate_to_council"
    HOLD_REFERENDUM = "hold_referendum"

    # System actions
    ADJUST_PRANA_FLOW = "adjust_prana_flow"
    FREEZE_DORMANT_AGENTS = "freeze_dormant_agents"
    EMERGENCY_BRAIN_RESTART = "emergency_brain_restart"


@dataclass(frozen=True)
class CivicConstraint:
    """Constraints on rule execution."""
    
    max_frequency: int = 1  # max executions per N heartbeats
    cooldown_heartbeats: int = 10
    require_quorum: bool = False
    min_prana_threshold: int = 0


@dataclass(frozen=True)
class CivicRule:
    """Declarative governance rule: WHEN condition THEN action WITH constraints."""
    
    name: str
    condition: CivicCondition
    condition_params: dict[str, Any] = field(default_factory=dict)
    action: CivicAction = CivicAction.POST_CITY_REPORT
    action_params: dict[str, Any] = field(default_factory=dict)
    constraints: CivicConstraint = field(default_factory=CivicConstraint)
    enabled: bool = True
    priority: int = 50  # higher = evaluated first

    def should_trigger(self, context: CivicContext) -> bool:
        """Deterministic condition evaluation."""
        if not self.enabled:
            return False

        # Check cooldown
        cooldown = self.constraints.cooldown_heartbeats
        last_exec = context.last_execution.get(self.name, -999)
        if context.heartbeat_count - last_exec < cooldown:
            return False

        # Check quorum if required
        if self.constraints.require_quorum and not context.has_quorum:
            return False

        # Check prana threshold
        min_prana = self.constraints.min_prana_threshold
        if min_prana > 0 and context.total_prana < min_prana:
            return False

        # Evaluate condition
        return self._evaluate_condition(context)

    def _evaluate_condition(self, context: CivicContext) -> bool:
        """Pure deterministic condition logic."""
        match self.condition:
            case CivicCondition.AVG_PRANA_BELOW:
                threshold = self.condition_params.get("threshold", 1000)
                return context.avg_prana < threshold

            case CivicCondition.TOTAL_PRANA_BELOW:
                threshold = self.condition_params.get("threshold", 10000)
                return context.total_prana < threshold

            case CivicCondition.DORMANT_ABOVE:
                threshold = self.condition_params.get("threshold", 5)
                return context.dormant_count > threshold

            case CivicCondition.BRAIN_OFFLINE:
                return not context.brain_online

            case CivicCondition.AGENT_COUNT_BELOW:
                threshold = self.condition_params.get("threshold", 10)
                return context.alive_agents < threshold

            case CivicCondition.THREADS_UNANSWERED_ABOVE:
                threshold = self.condition_params.get("threshold", 5)
                return context.unanswered_threads > threshold

            case CivicCondition.HEARTBEAT_MODULO:
                modulo = self.condition_params.get("modulo", 40)
                return context.heartbeat_count % modulo == 0

            case CivicCondition.TIME_SINCE_LAST_POST_HOURS:
                hours = self.condition_params.get("hours", 24)
                return context.hours_since_last_post > hours

            case CivicCondition.FEDERATION_DEGRADED:
                return _is_federation_degraded(context.federation_health)

            case _:
                logger.warning("Unknown civic condition: %s", self.condition)
                return False


@dataclass(frozen=True)
class CivicContext:
    """System state snapshot for rule evaluation."""

    heartbeat_count: int
    avg_prana: float
    total_prana: int
    dormant_count: int
    alive_agents: int
    brain_online: bool
    unanswered_threads: int
    hours_since_last_post: float
    has_quorum: bool
    last_execution: dict[str, int] = field(default_factory=dict)
    federation_health: dict = field(default_factory=dict)


# ── Civic Engine ───────────────────────────────────────────────────────


class CivicEngine:
    """Deterministic rule evaluation engine for governance."""
    
    def __init__(self) -> None:
        self._rules: dict[str, CivicRule] = {}
        self._execution_history: dict[str, list[int]] = {}

    def register_rule(self, rule: CivicRule) -> None:
        """Register a governance rule."""
        self._rules[rule.name] = rule
        logger.debug("CivicEngine: registered rule %s", rule.name)

    def evaluate(self, context: CivicContext) -> list[CivicRule]:
        """Evaluate all rules against context, return triggered rules."""
        triggered = []
        
        # Sort by priority (highest first)
        sorted_rules = sorted(self._rules.values(), key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if rule.should_trigger(context):
                triggered.append(rule)
                # Record execution for cooldown tracking
                self._execution_history.setdefault(rule.name, []).append(context.heartbeat_count)
                logger.info(
                    "CivicEngine: rule %s triggered (heartbeat #%d)",
                    rule.name, context.heartbeat_count,
                )
        
        return triggered

    def get_rule(self, name: str) -> CivicRule | None:
        """Get a rule by name."""
        return self._rules.get(name)

    def list_rules(self) -> list[CivicRule]:
        """List all registered rules."""
        return list(self._rules.values())

    def last_execution_map(self) -> dict[str, int]:
        """Return the most recent heartbeat at which each rule executed."""
        return {
            name: history[-1]
            for name, history in self._execution_history.items()
            if history
        }

    def enable_rule(self, name: str, enabled: bool = True) -> bool:
        """Enable or disable a rule."""
        rule = self._rules.get(name)
        if rule:
            # Create new rule with updated enabled flag
            updated = CivicRule(
                name=rule.name,
                condition=rule.condition,
                condition_params=rule.condition_params,
                action=rule.action,
                action_params=rule.action_params,
                constraints=rule.constraints,
                enabled=enabled,
                priority=rule.priority,
            )
            self._rules[name] = updated
            logger.info("CivicEngine: rule %s %s", name, "enabled" if enabled else "disabled")
            return True
        return False


# ── Federation Health Helper ─────────────────────────────────────────────


def _is_federation_degraded(health: dict) -> bool:
    """True when steward health data is absent or stale (>1h)."""
    if not health:
        return True
    import time

    ts = health.get("timestamp", 0)
    if ts and (time.time() - ts) > 3600:
        return True
    return False


# ── Default Rule Set ─────────────────────────────────────────────────────


def create_default_rules() -> list[CivicRule]:
    """Create the default governance rule set for Agent City."""
    return [
        # Economic crisis rules
        CivicRule(
            name="economy_critical_alert",
            condition=CivicCondition.AVG_PRANA_BELOW,
            condition_params={"threshold": 500},
            action=CivicAction.POST_HEALTH_DIAGNOSTIC,
            constraints=CivicConstraint(cooldown_heartbeats=20, require_quorum=False),
            priority=90,
        ),

        CivicRule(
            name="economy_warning",
            condition=CivicCondition.AVG_PRANA_BELOW,
            condition_params={"threshold": 2000},
            action=CivicAction.POST_CITY_REPORT,
            constraints=CivicConstraint(cooldown_heartbeats=40),
            priority=80,
        ),

        # System health rules
        CivicRule(
            name="brain_offline_alert",
            condition=CivicCondition.BRAIN_OFFLINE,
            action=CivicAction.POST_HEALTH_DIAGNOSTIC,
            constraints=CivicConstraint(cooldown_heartbeats=5),
            priority=95,
        ),

        CivicRule(
            name="dormant_spike_alert",
            condition=CivicCondition.DORMANT_ABOVE,
            condition_params={"threshold": 5},
            action=CivicAction.POST_HEALTH_DIAGNOSTIC,
            constraints=CivicConstraint(cooldown_heartbeats=30),
            priority=85,
        ),

        # Federation health
        CivicRule(
            name="federation_degraded_alert",
            condition=CivicCondition.FEDERATION_DEGRADED,
            action=CivicAction.POST_HEALTH_DIAGNOSTIC,
            constraints=CivicConstraint(cooldown_heartbeats=40),
            priority=75,
        ),

        # Regular reporting
        CivicRule(
            name="regular_city_report",
            condition=CivicCondition.HEARTBEAT_MODULO,
            condition_params={"modulo": 40},  # Every 10 MURALI cycles
            action=CivicAction.POST_CITY_REPORT,
            constraints=CivicConstraint(cooldown_heartbeats=35),
            priority=30,
        ),

        # Moltbook content cadence (controls MoltbookAssistant posting)
        CivicRule(
            name="regular_moltbook_content",
            condition=CivicCondition.HEARTBEAT_MODULO,
            condition_params={"modulo": 8},  # Every 2 MURALI cycles (~2 hours)
            action=CivicAction.POST_CITY_REPORT,  # Reused as "should_post" signal
            constraints=CivicConstraint(cooldown_heartbeats=6),
            priority=25,
        ),

        # Silence too long — post regardless of other conditions
        CivicRule(
            name="silence_breaker",
            condition=CivicCondition.TIME_SINCE_LAST_POST_HOURS,
            condition_params={"hours": 6},
            action=CivicAction.POST_CITY_REPORT,
            constraints=CivicConstraint(cooldown_heartbeats=20),
            priority=65,
        ),

        # Governance rules
        CivicRule(
            name="trigger_election",
            condition=CivicCondition.HEARTBEAT_MODULO,
            condition_params={"modulo": 108},  # MALA heartbeats
            action=CivicAction.TRIGGER_ELECTION,
            constraints=CivicConstraint(cooldown_heartbeats=100, require_quorum=True),
            priority=70,
        ),

        CivicRule(
            name="unanswered_threads_alert",
            condition=CivicCondition.THREADS_UNANSWERED_ABOVE,
            condition_params={"threshold": 5},
            action=CivicAction.POST_CITY_REPORT,
            constraints=CivicConstraint(cooldown_heartbeats=25),
            priority=60,
        ),
    ]


def create_civic_engine() -> CivicEngine:
    """Create and initialize CivicEngine with default rules."""
    engine = CivicEngine()
    for rule in create_default_rules():
        engine.register_rule(rule)
    logger.info("CivicEngine: initialized with %d default rules", len(engine.list_rules()))
    return engine
