"""
DHARMA Phase — Thin Dispatcher + Hook Registration.

All domain logic lives in city.hooks.dharma.* plugins.
This file builds the hook registry and dispatches hooks in priority order.

Phase 6A: God Object → Plugin Architecture.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.DHARMA")


def _build_registry():
    """Build PhaseHookRegistry with all DHARMA hooks."""
    from city.phase_hook import PhaseHookRegistry
    from city.hooks.dharma.metabolism import (
        HibernationHook,
        MetabolizeHook,
        PromotionHook,
        ZoneHealthHook,
    )
    from city.hooks.dharma.governance import (
        CognitionConstraintsHook,
        ElectionHook,
        ProposalExpiryHook,
    )
    from city.hooks.dharma.contracts_issues import (
        CommunityTriageHook,
        ContractsHook,
        IssueLifecycleHook,
        MoltbookAssistantDharmaHook,
    )

    registry = PhaseHookRegistry()
    registry.register(HibernationHook())              # pri=0   freeze first
    registry.register(MetabolizeHook())                # pri=5   metabolize
    registry.register(PromotionHook())                 # pri=10  promote
    registry.register(ZoneHealthHook())                # pri=15  zone health
    registry.register(ElectionHook())                  # pri=20  elections
    registry.register(CognitionConstraintsHook())      # pri=25  constraints
    registry.register(ProposalExpiryHook())            # pri=30  expire
    registry.register(ContractsHook())                 # pri=40  contracts
    registry.register(IssueLifecycleHook())            # pri=45  issues
    registry.register(MoltbookAssistantDharmaHook())   # pri=50  assistant
    registry.register(CommunityTriageHook())           # pri=60  triage

    return registry


def execute(ctx: PhaseContext) -> list[str]:
    """DHARMA: Dispatch hooks in priority order."""
    actions: list[str] = []

    from city.phase_hook import DHARMA
    registry = _build_registry()
    registry.dispatch(DHARMA, ctx, actions)

    if actions:
        logger.info(
            "DHARMA: %d governance actions via %d hooks",
            len(actions), registry.hook_count(DHARMA),
        )
    return actions
