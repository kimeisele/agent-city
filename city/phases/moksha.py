"""
MOKSHA Phase — Thin Dispatcher + Hook Registration.

All domain logic lives in city.hooks.moksha.* plugins.
This file builds the hook registry and dispatches hooks in priority order.

Phase 6A: God Object → Plugin Architecture.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.MOKSHA")


def _build_registry():
    """Build PhaseHookRegistry with all MOKSHA hooks."""
    from city.phase_hook import PhaseHookRegistry
    from city.hooks.moksha.reflection_stats import (
        AuditHook,
        BrainReflectionHook,
        ReflectionAnalysisHook,
        ReflectionStatsHook,
    )
    from city.hooks.moksha.mission_lifecycle import (
        MissionResultsHook,
        PRLifecycleHook,
    )
    from city.hooks.moksha.city_services import (
        CityServicesHook,
        DormantRevivalHook,
        GovernanceStatsHook,
        ThreadDecayHook,
    )
    from city.hooks.moksha.outbound import (
        DiscussionsOutboundHook,
        FederationReportHook,
        MoltbookOutboundHook,
        WikiSyncHook,
    )

    registry = PhaseHookRegistry()
    registry.register(ReflectionStatsHook())      # pri=5   stats foundation
    registry.register(AuditHook())                 # pri=20  audit
    registry.register(ReflectionAnalysisHook())    # pri=25  pattern analysis
    registry.register(PRLifecycleHook())           # pri=30  PR results
    registry.register(MissionResultsHook())        # pri=35  missions + rewards
    registry.register(CityServicesHook())          # pri=40  spawner/builder
    registry.register(GovernanceStatsHook())        # pri=42  governance
    registry.register(BrainReflectionHook())       # pri=45  brain
    registry.register(ThreadDecayHook())           # pri=50  thread lifecycle
    registry.register(DormantRevivalHook())        # pri=55  revival
    registry.register(FederationReportHook())      # pri=60  federation
    registry.register(MoltbookOutboundHook())      # pri=65  moltbook
    registry.register(DiscussionsOutboundHook())   # pri=70  discussions
    registry.register(WikiSyncHook())              # pri=75  wiki

    return registry


def execute(ctx: PhaseContext) -> dict:
    """MOKSHA: Dispatch hooks in priority order, return reflection dict."""
    operations: list[str] = []

    from city.phase_hook import MOKSHA
    registry = _build_registry()
    registry.dispatch(MOKSHA, ctx, operations)

    # Reflection dict is built by ReflectionStatsHook and enriched by later hooks
    reflection = getattr(ctx, "_reflection", {})

    if operations:
        logger.info(
            "MOKSHA: %d operations via %d hooks",
            len(operations), registry.hook_count(MOKSHA),
        )
    return reflection
