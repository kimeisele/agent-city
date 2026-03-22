"""
Bounty System — Economic incentives for problem-solving.

Brain detects problem → scope gate rejects → Bounty created on Marketplace.
Any agent (or Steward) can claim the bounty. Prana flows on completion.

Bounties are stored in the marketplace_orders table with asset_type='bounty'.
The "price" is the REWARD (escrowed from treasury or requester).
The "asset_id" is the bounty target (e.g., "fix:ruff_clean").

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.BOUNTY")

# Bounty reward tiers (in prana, from seed constants derivations)
BOUNTY_REWARD_LOW = 27       # NAVA × TRINITY — same as mission completion
BOUNTY_REWARD_MEDIUM = 54    # 2 × BOUNTY_LOW
BOUNTY_REWARD_HIGH = 108     # MALA — significant problem

# Bounty expiry (heartbeats)
BOUNTY_EXPIRY_HB = 20  # short-lived, urgent

# ── Severity → Reward mapping ────────────────────────────────────────

_SEVERITY_REWARD = {
    "low": BOUNTY_REWARD_LOW,
    "medium": BOUNTY_REWARD_MEDIUM,
    "high": BOUNTY_REWARD_HIGH,
}

# Targets that indicate code-fix bounties (scope-gated from Brain)
_CODE_FIX_KEYWORDS = (
    "ruff", "tests_pass", "test_pass", "lint", "contract",
    "code_health", "fix code", "repair code", "refactor",
)


def create_bounty(
    ctx: PhaseContext,
    target: str,
    *,
    severity: str = "medium",
    source: str = "brain",
    description: str = "",
) -> str | None:
    """Create a bounty on the marketplace. Returns bounty_id or None.

    The reward prana comes from the zone treasury (public good).
    If treasury is insufficient, bounty is created with reduced reward.
    """
    if ctx.sankalpa is None:
        return None

    reward = _SEVERITY_REWARD.get(severity, BOUNTY_REWARD_MEDIUM)
    bounty_id = f"bounty:{target[:50]}:{ctx.heartbeat_count}"

    # Dedup: skip if active bounty for same target exists
    try:
        active_orders = ctx.pokedex.get_active_orders(asset_type="bounty")
        for order in active_orders:
            if order.get("asset_id", "").startswith(f"fix:{target[:30]}"):
                logger.debug("Bounty dedup: %s already active", target[:50])
                return None
    except Exception:
        pass

    # Create as marketplace order with asset_type="bounty"
    # The "seller" is the treasury (public escrow), "price" is the reward
    try:
        from city.seed_constants import ORDER_EXPIRY_HEARTBEATS

        # Use a shorter expiry for bounties (urgent work)
        order_id = ctx.pokedex._create_bounty_order(
            target=target[:120],
            reward=reward,
            heartbeat=ctx.heartbeat_count,
            expiry_hb=BOUNTY_EXPIRY_HB,
            source=source,
            description=description[:200],
        )
        if order_id is not None:
            logger.info(
                "BOUNTY: created #%s — target='%s' reward=%d source=%s",
                order_id, target[:60], reward, source,
            )
            return str(order_id)
    except Exception as exc:
        logger.warning("BOUNTY: creation failed: %s", exc)

    return None


def claim_bounty(ctx: PhaseContext, order_id: int, claimer: str) -> bool:
    """Claim a bounty. Prana transferred from escrow to claimer on completion."""
    try:
        receipt = ctx.pokedex.fill_order(
            order_id, claimer, ctx.heartbeat_count,
        )
        if receipt:
            logger.info(
                "BOUNTY: claimed #%d by %s (reward=%d)",
                order_id, claimer, receipt.get("price", 0),
            )
            return True
    except Exception as exc:
        logger.warning("BOUNTY: claim failed: %s", exc)
    return False
