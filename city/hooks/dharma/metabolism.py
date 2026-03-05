"""
DHARMA Hook: Metabolism — hibernation, metabolize, immune scan, promotion, zones.

Extracted from dharma.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook
from city.seed_constants import HIBERNATION_THRESHOLD

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.METABOLISM")


class HibernationHook(BasePhaseHook):
    """Freeze low-prana agents BEFORE metabolize freezes them."""

    @property
    def name(self) -> str:
        return "hibernation"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 0  # first: before metabolize

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        hibernated = _hibernate_low_prana(ctx, HIBERNATION_THRESHOLD)
        for name in hibernated:
            operations.append(f"hibernated:{name}:low_prana")


class MetabolizeHook(BasePhaseHook):
    """Metabolize all living agents + feed reactor metrics."""

    @property
    def name(self) -> str:
        return "metabolize"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 5

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        # Populate active_agents BEFORE metabolize — feeds +10 prana bonus.
        from city.registry import SVC_SPAWNER

        spawner = ctx.registry.get(SVC_SPAWNER)
        if spawner is not None:
            spawner.mark_citizens_active(ctx.active_agents)

        # Metabolize all living agents
        _t0 = time.monotonic()
        dead = ctx.pokedex.metabolize_all(active_agents=ctx.active_agents)
        _metabolize_ms = (time.monotonic() - _t0) * 1000
        for name in dead:
            operations.append(f"dormant:{name}:prana_exhaustion")
            logger.info("DHARMA: Agent %s dormant (prana exhaustion)", name)

        # Feed CityReactor with metabolize timing + death count
        from city.registry import SVC_REACTOR

        reactor = ctx.registry.get(SVC_REACTOR)
        if reactor is not None:
            reactor.record("metabolize_all", duration_ms=_metabolize_ms, success=True)
            if dead:
                reactor.record("agent_deaths", count=len(dead))

        # Immune scan: diagnose why agents died
        if ctx.immune is not None and dead:
            for name in dead:
                diagnosis = ctx.immune.diagnose(f"agent_death:{name}:prana_exhaustion")
                if diagnosis.healable:
                    result = ctx.immune.heal(diagnosis)
                    if result.success:
                        operations.append(f"immune_healed:{name}:{diagnosis.rule_id}")

        # Clear active set for next cycle
        ctx.active_agents.clear()

        # Store dead list + reactor on ctx for later hooks
        ctx._dharma_dead = dead  # type: ignore[attr-defined]
        ctx._dharma_reactor = reactor  # type: ignore[attr-defined]


class PromotionHook(BasePhaseHook):
    """Auto-promote discovered agents → citizen → network-registered."""

    @property
    def name(self) -> str:
        return "promotion"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 10

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.registry import SVC_SPAWNER

        spawner = ctx.registry.get(SVC_SPAWNER)
        if spawner is not None:
            promoted = spawner.promote_eligible(ctx.heartbeat_count)
            for name in promoted:
                operations.append(f"promoted:{name}:citizen")


class ZoneHealthHook(BasePhaseHook):
    """Zone health check + feed reactor + detect pain."""

    @property
    def name(self) -> str:
        return "zone_health"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 15

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        stats = ctx.pokedex.stats()
        zones = stats.get("zones", {})
        for zone, count in zones.items():
            if count == 0:
                operations.append(f"warning:zone_{zone}_empty")
                logger.warning("DHARMA: Zone %s has 0 agents", zone)

        # Feed zone population into reactor + process pain
        reactor = getattr(ctx, "_dharma_reactor", None)
        if reactor is not None:
            if zones:
                reactor.record("zone_population", zones=zones)
            # Detect pain → route via CityAttention → execute via CityIntentExecutor
            from city.registry import SVC_ATTENTION, SVC_INTENT_EXECUTOR

            attention = ctx.registry.get(SVC_ATTENTION)
            executor = ctx.registry.get(SVC_INTENT_EXECUTOR)
            pain_intents = reactor.detect_pain()
            for intent in pain_intents:
                handler = attention.route(intent.signal) if attention else None
                if executor is not None:
                    result = executor.execute(ctx, intent, handler)
                    operations.append(f"pain:{intent.signal}:{intent.priority}:{result}")
                else:
                    operations.append(f"pain:{intent.signal}:{intent.priority}")
                logger.warning(
                    "DHARMA PAIN: %s (priority=%s, handler=%s, ctx=%s)",
                    intent.signal,
                    intent.priority,
                    handler,
                    intent.context,
                )


# ── Helpers ──────────────────────────────────────────────────────────


def _hibernate_low_prana(ctx: PhaseContext, threshold: int) -> list[str]:
    """Freeze agents whose prana dropped below threshold.

    Uses existing freeze() infrastructure (pokedex + CivicBank).
    Agents can be revived later via unfreeze() when energy is injected.
    """
    hibernated: list[str] = []
    for agent in ctx.pokedex.list_citizens():
        name = agent["name"]
        cell = ctx.pokedex.get_cell(name)
        if cell is None or not cell.is_alive:
            continue
        if cell.prana < threshold:
            try:
                ctx.pokedex.freeze(name, "auto_hibernation:low_prana")
                hibernated.append(name)
                logger.info(
                    "DHARMA: Agent %s hibernated (prana=%d < %d)",
                    name,
                    cell.prana,
                    threshold,
                )
            except Exception as e:
                logger.warning("DHARMA: Failed to hibernate %s: %s", name, e)
    return hibernated
