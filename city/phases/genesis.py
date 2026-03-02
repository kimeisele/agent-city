"""
GENESIS Phase — Thin Dispatcher + Hook Registration.

All domain logic lives in city.hooks.genesis.* plugins.
This file builds the hook registry and dispatches hooks in priority order.

Phase 6A: God Object → Plugin Architecture.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.GENESIS")


def _build_registry():
    """Build PhaseHookRegistry with all GENESIS hooks.

    Dynamic registration: hooks register themselves. Future agents
    can add new hooks via PR without touching this file.
    """
    from city.phase_hook import GENESIS, PhaseHookRegistry
    from city.hooks.genesis.census import CensusHook
    from city.hooks.genesis.moltbook_scan import (
        DMInboxHook,
        MoltbookAssistantHook,
        MoltbookFeedScanHook,
        SubmoltScanHook,
    )
    from city.hooks.genesis.federation import (
        FederationDirectivesHook,
        FederationNadiHook,
    )
    from city.hooks.genesis.discussion_scanner import (
        AgentIntroHook,
        DiscussionScannerHook,
    )

    registry = PhaseHookRegistry()
    registry.register(CensusHook())              # pri=0   setup
    registry.register(MoltbookFeedScanHook())     # pri=10  discovery
    registry.register(DMInboxHook())              # pri=15  inbox
    registry.register(SubmoltScanHook())           # pri=20  submolt
    registry.register(FederationNadiHook())        # pri=30  federation
    registry.register(FederationDirectivesHook())  # pri=35  directives
    registry.register(DiscussionScannerHook())     # pri=60  discussions
    registry.register(AgentIntroHook())            # pri=70  intros
    registry.register(MoltbookAssistantHook())     # pri=80  assistant

    return registry


def execute(ctx: PhaseContext) -> list[str]:
    """GENESIS: Dispatch hooks in priority order."""
    operations: list[str] = []

    from city.phase_hook import GENESIS
    registry = _build_registry()
    registry.dispatch(GENESIS, ctx, operations)

    if operations:
        logger.info(
            "GENESIS: %d operations via %d hooks",
            len(operations), registry.hook_count(GENESIS),
        )
    return operations
