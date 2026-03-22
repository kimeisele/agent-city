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
import re
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


def _normalized_target_key(target: str) -> str:
    lowered = target.lower().strip()
    if lowered.startswith("brain_bottleneck_"):
        lowered = lowered[len("brain_bottleneck_"):]
        lowered = re.sub(r"_\d+$", "", lowered)
    if "ruff" in lowered:
        return "ruff_clean"
    if "tests_pass" in lowered or "test_pass" in lowered or "tests" in lowered:
        return "tests_pass"
    if "integrity" in lowered:
        return "integrity"
    if "code_health" in lowered:
        return "code_health"
    if "engagement" in lowered:
        return "engagement"
    token = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return token[:100] or "unknown"


def _bounty_asset_id(target: str) -> str:
    return f"fix:{_normalized_target_key(target)}"


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

    from city.pokedex import SYSTEM_TREASURY

    reward = _SEVERITY_REWARD.get(severity, BOUNTY_REWARD_MEDIUM)
    try:
        treasury_balance = int(ctx.pokedex._bank.get_balance(SYSTEM_TREASURY))
        reward = min(reward, max(treasury_balance, 0))
    except Exception:
        pass
    if reward <= 0:
        return None

    asset_id = _bounty_asset_id(target)
    bounty_id = f"bounty:{asset_id}:{ctx.heartbeat_count}"

    # Dedup: skip if active bounty for same target exists
    try:
        active_orders = ctx.pokedex.get_active_orders(asset_type="bounty", asset_id=asset_id)
        if active_orders:
            logger.debug("Bounty dedup: %s already active", asset_id)
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
            asset_id=asset_id,
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
        receipt = ctx.pokedex.fill_bounty_order(
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


def resolve_bounties_for_missions(ctx: PhaseContext, terminal_missions: list[dict]) -> list[dict]:
    claimed: list[dict] = []
    for mission in terminal_missions:
        if mission.get("status") != "completed":
            continue

        owner = str(mission.get("owner", ""))
        if not owner or owner in {"reported", "unknown", "mayor", "dharma"}:
            continue

        mission_id = str(mission.get("id", ""))
        mission_name = str(mission.get("name", ""))
        if not mission_id.startswith("brain_bottleneck_"):
            continue

        asset_id = _bounty_asset_id(f"{mission_id} {mission_name}")
        try:
            open_orders = ctx.pokedex.get_active_orders(asset_type="bounty", asset_id=asset_id)
        except Exception:
            continue

        for order in open_orders:
            if claim_bounty(ctx, int(order["id"]), owner):
                claimed.append(
                    {
                        "agent": owner,
                        "asset": "bounty",
                        "mission": mission_id,
                        "bounty": asset_id,
                        "prana": int(order.get("price", 0) or 0),
                        "order_id": int(order["id"]),
                    }
                )
                break

    return claimed
