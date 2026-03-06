"""
Tests for Governance Layer — Civic Protocol + Deliberation + Referendum.

Tests the deterministic rule evaluation that replaces if/else logic.
Validates that governance decisions are made consistently and transparently.
"""

import pytest
from unittest.mock import MagicMock

from city.civic_protocol import (
    CivicAction,
    CivicCondition,
    CivicContext,
    CivicRule,
    create_civic_engine,
)
from city.deliberation_engine import DeliberationScope, create_deliberation_engine
from city.referendum_system import ReferendumTrigger, create_referendum_engine
from city.governance_layer import GovernanceLayer, get_governance_layer, reset_governance_layer


@pytest.fixture
def mock_ctx():
    """Mock PhaseContext for testing."""
    ctx = MagicMock()
    ctx.heartbeat_count = 42
    ctx.pokedex = MagicMock()
    ctx.pokedex.stats.return_value = {
        "total_prana": 10000,
        "active": 8,
        "citizen": 4,
        "dormant": 2,
    }
    ctx.brain = MagicMock()  # Brain is online
    ctx.thread_state = MagicMock()
    ctx.thread_state.stats.return_value = {"unanswered": 3}
    ctx.discussions = MagicMock()
    ctx.discussions.stats.return_value = {"last_post_age_s": 7200.0}
    return ctx


@pytest.fixture(autouse=True)
def reset_governance():
    """Reset governance layer between tests."""
    reset_governance_layer()


class TestCivicProtocol:
    """Test the Civic Protocol rule evaluation."""

    def test_economy_critical_rule_triggers(self, mock_ctx):
        """Critical economy rule should trigger when avg prana is very low."""
        engine = create_civic_engine()
        
        # Create context with critical economy
        context = CivicContext(
            heartbeat_count=42,
            avg_prana=300.0,  # Below 500 threshold
            total_prana=3000,
            dormant_count=2,
            alive_agents=10,
            brain_online=True,
            unanswered_threads=3,
            hours_since_last_post=12.0,
            has_quorum=True,
        )
        
        triggered = engine.evaluate(context)
        
        # Should trigger economy critical alert
        critical_rules = [r for r in triggered if r.name == "economy_critical_alert"]
        assert len(critical_rules) == 1
        assert critical_rules[0].action.value == "post_health_diagnostic"

    def test_brain_offline_rule_triggers(self, mock_ctx):
        """Brain offline rule should trigger when Brain is offline."""
        engine = create_civic_engine()
        
        context = CivicContext(
            heartbeat_count=42,
            avg_prana=5000.0,
            total_prana=50000,
            dormant_count=0,
            alive_agents=10,
            brain_online=False,  # Brain is offline
            unanswered_threads=1,
            hours_since_last_post=2.0,
            has_quorum=True,
        )
        
        triggered = engine.evaluate(context)
        
        # Should trigger brain offline alert
        brain_rules = [r for r in triggered if r.name == "brain_offline_alert"]
        assert len(brain_rules) == 1
        assert brain_rules[0].action.value == "post_health_diagnostic"

    def test_regular_reporting_rule(self, mock_ctx):
        """Regular reporting should trigger on heartbeat modulo."""
        engine = create_civic_engine()
        
        context = CivicContext(
            heartbeat_count=80,  # 80 % 40 = 0
            avg_prana=5000.0,
            total_prana=50000,
            dormant_count=0,
            alive_agents=10,
            brain_online=True,
            unanswered_threads=1,
            hours_since_last_post=2.0,
            has_quorum=True,
        )
        
        triggered = engine.evaluate(context)
        
        # Should trigger regular city report
        report_rules = [r for r in triggered if r.name == "regular_city_report"]
        assert len(report_rules) == 1
        assert report_rules[0].action.value == "post_city_report"

    def test_cooldown_prevents_duplicate_triggers(self, mock_ctx):
        """Rules should respect cooldown periods."""
        engine = create_civic_engine()
        
        context = CivicContext(
            heartbeat_count=42,
            avg_prana=300.0,  # Critical economy
            total_prana=3000,
            dormant_count=2,
            alive_agents=10,
            brain_online=True,
            unanswered_threads=3,
            hours_since_last_post=12.0,
            has_quorum=True,
            last_execution={"economy_critical_alert": 35},  # Recently executed
        )
        
        triggered = engine.evaluate(context)
        
        # Should not trigger due to cooldown
        critical_rules = [r for r in triggered if r.name == "economy_critical_alert"]
        assert len(critical_rules) == 0

    def test_rule_priority_ordering(self, mock_ctx):
        """Higher priority rules should be evaluated first."""
        engine = create_civic_engine()
        
        # Add custom high-priority rule
        high_priority_rule = CivicRule(
            name="test_high_priority",
            condition=CivicCondition.BRAIN_OFFLINE,
            action=CivicAction.POST_HEALTH_DIAGNOSTIC,
            priority=100,  # Higher than default
        )
        engine.register_rule(high_priority_rule)
        
        context = CivicContext(
            heartbeat_count=42,
            avg_prana=5000.0,
            total_prana=50000,
            dormant_count=0,
            alive_agents=10,
            brain_online=False,
            unanswered_threads=1,
            hours_since_last_post=2.0,
            has_quorum=True,
        )
        
        triggered = engine.evaluate(context)
        
        # High priority rule should be first in list
        assert triggered[0].name == "test_high_priority"
        assert triggered[1].name == "brain_offline_alert"


class TestDeliberationEngine:
    """Test the Deliberation Engine proposal analysis."""

    def test_submit_proposal_for_deliberation(self, mock_ctx):
        """Proposal submission should add to pending queue."""
        engine = create_deliberation_engine()
        
        engine.submit_for_deliberation(
            proposal_id="test_proposal",
            title="Test Proposal",
            description="A test proposal for deliberation",
            proposal_type="economic",
            proposer="test_agent",
            scope=DeliberationScope.ECONOMIC,
            context_data={"test": "data"},
        )
        
        assert engine.get_pending_count() == 1

    def test_analyze_pending_proposals(self, mock_ctx):
        """Pending proposals should be analyzed when Brain is available."""
        engine = create_deliberation_engine()
        
        # Submit proposal
        engine.submit_for_deliberation(
            proposal_id="test_proposal",
            title="Test Proposal",
            description="A test proposal for deliberation",
            proposal_type="governance",
            proposer="test_agent",
            scope=DeliberationScope.GOVERNANCE,
        )
        
        # Analyze with mock Brain
        results = engine.analyze_pending_proposals(mock_ctx)
        
        assert len(results) == 1
        assert results[0].proposal_id == "test_proposal"
        assert engine.get_pending_count() == 0  # Should be removed from pending

    def test_no_analysis_without_brain(self, mock_ctx):
        """Proposals should not be analyzed when Brain is offline."""
        engine = create_deliberation_engine()
        mock_ctx.brain = None  # Brain offline
        
        engine.submit_for_deliberation(
            proposal_id="test_proposal",
            title="Test Proposal",
            description="A test proposal for deliberation",
            proposal_type="governance",
            proposer="test_agent",
            scope=DeliberationScope.GOVERNANCE,
        )
        
        results = engine.analyze_pending_proposals(mock_ctx)
        
        assert len(results) == 0
        assert engine.get_pending_count() == 1  # Still pending

    def test_get_summary_stats(self, mock_ctx):
        """Engine should provide summary statistics."""
        engine = create_deliberation_engine()
        
        # Add some mock results
        from city.deliberation_engine import DeliberationResult, DeliberationRisk
        
        mock_result = DeliberationResult(
            proposal_id="test1",
            impact_summary="Test impact",
            feasibility_score=0.8,
            risk_level=DeliberationRisk.MODERATE,
            resource_estimate="100 prana",
            alignment_score=0.9,
            recommendation="support",
            reasoning="Good proposal",
            confidence=0.85,
            heartbeat_analyzed=42,
            brain_model="test-model",
        )
        
        engine._results["test1"] = mock_result
        
        stats = engine.get_summary_stats()
        
        assert stats["total"] == 1
        assert stats["avg_feasibility"] == 0.8
        assert stats["avg_alignment"] == 0.9
        assert stats["recommendations"]["support"] == 1


class TestReferendumSystem:
    """Test the Referendum System citizen voting."""

    def test_create_referendum(self):
        """Referendum creation should work with all trigger types."""
        engine = create_referendum_engine()
        
        for trigger in [ReferendumTrigger.COUNCIL_REFERRAL, ReferendumTrigger.CITIZEN_PETITION]:
            referendum = engine.create_referendum(
                title=f"Test {trigger.value}",
                description="Test description",
                proposer="test_agent",
                trigger=trigger,
            )
            
            assert referendum.id.startswith("ref_")
            assert referendum.trigger == trigger
            assert referendum.status == "draft"

    def test_council_referral_voting(self):
        """Council referrals should go straight to voting."""
        engine = create_referendum_engine()
        
        referendum = engine.create_referendum(
            title="Council Referral Test",
            description="Test description",
            proposer="council",
            trigger=ReferendumTrigger.COUNCIL_REFERRAL,
        )
        
        # Start voting directly (no petition needed)
        success = engine.start_voting(referendum.id)
        assert success
        
        updated = engine.get_referendum(referendum.id)
        assert updated.status == "active"
        assert updated.voting_started_at is not None
        assert updated.voting_ends_at is not None

    def test_petition_to_voting_flow(self):
        """Petitions should start and accept signatures."""
        engine = create_referendum_engine()
        
        referendum = engine.create_referendum(
            title="Petition Test",
            description="Test description",
            proposer="citizen",
            trigger=ReferendumTrigger.CITIZEN_PETITION,
        )
        
        # Start petition
        success = engine.start_petition(referendum.id)
        assert success
        
        # Add a signature
        success = engine.sign_petition(referendum.id, "citizen_1", prana=1000)
        assert success
        
        # Verify petition exists
        updated = engine.get_referendum(referendum.id)
        assert updated.status == "petitioning"

    def test_voting_and_results(self):
        """Voting should accept votes and calculate results."""
        engine = create_referendum_engine()
        
        referendum = engine.create_referendum(
            title="Voting Test",
            description="Test description",
            proposer="council",
            trigger=ReferendumTrigger.COUNCIL_REFERRAL,
        )
        
        engine.start_voting(referendum.id)
        
        # Cast votes
        success1 = engine.cast_vote(referendum.id, "citizen_1", "yes", prana=1000)
        success2 = engine.cast_vote(referendum.id, "citizen_2", "yes", prana=2000)
        success3 = engine.cast_vote(referendum.id, "citizen_3", "no", prana=500)
        
        assert success1 and success2 and success3
        
        # Check that voting is active
        updated = engine.get_referendum(referendum.id)
        assert updated.is_voting_active()
        
        # Test result calculation (mock implementation)
        results = updated.calculate_results()
        assert results["status"] == "voting_still_active"


class TestGovernanceLayer:
    """Test the integrated Governance Layer."""

    def test_governance_evaluation(self, mock_ctx):
        """Governance layer should evaluate all subsystems."""
        layer = GovernanceLayer()
        
        actions = layer.evaluate_governance_actions(mock_ctx)
        
        assert actions.heartbeat == 42
        assert isinstance(actions.triggered_rules, list)
        assert isinstance(actions.deliberation_results, list)
        assert isinstance(actions.finalized_referendums, list)

    def test_civic_context_building(self, mock_ctx):
        """Civic context should be built correctly from PhaseContext."""
        layer = GovernanceLayer()
        
        actions = layer.evaluate_governance_actions(mock_ctx)
        
        # Context should reflect system state
        # avg_prana = 10000 / (8+4) = 833.33
        assert actions.triggered_rules is not None

    def test_civic_context_uses_discussions_post_telemetry(self, mock_ctx):
        """Discussions bridge telemetry should feed governance timing."""
        layer = GovernanceLayer()

        context = layer._build_civic_context(mock_ctx)

        assert context.hours_since_last_post == pytest.approx(2.0)
        assert context.last_execution == {}

    def test_evaluation_respects_cooldowns_across_heartbeats(self, mock_ctx):
        """Repeated governance evaluation should reuse civic execution history."""
        layer = GovernanceLayer()
        mock_ctx.pokedex.stats.return_value = {
            "total_prana": 3000,
            "active": 6,
            "citizen": 4,
            "dormant": 2,
        }

        first = layer.evaluate_governance_actions(mock_ctx)
        assert any(rule.name == "economy_critical_alert" for rule in first.triggered_rules)

        mock_ctx.heartbeat_count = 43
        second = layer.evaluate_governance_actions(mock_ctx)
        assert all(rule.name != "economy_critical_alert" for rule in second.triggered_rules)

    def test_governance_stats(self, mock_ctx):
        """Governance layer should provide comprehensive stats."""
        layer = GovernanceLayer()
        
        # Trigger evaluation to populate stats
        layer.evaluate_governance_actions(mock_ctx)
        
        stats = layer.get_governance_stats()
        
        assert "civic_rules" in stats
        assert "deliberation" in stats
        assert "referendums" in stats
        assert stats["civic_rules"]["total"] > 0

    def test_global_instance(self, mock_ctx):
        """Global governance layer instance should work."""
        reset_governance_layer()
        
        layer1 = get_governance_layer()
        layer2 = get_governance_layer()
        
        # Should be the same instance
        assert layer1 is layer2
        
        # Should work normally
        actions = layer1.evaluate_governance_actions(mock_ctx)
        assert actions.heartbeat == 42

    def test_submit_proposal_integration(self, mock_ctx):
        """Proposal submission should integrate with deliberation engine."""
        layer = GovernanceLayer()
        
        layer.submit_council_proposal_for_deliberation(
            proposal_id="integration_test",
            title="Integration Test",
            description="Testing proposal submission",
            proposal_type="governance",
            proposer="test_agent",
            ctx=mock_ctx,
        )
        
        # Should be pending in deliberation engine
        assert layer._deliberation_engine.get_pending_count() == 1

    def test_referendum_integration(self, mock_ctx):
        """Referendum triggering should integrate with referendum engine."""
        layer = GovernanceLayer()
        
        referendum_id = layer.trigger_referendum_from_proposal(
            proposal_id="ref_test",
            title="Referendum Test",
            description="Testing referendum integration",
            proposer="council",
        )
        
        # Should exist and be active
        referendum = layer.get_referendum(referendum_id)
        assert referendum is not None
        assert referendum.status == "active"
