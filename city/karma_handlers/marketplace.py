"""Marketplace Handler — Auto-list surplus, need-driven auto-match, anti-Pac-Man."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.MARKETPLACE")


class MarketplaceHandler(BaseKarmaHandler):
    """Marketplace: expire stale orders, auto-list surplus, need-driven auto-match."""

    @property
    def name(self) -> str:
        return "marketplace"

    @property
    def priority(self) -> int:
        return 60

    def should_run(self, ctx: PhaseContext) -> bool:
        # Council freeze gate
        if ctx.council is not None and ctx.council.is_market_frozen:
            return False
        return True

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        all_specs = getattr(ctx, "_all_specs", {})
        all_inventories = getattr(ctx, "_all_inventories", {})

        # Council freeze (redundant but safe — also logged)
        if ctx.council is not None and ctx.council.is_market_frozen:
            operations.append("marketplace:frozen_by_council")
            return

        from city.seed_constants import WORKER_VISA_STIPEND

        # Step 1: Expire stale orders
        expired = ctx.pokedex.expire_orders(ctx.heartbeat_count)
        if expired:
            operations.append(f"marketplace:expired={expired}")

        # Step 2: Auto-list surplus capability_tokens
        for agent_name in ctx.active_agents:
            inv = all_inventories.get(agent_name, [])
            for asset in inv:
                if asset["asset_type"] == "capability_token" and asset["quantity"] > 1:
                    surplus = asset["quantity"] - 1
                    ctx.pokedex.create_order(
                        agent_name, "capability_token", asset["asset_id"],
                        quantity=surplus, price=WORKER_VISA_STIPEND, heartbeat=ctx.heartbeat_count,
                    )
                    operations.append(f"marketplace:listed={asset['asset_id']}x{surplus}:{agent_name}")

        # Step 3: Need-driven auto-match (anti-Pac-Man)
        open_orders = ctx.pokedex.get_active_orders(asset_type="capability_token")
        if not open_orders:
            return

        mission_needs: set[str] = set()
        if ctx.sankalpa is not None:
            try:
                from city.mission_router import get_requirement
                active_missions = ctx.sankalpa.registry.get_active_missions()
                for mission in active_missions:
                    req = get_requirement(mission.id)
                    for cap in req["required"]:
                        mission_needs.add(cap)
            except Exception:
                pass

        from city.guardian_spec import ELEMENT_CAPABILITIES

        for agent_name in ctx.active_agents:
            spec = all_specs.get(agent_name)
            if spec is None:
                continue

            agent_caps = set(spec.get("capabilities", []))
            inv = all_inventories.get(agent_name, [])
            for asset in inv:
                if asset.get("asset_type") == "capability_token":
                    agent_caps.add(asset["asset_id"])

            needed_caps: set[str] = set()
            for cap in mission_needs:
                if cap not in agent_caps:
                    needed_caps.add(cap)

            element = spec.get("element", "")
            domain_caps = set(ELEMENT_CAPABILITIES.get(element, []))
            for cap in domain_caps:
                if cap not in agent_caps:
                    needed_caps.add(cap)

            if not needed_caps:
                continue

            for order in open_orders:
                if order["status"] != "open":
                    continue
                if order["seller"] == agent_name:
                    continue
                if order["asset_id"] not in needed_caps:
                    continue

                buyer_balance = ctx.pokedex._bank.get_balance(agent_name)
                if buyer_balance < order["price"]:
                    continue

                commission_pct = None
                if ctx.council is not None:
                    commission_pct = ctx.council.effective_commission
                receipt = ctx.pokedex.fill_order(
                    order["id"], agent_name, ctx.heartbeat_count, commission_pct=commission_pct,
                )
                if receipt:
                    operations.append(
                        f"marketplace:trade={order['asset_id']}:"
                        f"{order['seller']}→{agent_name}:"
                        f"price={receipt['price']}"
                    )
                    logger.info(
                        "KARMA: Trade filled — %s bought %s from %s for %d prana",
                        agent_name, order["asset_id"], order["seller"], receipt["price"],
                    )
                    break  # one trade per agent per cycle


# ── Backward-compatible shim for tests ────────────────────────────────
def _process_marketplace(
    ctx: PhaseContext,
    operations: list[str],
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]] | None = None,
) -> None:
    """Shim: old call signature → MarketplaceHandler."""
    ctx._all_specs = all_specs  # type: ignore[attr-defined]
    ctx._all_inventories = all_inventories or {}  # type: ignore[attr-defined]
    handler = MarketplaceHandler()
    if handler.should_run(ctx):
        handler.execute(ctx, operations)
    elif ctx.council is not None and ctx.council.is_market_frozen:
        operations.append("marketplace:frozen_by_council")
