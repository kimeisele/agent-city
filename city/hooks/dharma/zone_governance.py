"""
DHARMA Hook: Zone Governance — Zone vitality, treasury, and recruitment.

Runs after ZoneHealth (pri=15), before Elections (pri=20).
Extends basic zone-empty detection with:
  1. Zone vitality scoring (total prana per zone)
  2. Zone treasury balance monitoring
  3. Recruitment missions for underpopulated zones

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.ZONE_GOVERNANCE")

# Minimum population before a zone is considered "critical"
ZONE_CRITICAL_THRESHOLD = 2
# Treasury balance below which a zone is "underfunded"
ZONE_TREASURY_LOW_THRESHOLD = 10


class ZoneGovernanceHook(BasePhaseHook):
    """Zone vitality, treasury monitoring, and recruitment missions."""

    @property
    def name(self) -> str:
        return "zone_governance"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 16  # after zone_health (15), before elections (20)

    def should_run(self, ctx: PhaseContext) -> bool:
        return True  # Always run — zones always exist

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.pokedex import ZONE_TREASURIES

        stats = ctx.pokedex.stats()
        zones = stats.get("zones", {})
        total_population = sum(zones.values())

        if total_population == 0:
            return  # No agents yet — nothing to govern

        # 1. Zone vitality: total prana per zone
        vitality: dict[str, int] = {}
        for zone in ZONE_TREASURIES:
            agents = ctx.pokedex.list_by_zone(zone)
            zone_prana = 0
            for agent in agents:
                try:
                    prana = ctx.pokedex.get_prana(agent["name"])
                    zone_prana += prana
                except Exception:
                    pass
            vitality[zone] = zone_prana

        # 2. Zone treasury balances
        treasury_balances: dict[str, int] = {}
        for zone, account in ZONE_TREASURIES.items():
            try:
                balance = ctx.pokedex._bank.get_balance(account)
                treasury_balances[zone] = balance
            except Exception:
                treasury_balances[zone] = 0

        # 3. Detect critical zones + create recruitment missions
        avg_population = total_population / len(ZONE_TREASURIES) if ZONE_TREASURIES else 0

        for zone in ZONE_TREASURIES:
            pop = zones.get(zone, 0)
            treasury = treasury_balances.get(zone, 0)

            # Critical population
            if pop < ZONE_CRITICAL_THRESHOLD:
                operations.append(f"zone_critical:{zone}:pop={pop}")
                logger.warning(
                    "ZONE GOVERNANCE: %s is critical (pop=%d, threshold=%d)",
                    zone, pop, ZONE_CRITICAL_THRESHOLD,
                )
                # Create recruitment mission if sankalpa available
                if ctx.sankalpa is not None:
                    try:
                        from city.missions import create_zone_recruitment_mission
                        create_zone_recruitment_mission(ctx, zone)
                        operations.append(f"zone_recruit_mission:{zone}")
                    except (ImportError, Exception) as exc:
                        logger.debug("Zone recruitment mission skipped: %s", exc)

            # Underfunded treasury
            if treasury < ZONE_TREASURY_LOW_THRESHOLD:
                operations.append(f"zone_treasury_low:{zone}:balance={treasury}")
                logger.warning(
                    "ZONE GOVERNANCE: %s treasury low (balance=%d)",
                    zone, treasury,
                )

            # Imbalanced zone (>2x average population)
            if avg_population > 0 and pop > avg_population * 2:
                operations.append(
                    f"zone_imbalanced:{zone}:pop={pop}:avg={avg_population:.0f}"
                )

        # 4. Log summary
        logger.info(
            "ZONE GOVERNANCE: vitality=%s, treasuries=%s, populations=%s",
            vitality, treasury_balances, zones,
        )
