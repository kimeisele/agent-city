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
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.RECRUITMENT")

# Recruitment target keywords that map to existing GitHub issues
_RECRUITMENT_TARGETS = {
    "nadi-reliability": {
        "keywords": {"nadi", "federation", "reliability", "message", "async"},
        "issue": 360,
        "severity": "high",
        "default_reward": 108,  # MALA
    },
    "brain-cognition-latency": {
        "keywords": {"brain", "cognition", "stuck", "comment", "latency"},
        "issue": 131,
        "severity": "high",
        "default_reward": 108,
    },
    "cross-zone-economy": {
        "keywords": {"zone", "economy", "prana", "trading", "market"},
        "issue": 348,
        "severity": "medium",
        "default_reward": 54,  # 2 × TRINITY
    },
}


def _detect_recruitment_gap(gap_text: str) -> str | None:
    """Detect which recruitment target a gap text refers to."""
    text_lower = gap_text.lower()
    for target_id, config in _RECRUITMENT_TARGETS.items():
        if any(kw in text_lower for kw in config["keywords"]):
            return target_id
    return None


def _create_recruitment_bounty(
    ctx: PhaseContext,
    target_id: str,
    gap_text: str,
) -> str | None:
    """Create a bounty for a recruitment target. Returns bounty_id or None."""
    from city.bounty import create_bounty

    config = _RECRUITMENT_TARGETS.get(target_id)
    if not config:
        return None

    # Check if bounty already exists for this target
    existing = getattr(ctx, "_recruitment_bounties", set())
    bounty_key = f"{target_id}:{ctx.heartbeat_count}"
    if bounty_key in existing:
        logger.debug("Recruitment bounty %s already created this cycle", bounty_key)
        return None

    # Create bounty with severity-based reward
    bounty_id = create_bounty(
        ctx,
        target=config["issue"],
        severity=config["severity"],
        source="recruitment_campaign",
        description=f"External recruitment needed: {gap_text[:200]}",
    )

    if bounty_id:
        existing.add(bounty_key)
        ctx._recruitment_bounties = existing  # type: ignore[attr-defined]
        logger.info(
            "RECRUITMENT: Created bounty %s for %s (issue #%d, reward=%d)",
            bounty_id, target_id, config["issue"], config["default_reward"],
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
                # Detect if this gap is a recruitment target
                target_id = _detect_recruitment_gap(gap_text)
                if not target_id:
                    continue

                # Create bounty for this recruitment target
                bounty_id = _create_recruitment_bounty(ctx, target_id, gap_text)
                if bounty_id:
                    operations.append(f"recruitment_bounty:{target_id}:{bounty_id}")

        # Log summary
        bounties_created = len(getattr(ctx, "_recruitment_bounties", set()))
        if bounties_created > 0:
            logger.info(
                "DHARMA: %d recruitment bounties created this cycle",
                bounties_created,
            )
