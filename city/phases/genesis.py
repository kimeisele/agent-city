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
    from city.phase_hook import PhaseHookRegistry
    from city.hooks.genesis.census import CensusHook
    from city.hooks.genesis.moltbook_scan import (
        DMInboxHook,
        MoltbookAssistantHook,
        MoltbookFeedScanHook,
        MoltbookDiplomacyHook,
        SubmoltScanHook,
    )
    from city.hooks.genesis.federation import (
        FederationDirectivesHook,
        FederationHealthHook,
        FederationNadiHook,
    )
    from city.hooks.genesis.discussion_scanner import (
        AgentIntroHook,
        DiscussionScannerHook,
    )
    from city.hooks.genesis.issue_scanner import RegistrationIssueScannerHook
    from city.hooks.genesis.federation_relay_pull import FederationRelayPullHook
    from city.hooks.genesis.active_discovery import ActiveDiscoveryHook
    from city.hooks.genesis.nadi_inbox_scanner import NadiInboxScannerHook
    from city.hooks.genesis.heartbeat_observer_hook import HeartbeatObserverHook
    from city.hooks.genesis.inbound_membrane import InboundMembraneHook

    registry = PhaseHookRegistry()
    registry.register(CensusHook())              # pri=0   setup
    registry.register(HeartbeatObserverHook())   # pri=5   self-observation
    registry.register(MoltbookFeedScanHook())     # pri=10  discovery
    registry.register(DMInboxHook())              # pri=15  inbox
    registry.register(MoltbookDiplomacyHook())      # pri=18  mentions/replies
    registry.register(SubmoltScanHook())           # pri=20  submolt
    registry.register(FederationNadiHook())        # pri=30  federation
    registry.register(FederationHealthHook())      # pri=32  health reader
    registry.register(FederationDirectivesHook())  # pri=35  directives
    registry.register(FederationRelayPullHook())      # pri=28  relay pull from hub
    registry.register(NadiInboxScannerHook())         # pri=45  nadi inbox
    registry.register(RegistrationIssueScannerHook())  # pri=55  github issues
    registry.register(InboundMembraneHook())          # pri=58  inbound membrane
    registry.register(ActiveDiscoveryHook())              # pri=58  active discovery (daily)
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
