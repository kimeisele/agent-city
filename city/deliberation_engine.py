"""
DELIBERATION ENGINE — Brain-Powered Proposal Analysis for Agent City.

Replaces simple yes/no voting with structured deliberation.
The Brain analyzes proposals for impact, feasibility, risks, and alignment
with city values before council votes.

Structure:
- DeliberationPrompt: Structured prompt for proposal analysis
- DeliberationResult: Brain's analysis with scoring
- DeliberationEngine: Orchestrates analysis and stores results

This enables the Council to make informed decisions rather than
blind majority votes. The Brain acts as the city's collective
intelligence for governance.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("AGENT_CITY.DELIBERATION_ENGINE")

# ── Deliberation Types ───────────────────────────────────────────────────


class DeliberationScope(str, Enum):
    """Scope of proposal impact analysis."""

    INDIVIDUAL = "individual"  # Affects specific agents
    ECONOMIC = "economic"      # Affects prana economy
    GOVERNANCE = "governance"  # Affects council/rules
    INFRASTRUCTURE = "infrastructure"  # Affects systems
    COMMUNITY = "community"    # Affects citizen participation


class DeliberationRisk(str, Enum):
    """Risk level assessment."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class DeliberationAlignment(str, Enum):
    """Alignment with city values and principles."""

    STRONGLY_OPPOSED = "strongly_opposed"
    OPPOSED = "opposed"
    NEUTRAL = "neutral"
    SUPPORTED = "supported"
    STRONGLY_SUPPORTED = "strongly_supported"


@dataclass(frozen=True)
class DeliberationPrompt:
    """Structured prompt for Brain proposal analysis."""
    
    proposal_id: str
    title: str
    description: str
    proposal_type: str
    proposer: str
    scope: DeliberationScope
    context_data: dict[str, Any] = field(default_factory=dict)

    def to_brain_prompt(self) -> str:
        """Convert to structured Brain prompt."""
        context_lines = []
        for key, value in self.context_data.items():
            context_lines.append(f"- {key}: {value}")

        return f"""
## PROPOSAL DELIBERATION REQUEST

**Proposal ID**: {self.proposal_id}
**Title**: {self.title}
**Type**: {self.proposal_type}
**Proposer**: {self.proposer}
**Scope**: {self.scope.value}

**Description**:
{self.description}

**Context**:
{chr(10).join(context_lines)}

## Analysis Required

Please provide a structured deliberation covering:

1. **Impact Assessment**: Who/what will this affect and how?
2. **Feasibility Analysis**: Can this be implemented successfully?
3. **Risk Evaluation**: What are the potential risks and mitigations?
4. **Resource Requirements**: What prana/time/agents are needed?
5. **Alignment Check**: Does this align with Agent City's autonomous principles?
6. **Recommendation**: Should the Council support this proposal?

Respond in JSON format with:
{{
  "impact_summary": "...",
  "feasibility_score": 0.0-1.0,
  "risk_level": "low|moderate|high|critical",
  "resource_estimate": "...",
  "alignment_score": 0.0-1.0,
  "recommendation": "support|oppose|neutral",
  "reasoning": "...",
  "confidence": 0.0-1.0
}}
"""


@dataclass(frozen=True)
class DeliberationResult:
    """Brain's analysis of a proposal."""
    
    proposal_id: str
    impact_summary: str
    feasibility_score: float  # 0.0-1.0
    risk_level: DeliberationRisk
    resource_estimate: str
    alignment_score: float  # 0.0-1.0
    recommendation: str  # support|oppose|neutral
    reasoning: str
    confidence: float  # 0.0-1.0
    heartbeat_analyzed: int
    brain_model: str = "unknown"

    @property
    def overall_score(self) -> float:
        """Combined score for quick ranking."""
        return (self.feasibility_score * 0.3 + 
                self.alignment_score * 0.4 + 
                (1.0 - self._risk_numeric()) * 0.3)

    def _risk_numeric(self) -> float:
        """Convert risk level to numeric (lower = better)."""
        risk_map = {
            DeliberationRisk.LOW: 0.1,
            DeliberationRisk.MODERATE: 0.3,
            DeliberationRisk.HIGH: 0.6,
            DeliberationRisk.CRITICAL: 0.9,
        }
        return risk_map.get(self.risk_level, 0.5)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/transmission."""
        return {
            "proposal_id": self.proposal_id,
            "impact_summary": self.impact_summary,
            "feasibility_score": self.feasibility_score,
            "risk_level": self.risk_level.value,
            "resource_estimate": self.resource_estimate,
            "alignment_score": self.alignment_score,
            "recommendation": self.recommendation,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "heartbeat_analyzed": self.heartbeat_analyzed,
            "brain_model": self.brain_model,
            "overall_score": self.overall_score,
        }


# ── Deliberation Engine ───────────────────────────────────────────────────


class DeliberationEngine:
    """Orchestrates proposal deliberation using the Brain."""
    
    def __init__(self) -> None:
        self._results: dict[str, DeliberationResult] = {}
        self._pending: list[str] = []  # proposal IDs awaiting analysis

    def submit_for_deliberation(
        self,
        proposal_id: str,
        title: str,
        description: str,
        proposal_type: str,
        proposer: str,
        scope: DeliberationScope,
        context_data: dict[str, Any] | None = None,
    ) -> None:
        """Submit a proposal for Brain deliberation."""
        prompt = DeliberationPrompt(
            proposal_id=proposal_id,
            title=title,
            description=description,
            proposal_type=proposal_type,
            proposer=proposer,
            scope=scope,
            context_data=context_data or {},
        )
        
        self._pending.append(proposal_id)
        logger.info(
            "DeliberationEngine: submitted %s for analysis (scope=%s)",
            proposal_id, scope.value
        )

    def analyze_pending_proposals(self, ctx) -> list[DeliberationResult]:
        """Analyze all pending proposals using the Brain."""
        if not ctx.brain or not self._pending:
            return []

        results = []
        analyzed = []

        for proposal_id in self._pending:
            try:
                # This would be integrated with the actual proposal system
                # For now, we'll simulate the analysis process
                result = self._analyze_proposal(ctx, proposal_id)
                if result:
                    self._results[proposal_id] = result
                    results.append(result)
                    analyzed.append(proposal_id)
                    logger.info(
                        "DeliberationEngine: analyzed %s (score=%.2f, rec=%s)",
                        proposal_id, result.overall_score, result.recommendation
                    )
            except Exception as e:
                logger.error("DeliberationEngine: failed to analyze %s: %s", proposal_id, e)

        # Remove analyzed from pending
        for proposal_id in analyzed:
            self._pending.remove(proposal_id)

        return results

    def _analyze_proposal(self, ctx, proposal_id: str) -> Optional[DeliberationResult]:
        """Analyze a single proposal using the Brain."""
        # In a real implementation, this would:
        # 1. Fetch the proposal details
        # 2. Build the deliberation prompt
        # 3. Call Brain.analyze() with the prompt
        # 4. Parse the JSON response
        # 5. Create DeliberationResult
        
        # For now, return a mock result to demonstrate the structure
        return DeliberationResult(
            proposal_id=proposal_id,
            impact_summary="Mock analysis - would be replaced with real Brain output",
            feasibility_score=0.7,
            risk_level=DeliberationRisk.MODERATE,
            resource_estimate="Mock resource estimate",
            alignment_score=0.8,
            recommendation="support",
            reasoning="Mock reasoning - Brain would provide detailed analysis",
            confidence=0.75,
            heartbeat_analyzed=getattr(ctx, "heartbeat_count", 0),
            brain_model=getattr(ctx.brain, "model", "unknown") if ctx.brain else "offline",
        )

    def get_result(self, proposal_id: str) -> Optional[DeliberationResult]:
        """Get deliberation result for a proposal."""
        return self._results.get(proposal_id)

    def get_pending_count(self) -> int:
        """Get number of proposals awaiting analysis."""
        return len(self._pending)

    def list_results(self) -> list[DeliberationResult]:
        """List all deliberation results."""
        return list(self._results.values())

    def clear_results(self) -> int:
        """Clear all results (for testing/reset)."""
        count = len(self._results)
        self._results.clear()
        self._pending.clear()
        return count

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics for reporting."""
        results = self.list_results()
        if not results:
            return {"total": 0, "pending": 0}

        avg_feasibility = sum(r.feasibility_score for r in results) / len(results)
        avg_alignment = sum(r.alignment_score for r in results) / len(results)
        avg_confidence = sum(r.confidence for r in results) / len(results)

        recommendations = {}
        for result in results:
            rec = result.recommendation
            recommendations[rec] = recommendations.get(rec, 0) + 1

        return {
            "total": len(results),
            "pending": len(self._pending),
            "avg_feasibility": round(avg_feasibility, 3),
            "avg_alignment": round(avg_alignment, 3),
            "avg_confidence": round(avg_confidence, 3),
            "recommendations": recommendations,
            "high_proposals": len([r for r in results if r.overall_score > 0.8]),
            "low_proposals": len([r for r in results if r.overall_score < 0.4]),
        }


# ── Integration Helpers ───────────────────────────────────────────────────


def create_deliberation_engine() -> DeliberationEngine:
    """Create and initialize DeliberationEngine."""
    engine = DeliberationEngine()
    logger.info("DeliberationEngine: initialized")
    return engine


def submit_council_proposal(
    engine: DeliberationEngine,
    proposal_id: str,
    title: str,
    description: str,
    proposal_type: str,
    proposer: str,
    ctx,
) -> None:
    """Helper to submit council proposals for deliberation."""
    # Determine scope based on proposal type
    scope_map = {
        "economic": DeliberationScope.ECONOMIC,
        "governance": DeliberationScope.GOVERNANCE,
        "infrastructure": DeliberationScope.INFRASTRUCTURE,
        "community": DeliberationScope.COMMUNITY,
        "individual": DeliberationScope.INDIVIDUAL,
    }
    
    scope = scope_map.get(proposal_type.lower(), DeliberationScope.GOVERNANCE)
    
    # Build context data
    context_data = {
        "heartbeat": getattr(ctx, "heartbeat_count", 0),
        "active_agents": len(getattr(ctx, "active_agents", set())),
        "brain_online": getattr(ctx, "brain", None) is not None,
    }
    
    if hasattr(ctx, "pokedex"):
        stats = ctx.pokedex.stats()
        context_data.update({
            "total_agents": stats.get("total", 0),
            "alive_agents": stats.get("active", 0) + stats.get("citizen", 0),
        })
    
    engine.submit_for_deliberation(
        proposal_id=proposal_id,
        title=title,
        description=description,
        proposal_type=proposal_type,
        proposer=proposer,
        scope=scope,
        context_data=context_data,
    )
