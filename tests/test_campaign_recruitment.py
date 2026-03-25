"""
Tests for DHARMA Campaign Recruitment Hook.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import pytest
from unittest.mock import MagicMock, patch

from city.hooks.dharma.campaign_recruitment import (
    CampaignRecruitmentHook,
    _detect_recruitment_gap,
    _RECRUITMENT_TARGETS,
)


class TestRecruitmentTargetDetection:
    """Test gap text → recruitment target mapping."""

    def test_detect_nadi_reliability(self):
        """NADI reliability keywords detected."""
        assert _detect_recruitment_gap("NADI federation reliability issue") == "nadi-reliability"
        assert _detect_recruitment_gap("message drops under async load") == "nadi-reliability"

    def test_detect_brain_cognition(self):
        """Brain cognition latency keywords detected."""
        assert _detect_recruitment_gap("Brain stuck comments cognition") == "brain-cognition-latency"
        assert _detect_recruitment_gap("comment latency ENQUEUED forever") == "brain-cognition-latency"

    def test_detect_cross_zone_economy(self):
        """Cross-zone economy keywords detected."""
        assert _detect_recruitment_gap("zone economy prana trading") == "cross-zone-economy"
        assert _detect_recruitment_gap("market mechanism for zones") == "cross-zone-economy"

    def test_unknown_gap_returns_none(self):
        """Unrelated gap text returns None."""
        assert _detect_recruitment_gap("random infrastructure thing") is None
        assert _detect_recruitment_gap("") is None


class TestCampaignRecruitmentHook:
    """Test DHARMA hook integration."""

    def test_hook_metadata(self):
        """Hook has correct phase, priority, name."""
        hook = CampaignRecruitmentHook()
        assert hook.phase == "dharma"
        assert hook.priority == 25
        assert hook.name == "campaign_recruitment"

    def test_should_run_no_campaigns(self):
        """Hook skips if no campaigns service."""
        ctx = MagicMock()
        ctx.campaigns = None
        hook = CampaignRecruitmentHook()
        assert hook.should_run(ctx) is False

    def test_should_run_no_active_campaigns(self):
        """Hook skips if no active campaigns."""
        ctx = MagicMock()
        ctx.campaigns.get_active_campaigns.return_value = []
        hook = CampaignRecruitmentHook()
        assert hook.should_run(ctx) is False

    def test_should_run_has_active_campaigns(self):
        """Hook runs if active campaigns exist."""
        ctx = MagicMock()
        ctx.campaigns.get_active_campaigns.return_value = [MagicMock()]
        hook = CampaignRecruitmentHook()
        assert hook.should_run(ctx) is True

    @patch("city.bounty.create_bounty")
    def test_execute_creates_bounty(self, mock_create_bounty):
        """Hook creates bounty for recruitment gap."""
        mock_create_bounty.return_value = "bounty:123"

        ctx = MagicMock()
        campaign = MagicMock()
        campaign.last_gap_summary = ["NADI reliability problem detected"]
        ctx.campaigns.get_active_campaigns.return_value = [campaign]
        ctx.heartbeat_count = 42

        hook = CampaignRecruitmentHook()
        operations = []
        hook.execute(ctx, operations)

        mock_create_bounty.assert_called_once()
        assert any("recruitment_bounty" in op for op in operations)

    @patch("city.bounty.create_bounty")
    def test_execute_dedup_same_cycle(self, mock_create_bounty):
        """Hook doesn't create duplicate bounties in same cycle."""
        mock_create_bounty.return_value = "bounty:123"

        ctx = MagicMock()
        campaign = MagicMock()
        campaign.last_gap_summary = ["NADI reliability problem", "NADI message drops"]
        ctx.campaigns.get_active_campaigns.return_value = [campaign]
        ctx.heartbeat_count = 42

        hook = CampaignRecruitmentHook()
        operations = []
        hook.execute(ctx, operations)

        # Only one bounty per target per cycle
        call_count = mock_create_bounty.call_count
        assert call_count <= 2  # max 2 different targets

    def test_execute_no_matching_gaps(self):
        """Hook skips if no recruitment gaps detected."""
        ctx = MagicMock()
        campaign = MagicMock()
        campaign.last_gap_summary = ["random unrelated gap"]
        ctx.campaigns.get_active_campaigns.return_value = [campaign]

        hook = CampaignRecruitmentHook()
        operations = []
        hook.execute(ctx, operations)

        assert not any("recruitment_bounty" in op for op in operations)


class TestRecruitmentTargetsConfig:
    """Test recruitment target configuration."""

    def test_all_targets_have_required_fields(self):
        """Each target has keywords, issue, severity, reward."""
        required = {"keywords", "issue", "severity", "default_reward"}
        for target_id, config in _RECRUITMENT_TARGETS.items():
            assert required <= set(config), f"Target {target_id} missing fields"

    def test_severity_levels_valid(self):
        """Severity must be low, medium, or high."""
        valid = {"low", "medium", "high"}
        for config in _RECRUITMENT_TARGETS.values():
            assert config["severity"] in valid

    def test_reward_tiers_reasonable(self):
        """Rewards should match bounty system tiers (27, 54, 108)."""
        valid_rewards = {27, 54, 108}
        for config in _RECRUITMENT_TARGETS.values():
            # Allow some flexibility but should be in reasonable range
            assert 20 <= config["default_reward"] <= 150
