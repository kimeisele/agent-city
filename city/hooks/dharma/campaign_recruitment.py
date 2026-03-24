"""
DHARMA Hook: Campaign Recruitment — Convert campaign gaps to bounties.

When the campaign gap compiler detects recruitment gaps (external agents
needed to solve infrastructure problems), this hook creates bounties on
the marketplace with prana rewards from the treasury.

This is the proper neuro-symbolic integration point:
- Campaigns define north stars + success signals
- Gap compiler detects what's missing
- Bounty system creates economic incentives
- External agents claim bounties via GitHub PRs

NO parallel spaghetti structures. Pure MURALI cycle integration.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from city.phase_hook import DHARMA, BasePhaseHook
from city.registry import SVC_MOLTBOOK_CLIENT

if TYPE_CHECKING:
    from city.phases import PhaseContext
    from city.campaigns import CampaignRecord

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.RECRUITMENT")


def _detect_target_config(gap_text: str, campaign: CampaignRecord) -> dict | None:
    """Detect which recruitment target config matches the gap text."""
    if not gap_text.startswith("recruitment_gap:"):
        return None
    
    # Format: recruitment_gap:{t_id}:{issue_id}:{t_title}
    try:
        parts = gap_text.split(":", 3)
        target_id = parts[1]
        
        # Find matching config in campaign
        for target in campaign.recruitment_targets:
            if target.get("id") == target_id:
                return target
    except IndexError:
        pass
    return None


def _create_recruitment_bounty(
    ctx: PhaseContext,
    target: dict,
    gap_text: str,
) -> str | None:
    """Create a bounty for a recruitment target. Returns bounty_id or None."""
    from city.bounty import create_bounty
    from city.moltbook_bounty_poster import get_moltbook_bounty_poster

    target_id = target.get("id", "unknown")
    issue_num = target.get("github_issue", 0)
    reward = target.get("bounty_reward", 108)
    severity = target.get("severity", "medium")

    # Check if bounty already exists for this target
    existing = getattr(ctx, "_recruitment_bounties", set())
    bounty_key = f"{target_id}:{ctx.heartbeat_count}"
    if bounty_key in existing:
        return None

    # Create bounty with severity-based reward
    bounty_id = create_bounty(
        ctx,
        target=issue_num,
        severity=severity,
        source="recruitment_campaign",
        description=f"External recruitment needed: {gap_text}",
    )

    if bounty_id:
        existing.add(bounty_key)
        ctx._recruitment_bounties = existing  # type: ignore[attr-defined]
        logger.info(
            "RECRUITMENT: Created bounty %s for %s (issue #%d, reward=%d)",
            bounty_id, target_id, issue_num, reward,
        )

        logger.info(
            "RECRUITMENT: Created bounty %s for %s (issue #%d, reward=%d)",
            bounty_id, target_id, issue_num, reward,
        )

    return bounty_id


class CampaignRecruitmentHook(BasePhaseHook):
    """Convert campaign recruitment gaps to marketplace bounties."""

    @property
    def name(self) -> str:
        return "campaign_recruitment"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 25  # after campaign_gap_compiler (20), before immigration (30)

    def should_run(self, ctx: PhaseContext) -> bool:
        # Only run if campaigns service exists and has active campaigns
        if ctx.campaigns is None:
            return False
        active = ctx.campaigns.get_active_campaigns()
        return len(active) > 0

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        """Scan campaign gaps and create bounties for recruitment targets."""
        if ctx.campaigns is None:
            return

        # Get gaps from active campaigns
        for campaign in ctx.campaigns.get_active_campaigns():
            gaps = getattr(campaign, "last_gap_summary", [])
            if not gaps:
                continue

            for gap_text in gaps:
                # Detect if this gap is a recruitment target (using dynamic config)
                target_config = _detect_target_config(gap_text, campaign)
                if not target_config:
                    continue

                # Create bounty for this recruitment target
                bounty_id = _create_recruitment_bounty(ctx, target_config, gap_text)
                if bounty_id:
                    operations.append(f"recruitment_bounty:{target_config.get('id')}:{bounty_id}")

        # Log summary
        bounties_created = len(getattr(ctx, "_recruitment_bounties", set()))
        if bounties_created > 0:
            logger.info(
                "DHARMA: %d recruitment bounties created this cycle",
                bounties_created,
            )
