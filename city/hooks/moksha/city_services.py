"""
MOKSHA Hook: City Services — spawner, cartridge, city builder, governance,
thread decay, dormant revival, marketplace.

Extracted from moksha.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.membrane import internal_membrane_snapshot
from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.SERVICES")


class CityServicesHook(BasePhaseHook):
    """Spawner, CartridgeFactory, CityBuilder stats + census."""

    @property
    def name(self) -> str:
        return "city_services"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 40

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # Spawner stats
        from city.registry import SVC_SPAWNER

        spawner = ctx.registry.get(SVC_SPAWNER)
        if spawner is not None:
            reflection["spawner_stats"] = spawner.stats()

        # CartridgeFactory stats
        from city.registry import SVC_CARTRIDGE_FACTORY

        cart_factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
        if cart_factory is not None:
            reflection["cartridge_factory_stats"] = cart_factory.stats()

        # CityBuilder: update cell snapshots + census
        from city.registry import SVC_CITY_BUILDER

        city_builder = ctx.registry.get(SVC_CITY_BUILDER)
        if city_builder is not None:
            for agent in ctx.pokedex.list_citizens():
                city_builder.update_cell(agent["name"])
            reflection["city_census"] = city_builder.census()


class GovernanceStatsHook(BasePhaseHook):
    """Council governance stats + marketplace stats."""

    @property
    def name(self) -> str:
        return "governance_stats"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 42

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # Marketplace stats (Phase 7)
        mkt_stats = ctx.pokedex.marketplace_stats()
        if mkt_stats.get("active_orders", 0) > 0 or mkt_stats.get("total_filled", 0) > 0:
            reflection["marketplace"] = mkt_stats

        # Governance stats (Phase 8)
        if ctx.council is not None:
            gov_stats = {
                "council_members": ctx.council.member_count,
                "elected_mayor": ctx.council.elected_mayor,
                "open_proposals": len(ctx.council.get_open_proposals()),
                "market_frozen": ctx.council.is_market_frozen,
                "effective_commission": ctx.council.effective_commission,
            }
            reflection["governance"] = gov_stats


class ThreadDecayHook(BasePhaseHook):
    """Decay thread energy + detect repetition alerts."""

    @property
    def name(self) -> str:
        return "thread_decay"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 50

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.thread_state is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        thread_decay = ctx.thread_state.decay_all()
        if thread_decay.get("cooled") or thread_decay.get("archived"):
            reflection["thread_decay"] = thread_decay
        # Repetition alerts → pain signal
        alerts = ctx.thread_state.repetition_alerts()
        if alerts:
            reflection["thread_repetition_alerts"] = [
                {"number": a.discussion_number, "title": a.title}
                for a in alerts
            ]

        # 6C-6: TTL cleanup every 10th heartbeat
        if ctx.heartbeat_count % 10 == 0:
            purge_stats = ctx.thread_state.purge_stale()
            # Also prune DiscussionsBridge in-memory rate-limit entries
            if ctx.discussions is not None and hasattr(ctx.discussions, "prune_stale"):
                bridge_pruned = ctx.discussions.prune_stale()
                purge_stats["bridge_pruned"] = bridge_pruned
            if any(v for v in purge_stats.values()):
                operations.append(
                    f"ttl_cleanup:threads={purge_stats['threads_purged']}"
                    f":comments={purge_stats['comments_purged']}"
                )
                reflection["ttl_cleanup"] = purge_stats


class DormantRevivalHook(BasePhaseHook):
    """Evaluate dormant agents for treasury-funded revival."""

    @property
    def name(self) -> str:
        return "dormant_revival"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 55

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        result = _evaluate_dormant_revival(ctx)
        if result:
            reflection["revival"] = result


def _evaluate_dormant_revival(ctx: PhaseContext) -> dict | None:
    """Evaluate dormant agents for treasury-funded revival.

    Runs during MOKSHA (reflection phase).  Selects frozen agents who lived
    long enough to have proven value (cell_cycle > threshold) and revives
    them with a REVIVE_DOSE funded from the zone treasury.

    Rate-limited: at most 1 revive per MOKSHA cycle to prevent treasury drain.
    """
    from city.seed_constants import REVIVE_COOLDOWN_CYCLES, REVIVE_DOSE

    dormant = ctx.pokedex.list_dormant()
    if not dormant:
        return None

    # Eligibility: agent must have lived at least REVIVE_COOLDOWN_CYCLES
    # heartbeats before going dormant (proof of prior value)
    eligible = [
        d
        for d in dormant
        if d["cell_cycle"] >= REVIVE_COOLDOWN_CYCLES and d["prana_class"] != "immortal"
    ]

    if not eligible:
        return {"dormant_count": len(dormant), "eligible": 0, "revived": []}

    # Sort by cell_cycle descending — most experienced agents first
    eligible.sort(key=lambda d: d["cell_cycle"], reverse=True)

    # Revive at most 1 per MOKSHA cycle (treasury protection)
    revived: list[str] = []
    candidate = eligible[0]

    # Determine which zone treasury funds the revival
    agent_data = ctx.pokedex.get(candidate["name"])
    zone = "discovery"  # fallback
    if agent_data and agent_data.get("zone"):
        zone = agent_data["zone"]

    from city.pokedex import ZONE_TREASURIES

    treasury_account = ZONE_TREASURIES.get(zone, "ZONE_DISCOVERY")

    try:
        ctx.pokedex.revive(
            candidate["name"],
            prana_dose=REVIVE_DOSE,
            sponsor=treasury_account,
            reason=f"revive:moksha_auto:cycle_{ctx.heartbeat_count}",
            membrane=internal_membrane_snapshot(source_class="moksha"),
        )
        revived.append(candidate["name"])
        logger.info(
            "MOKSHA: Revived %s (cycle=%d, zone=%s, dose=%d)",
            candidate["name"],
            candidate["cell_cycle"],
            zone,
            REVIVE_DOSE,
        )
    except Exception as e:
        logger.warning("MOKSHA: Failed to revive %s: %s", candidate["name"], e)

    return {
        "dormant_count": len(dormant),
        "eligible": len(eligible),
        "revived": revived,
    }
