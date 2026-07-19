"""
Tests for DHARMA Campaign Recruitment Hook.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from city.campaigns import CampaignRecord
from city.hooks.dharma.campaign_recruitment import (
    CampaignRecruitmentHook,
    _detect_target_config,
)


_CAMPAIGNS = json.loads(
    (Path(__file__).parents[1] / "campaigns" / "default.json").read_text()
)["campaigns"]
_RECRUITMENT_CAMPAIGN = next(
    campaign for campaign in _CAMPAIGNS if campaign["id"] == "federation-recruitment"
)


def _campaign_with_targets() -> CampaignRecord:
    return CampaignRecord.from_dict(_RECRUITMENT_CAMPAIGN)


class TestRecruitmentTargetDetection:
    """Test gap text → recruitment target mapping."""

    def test_detect_nadi_reliability(self):
        """Campaign compiler gap resolves to the configured NADI target."""
        campaign = _campaign_with_targets()
        gap = "recruitment_gap:nadi-reliability:360:NADI reliability"
        assert _detect_target_config(gap, campaign) == campaign.recruitment_targets[0]

    def test_detect_brain_cognition(self):
        """Campaign compiler gap resolves to the configured brain target."""
        campaign = _campaign_with_targets()
        gap = "recruitment_gap:brain-cognition-latency:131:Brain latency"
        assert _detect_target_config(gap, campaign) == campaign.recruitment_targets[1]

    def test_detect_cross_zone_economy(self):
        """Campaign compiler gap resolves to the configured economy target."""
        campaign = _campaign_with_targets()
        gap = "recruitment_gap:cross-zone-economy:348:Cross-zone economy"
        assert _detect_target_config(gap, campaign) == campaign.recruitment_targets[2]

    def test_unknown_gap_returns_none(self):
        """Non-compiler text and unknown target IDs return None."""
        campaign = _campaign_with_targets()
        assert _detect_target_config("random infrastructure thing", campaign) is None
        assert _detect_target_config("recruitment_gap:unknown:1:unknown", campaign) is None
        assert _detect_target_config("", campaign) is None


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
        campaign = _campaign_with_targets()
        campaign.last_gap_summary = ["recruitment_gap:nadi-reliability:360:NADI reliability"]
        ctx.campaigns.get_active_campaigns.return_value = [campaign]
        ctx.heartbeat_count = 42
        ctx._recruitment_bounties = set()

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
        campaign = _campaign_with_targets()
        campaign.last_gap_summary = [
            "recruitment_gap:nadi-reliability:360:NADI reliability",
            "recruitment_gap:nadi-reliability:360:NADI message drops",
        ]
        ctx.campaigns.get_active_campaigns.return_value = [campaign]
        ctx.heartbeat_count = 42
        ctx._recruitment_bounties = set()

        hook = CampaignRecruitmentHook()
        operations = []
        hook.execute(ctx, operations)

        assert mock_create_bounty.call_count == 1

    def test_execute_no_matching_gaps(self):
        """Hook skips if no recruitment gaps detected."""
        ctx = MagicMock()
        campaign = _campaign_with_targets()
        campaign.last_gap_summary = ["random unrelated gap"]
        ctx.campaigns.get_active_campaigns.return_value = [campaign]

        hook = CampaignRecruitmentHook()
        operations = []
        hook.execute(ctx, operations)

        assert not any("recruitment_bounty" in op for op in operations)


class TestRecruitmentTargetsConfig:
    """Test recruitment target configuration."""

    def test_all_targets_have_required_fields(self):
        """Each manifest target has the fields consumed by the hook."""
        required = {"id", "title", "github_issue", "severity", "bounty_reward"}
        for config in _RECRUITMENT_CAMPAIGN["recruitment_targets"]:
            assert required <= set(config), f"Target {config['id']} missing fields"

    def test_severity_levels_valid(self):
        """Severity must be low, medium, or high."""
        valid = {"low", "medium", "high"}
        for config in _RECRUITMENT_CAMPAIGN["recruitment_targets"]:
            assert config["severity"] in valid

    def test_reward_tiers_reasonable(self):
        """Rewards should match bounty system tiers (27, 54, 108)."""
        valid_rewards = {27, 54, 108}
        for config in _RECRUITMENT_CAMPAIGN["recruitment_targets"]:
            assert config["bounty_reward"] in valid_rewards
