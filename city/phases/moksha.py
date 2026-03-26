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
        GovernanceEvalHook,
        EventDrivenOutboundHook,
        WikiSyncHook,
    )
    from city.hooks.moksha.system_health import SystemHealthHook
    from city.hooks.moksha.federation_relay_push import FederationRelayPushHook
    from city.hooks.moksha.city_diary import CityDiaryHook
    from city.hooks.moksha.moltbook_outbound import MoltbookOutboundHook
    from city.hooks.moksha.moltbook_sender import MoltbookSenderHook

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
    registry.register(GovernanceEvalHook())        # pri=58  governance (once, shared)
    registry.register(FederationReportHook())      # pri=60  federation
    registry.register(EventDrivenOutboundHook())   # pri=65  moltbook
    registry.register(MoltbookOutboundHook())      # pri=64  write to outbox (must run before sender)
    registry.register(MoltbookSenderHook())        # pri=66  send pending outbox messages
    registry.register(SystemHealthHook())          # pri=68  12E: proactive diagnostics
    registry.register(DiscussionsOutboundHook())   # pri=70  discussions
    registry.register(CityDiaryHook())             # pri=72  hourly diary to Announcements
    registry.register(WikiSyncHook())              # pri=75  wiki
    registry.register(FederationRelayPushHook())   # pri=80  relay push to hub

    return registry


def execute(ctx: PhaseContext) -> dict:
    """MOKSHA: Dispatch hooks in priority order, return reflection dict."""
    operations: list[str] = []

    # Import MOKSHA constant safely
    try:
        from city.phase_hook import MOKSHA
    except ImportError:
        # Fallback to a default value if the constant is not available
        # This should match the actual constant used in PhaseHookRegistry
        MOKSHA = "MOKSHA"

    # Ensure ctx has required ledgers after DI refactoring
    # Try to obtain ledgers from runtime or registry and attach them to ctx
    if hasattr(ctx, 'runtime'):
        runtime = ctx.runtime
        # Attach common ledgers if they exist on runtime
        for ledger_name in ['discovery_ledger', 'signal_state_ledger', 
                            'reflection_ledger', 'mission_ledger']:
            if hasattr(runtime, ledger_name) and not hasattr(ctx, ledger_name):
                setattr(ctx, ledger_name, getattr(runtime, ledger_name))
    elif hasattr(ctx, 'registry'):
        registry = ctx.registry
        # Similar logic for registry if ledgers are stored there
        for ledger_name in ['discovery_ledger', 'signal_state_ledger',
                            'reflection_ledger', 'mission_ledger']:
            if hasattr(registry, ledger_name) and not hasattr(ctx, ledger_name):
                setattr(ctx, ledger_name, getattr(registry, ledger_name))

    registry = _build_registry()
    try:
        registry.dispatch(MOKSHA, ctx, operations)
    except Exception as e:
        logger.error("MOKSHA dispatch failed: %s", e, exc_info=True)
        # Re-raise to maintain original error behavior
        raise

    # Reflection dict is built by ReflectionStatsHook and enriched by later hooks
    # Try multiple possible locations due to DI refactoring
    reflection = {}
    if hasattr(ctx, "_reflection"):
        reflection = ctx._reflection
    elif hasattr(ctx, "reflection"):
        reflection = ctx.reflection
    else:
        # Try to get from runtime if available
        runtime = getattr(ctx, "runtime", None)
        if runtime is not None:
            reflection = getattr(runtime, "_reflection", getattr(runtime, "reflection", {}))
        else:
            # Last resort: check if ctx itself is a dict-like object
            try:
                if isinstance(ctx, dict):
                    reflection = ctx.get("_reflection", ctx.get("reflection", {}))
            except:
                pass

    # Guard: if ReflectionStatsHook failed, reflection is empty — downstream hooks
    # silently wrote to a throwaway dict. Flag so operator knows data is incomplete.
    if reflection and "city_stats" not in reflection:
        logger.critical(
            "MOKSHA: reflection missing city_stats — ReflectionStatsHook may have failed"
        )
        reflection["_incomplete"] = True

    if operations:
        logger.info(
            "MOKSHA: %d operations via %d hooks",
            len(operations), registry.hook_count(MOKSHA),
        )
    return reflection
