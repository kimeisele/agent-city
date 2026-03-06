"""
GOVERNANCE LAYER — Unified Civic Protocol Integration.

Replaces scattered if/else governance logic with structured
CivicProtocol + DeliberationEngine + ReferendumSystem.

This is the single source of truth for all governance decisions:
- When to post city reports
- When to trigger elections  
- When to hold referendums
- When to escalate to council
- When to post health diagnostics

No more hardcoded conditions in outbound hooks.
All governance flows through this deterministic layer.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from city.civic_protocol import CivicContext, create_civic_engine
from city.deliberation_engine import create_deliberation_engine, submit_council_proposal
from city.referendum_system import create_referendum_engine, trigger_council_referral

logger = logging.getLogger("AGENT_CITY.GOVERNANCE_LAYER")


class GovernanceLayer:
    """Unified governance layer replacing scattered if/else logic."""
    
    def __init__(self) -> None:
        self._civic_engine = create_civic_engine()
        self._deliberation_engine = create_deliberation_engine()
        self._referendum_engine = create_referendum_engine()
        self._last_heartbeat = 0

    def evaluate_governance_actions(self, ctx) -> GovernanceActions:
        """Evaluate all governance rules and return actions to execute."""
        heartbeat = getattr(ctx, "heartbeat_count", 0)
        
        # Build civic context from system state
        civic_context = self._build_civic_context(ctx)
        
        # Evaluate civic rules
        triggered_rules = self._civic_engine.evaluate(civic_context)
        
        # Analyze pending proposals
        deliberation_results = self._deliberation_engine.analyze_pending_proposals(ctx)
        
        # Finalize expired referendums
        finalized_referendums = self._referendum_engine.finalize_expired_referendums()
        
        # Build action plan
        actions = GovernanceActions(
            heartbeat=heartbeat,
            triggered_rules=triggered_rules,
            deliberation_results=deliberation_results,
            finalized_referendums=finalized_referendums,
            should_post_city_report=self._should_post_city_report(triggered_rules),
            should_post_health_diagnostic=self._should_post_health_diagnostic(triggered_rules),
            should_trigger_election=self._should_trigger_election(triggered_rules),
            should_hold_referendum=self._should_hold_referendum(triggered_rules),
        )
        
        self._last_heartbeat = heartbeat
        logger.info(
            "GovernanceLayer: evaluated %d rules, %d deliberations, %d referendums",
            len(triggered_rules), len(deliberation_results), len(finalized_referendums)
        )
        
        return actions

    def _build_civic_context(self, ctx) -> CivicContext:
        """Build CivicContext from PhaseContext."""
        heartbeat = getattr(ctx, "heartbeat_count", 0)
        
        # Get economic stats
        avg_prana = 0.0
        total_prana = 0
        dormant_count = 0
        alive_agents = 0
        
        if hasattr(ctx, "pokedex") and ctx.pokedex:
            stats = ctx.pokedex.stats()
            total_prana = stats.get("total_prana", 0)
            alive_agents = stats.get("active", 0) + stats.get("citizen", 0)
            dormant_count = stats.get("dormant", 0)
            
            # Calculate average prana
            if alive_agents > 0:
                avg_prana = total_prana / alive_agents
        
        # Get brain status
        brain_online = hasattr(ctx, "brain") and ctx.brain is not None
        
        # Get thread stats
        unanswered_threads = 0
        if hasattr(ctx, "thread_state") and ctx.thread_state:
            try:
                ts_stats = ctx.thread_state.stats()
                unanswered_threads = ts_stats.get("unanswered", 0)
            except Exception:
                pass
        
        # Get last execution times from the actual civic engine.
        last_execution = self._civic_engine.last_execution_map()
        
        # Check quorum (simplified)
        has_quorum = alive_agents >= 5  # Basic quorum check
        
        # Calculate hours since last Discussions post from bridge telemetry.
        hours_since_last_post = self._hours_since_last_post(ctx)
        
        return CivicContext(
            heartbeat_count=heartbeat,
            avg_prana=avg_prana,
            total_prana=total_prana,
            dormant_count=dormant_count,
            alive_agents=alive_agents,
            brain_online=brain_online,
            unanswered_threads=unanswered_threads,
            hours_since_last_post=hours_since_last_post,
            has_quorum=has_quorum,
            last_execution=last_execution,
        )

    @staticmethod
    def _hours_since_last_post(ctx) -> float:
        """Resolve Discussions posting age in hours from observable bridge stats."""
        discussions = getattr(ctx, "discussions", None)
        if discussions is None or not hasattr(discussions, "stats"):
            return 0.0

        try:
            stats = discussions.stats()
        except Exception:
            return 0.0

        age_s = stats.get("last_post_age_s")
        if age_s is None:
            return 0.0

        try:
            return max(float(age_s), 0.0) / 3600.0
        except (TypeError, ValueError):
            return 0.0

    def _should_post_city_report(self, triggered_rules) -> bool:
        """Check if any triggered rules require city report posting."""
        return any(
            rule.action.value == "post_city_report"
            for rule in triggered_rules
        )

    def _should_post_health_diagnostic(self, triggered_rules) -> bool:
        """Check if any triggered rules require health diagnostic posting."""
        return any(
            rule.action.value == "post_health_diagnostic"
            for rule in triggered_rules
        )

    def _should_trigger_election(self, triggered_rules) -> bool:
        """Check if any triggered rules require election triggering."""
        return any(
            rule.action.value == "trigger_election"
            for rule in triggered_rules
        )

    def _should_hold_referendum(self, triggered_rules) -> bool:
        """Check if any triggered rules require referendum holding."""
        return any(
            rule.action.value == "hold_referendum"
            for rule in triggered_rules
        )

    def submit_council_proposal_for_deliberation(
        self,
        proposal_id: str,
        title: str,
        description: str,
        proposal_type: str,
        proposer: str,
        ctx,
    ) -> None:
        """Submit a council proposal for Brain deliberation."""
        submit_council_proposal(
            self._deliberation_engine,
            proposal_id,
            title,
            description,
            proposal_type,
            proposer,
            ctx,
        )

    def trigger_referendum_from_proposal(
        self,
        proposal_id: str,
        title: str,
        description: str,
        proposer: str,
    ) -> str:
        """Trigger a referendum from a council proposal."""
        return trigger_council_referral(
            self._referendum_engine,
            proposal_id,
            title,
            description,
            proposer,
        )

    def get_deliberation_result(self, proposal_id: str) -> Optional[Any]:
        """Get deliberation result for a proposal."""
        return self._deliberation_engine.get_result(proposal_id)

    def get_referendum(self, referendum_id: str) -> Optional[Any]:
        """Get a referendum by ID."""
        return self._referendum_engine.get_referendum(referendum_id)

    def get_governance_stats(self) -> dict[str, Any]:
        """Get comprehensive governance statistics."""
        civic_rules = len(self._civic_engine.list_rules())
        enabled_rules = len([r for r in self._civic_engine.list_rules() if r.enabled])
        
        deliberation_stats = self._deliberation_engine.get_summary_stats()
        referendum_stats = self._referendum_engine.get_stats()
        
        return {
            "civic_rules": {
                "total": civic_rules,
                "enabled": enabled_rules,
                "last_heartbeat": self._last_heartbeat,
            },
            "deliberation": deliberation_stats,
            "referendums": referendum_stats,
        }


# ── Action Container ─────────────────────────────────────────────────────


@dataclass
class GovernanceActions:
    """Container for governance actions to execute."""
    
    heartbeat: int
    triggered_rules: list[Any]
    deliberation_results: list[Any]
    finalized_referendums: list[Any]
    
    should_post_city_report: bool
    should_post_health_diagnostic: bool
    should_trigger_election: bool
    should_hold_referendum: bool


# ── Global Instance ─────────────────────────────────────────────────────


_governance_layer: Optional[GovernanceLayer] = None


def get_governance_layer() -> GovernanceLayer:
    """Get the global governance layer instance."""
    global _governance_layer
    if _governance_layer is None:
        _governance_layer = GovernanceLayer()
        logger.info("GovernanceLayer: initialized global instance")
    return _governance_layer


def reset_governance_layer() -> None:
    """Reset the global governance layer (for testing)."""
    global _governance_layer
    _governance_layer = None
    logger.info("GovernanceLayer: reset global instance")
