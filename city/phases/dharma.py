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
        CampaignEvaluationHook,
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
    from city.hooks.dharma.immigration_ingress import ImmigrationIngressHook
    from city.hooks.dharma.immigration_processor import ImmigrationProcessorHook
    from city.hooks.dharma.zone_governance import ZoneGovernanceHook
    from city.hooks.dharma.pr_verdict import PRVerdictHook
    from city.hooks.dharma.bottleneck_resolution import BottleneckResolutionHook
    from city.hooks.dharma.campaign_recruitment import CampaignRecruitmentHook

    registry = PhaseHookRegistry()
    registry.register(HibernationHook())              # pri=0   freeze first
    registry.register(MetabolizeHook())                # pri=5   metabolize
    registry.register(PromotionHook())                 # pri=10  promote
    registry.register(ImmigrationIngressHook())        # pri=11  DM→application bridge
    registry.register(ImmigrationProcessorHook())      # pri=12  immigration
    registry.register(ZoneHealthHook())                # pri=15  zone health
    registry.register(ZoneGovernanceHook())            # pri=16  zone governance
    registry.register(ElectionHook())                  # pri=20  elections
    registry.register(CognitionConstraintsHook())      # pri=25  constraints
    registry.register(ProposalExpiryHook())            # pri=30  expire
    registry.register(CampaignEvaluationHook())        # pri=35  long-horizon strategy
    registry.register(CampaignRecruitmentHook())       # pri=36  recruitment bounties
    registry.register(ContractsHook())                 # pri=40  contracts
    registry.register(IssueLifecycleHook())            # pri=45  issues
    registry.register(MoltbookAssistantDharmaHook())   # pri=50  assistant
    registry.register(PRVerdictHook())                 # pri=55  steward PR verdicts
    registry.register(BottleneckResolutionHook())      # pri=56  steward bottleneck resolution
    registry.register(CommunityTriageHook())           # pri=60  triage

    return registry


def execute(ctx: PhaseContext) -> list[str]:
    """DHARMA: Dispatch hooks in priority order."""
    actions: list[str] = []

    # 12D: Drain city_nadi into gateway_queue so DHARMA hooks can see system messages
    if ctx.city_nadi is not None:
        new_items = ctx.city_nadi.drain()
        if new_items:
            ctx.gateway_queue.extend(new_items)
            logger.debug("DHARMA: drained %d items from city_nadi into gateway_queue", len(new_items))

    from city.phase_hook import DHARMA
    registry = _build_registry()
    registry.dispatch(DHARMA, ctx, actions)

    # 12D: Consume federation messages handled in DHARMA so they don't leak to KARMA intents
    if ctx.gateway_queue:
        original_count = len(ctx.gateway_queue)
        ctx.gateway_queue[:] = [
            item for item in ctx.gateway_queue
            if item.get("membrane", {}).get("surface") != "federation"
        ]
        consumed = original_count - len(ctx.gateway_queue)
        if consumed:
            logger.debug("DHARMA: consumed %d federation messages", consumed)

    if actions:
        logger.info(
            "DHARMA: %d governance actions via %d hooks",
            len(actions), registry.hook_count(DHARMA),
        )
    return actions
