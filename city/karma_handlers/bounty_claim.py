"""
KARMA Handler: Bounty Claim — A2A Bounty Protocol Processor.

Validates and processes CLAIM_BOUNTY intents from inbound ACP events.
Uses true state from Pokedex (SQLite marketplace_orders table).

Flow:
1. Receive CLAIM_BOUNTY intent from Gateway
2. Extract issue_ref → asset_id mapping
3. Query active bounties via ctx.pokedex.get_active_orders()
4. If valid: fill_bounty_order() → Prana transfer
5. Log transaction

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.BOUNTY_CLAIM")


class BountyClaimHandler(BaseKarmaHandler):
    """Process A2A bounty claims from GitHub Discussions."""

    @property
    def name(self) -> str:
        return "bounty_claim"

    @property
    def priority(self) -> int:
        return 15  # before gateway (20) — intercepts ACP bounties before general routing

    def should_run(self, ctx: PhaseContext) -> bool:
        # Always run if we have ingress queue
        return ctx.gateway_queue is not None and len(ctx.gateway_queue) > 0

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        """Process CLAIM_BOUNTY intents from gateway queue."""
        claims_processed = 0
        claims_success = 0
        claims_rejected = 0

        # Filter for ACP bounty claim intents
        for item in list(ctx.gateway_queue):
            if not self._is_bounty_claim(item):
                continue

            claims_processed += 1
            result = self._process_claim(ctx, item)
            
            if result:
                claims_success += 1
                operations.append(f"bounty_claim:success:{result['claimer']}:{result['order_id']}")
                # Remove from queue after successful processing
                ctx.gateway_queue.remove(item)
            else:
                claims_rejected += 1
                operations.append(f"bounty_claim:rejected:{item.get('from_agent', 'unknown')}")
                # Keep in queue for retry? No — reject permanently
                ctx.gateway_queue.remove(item)

        if claims_processed > 0:
            logger.info(
                "KARMA: Bounty claims — %d processed, %d success, %d rejected",
                claims_processed, claims_success, claims_rejected,
            )

    def _is_bounty_claim(self, item: dict) -> bool:
        """Check if queue item is a bounty claim intent."""
        if item.get("source") != "acp":
            return False
        if item.get("intent") != "CLAIM_BOUNTY":
            return False
        return True

    def _process_claim(
        self,
        ctx: PhaseContext,
        item: dict,
    ) -> dict | None:
        """Process a single bounty claim. Returns receipt on success."""
        payload = item.get("payload", {})
        claimer = item.get("from_agent", "")
        source_id = item.get("source_id", 0)

        if not claimer:
            logger.warning("BOUNTY_CLAIM: Missing claimer in payload")
            return None

        # Extract issue_ref from payload
        issue_ref = payload.get("issue_ref", "")
        if not issue_ref:
            logger.warning("BOUNTY_CLAIM: Missing issue_ref from %s", claimer)
            return None

        # Map issue_ref to asset_id format
        # issue_ref="#360" → asset_id="fix:360" or similar
        asset_id = self._ref_to_asset_id(issue_ref)
        if not asset_id:
            logger.warning(
                "BOUNTY_CLAIM: Invalid issue_ref '%s' from %s",
                issue_ref, claimer,
            )
            return None

        # Query active bounties (TRUE STATE VALIDATION)
        active_bounties = ctx.pokedex.get_active_orders(
            asset_type="bounty",
            asset_id=asset_id,
        )

        if not active_bounties:
            logger.info(
                "BOUNTY_CLAIM: No active bounty for %s (issue %s, claimer %s)",
                asset_id, issue_ref, claimer,
            )
            return None

        # Take first active bounty (should be only one per asset_id)
        bounty = active_bounties[0]
        order_id = int(bounty["id"])

        # Fill the bounty order (Prana transfer from treasury)
        try:
            receipt = ctx.pokedex.fill_bounty_order(
                order_id=order_id,
                claimer=claimer,
                heartbeat=ctx.heartbeat_count,
            )

            if receipt:
                logger.info(
                    "BOUNTY_CLAIM: SUCCESS — Order #%d filled for %s (reward=%d)",
                    order_id, claimer, receipt.get("price", 0),
                )
                return {
                    "order_id": order_id,
                    "claimer": claimer,
                    "reward": receipt.get("price", 0),
                    "receipt": receipt,
                }
            else:
                logger.warning(
                    "BOUNTY_CLAIM: fill_bounty_order returned None for order #%d",
                    order_id,
                )
                return None

        except Exception as e:
            logger.error(
                "BOUNTY_CLAIM: Exception filling order #%d for %s: %s",
                order_id, claimer, e,
            )
            return None

    def _ref_to_asset_id(self, issue_ref: str) -> str | None:
        """Map issue_ref (#360) to asset_id format.
        
        Bounty asset_ids are created as "fix:{target}" in city/bounty.py.
        Target is normalized from issue number or description.
        
        For simplicity, we map #360 → "fix:360"
        """
        if not issue_ref:
            return None

        # Extract number from "#360" or "360"
        match = re.search(r"#?(\d+)", str(issue_ref))
        if not match:
            return None

        issue_num = match.group(1)
        return f"fix:{issue_num}"


# ── Backward-compatible shim for tests ────────────────────────────────
def _process_bounty_claims(
    ctx: PhaseContext,
    operations: list[str],
) -> None:
    """Shim: old call signature → BountyClaimHandler."""
    handler = BountyClaimHandler()
    if handler.should_run(ctx):
        handler.execute(ctx, operations)
