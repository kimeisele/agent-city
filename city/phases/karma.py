"""
KARMA Phase — Thin Dispatcher + Venu Wiring.

All domain logic lives in city.karma_handlers.* plugins.
This file is the dispatcher: it builds the handler registry,
steps the VenuOrchestrator (19-bit DIW), then dispatches
handlers in priority order.

Phase 6A: God Object → Plugin Architecture.
Phase 6C: VenuOrchestrator.step() emits DIWEvent to subscribers.

8E: Two handlers are now DIW-aware, gated on VENU energy bits (0-63):
  - HealHandler:      venu >= 32 (high energy — healing is expensive)
  - CognitionHandler: venu >= 16 (moderate energy — cognition is cheaper)
In low-energy ticks, these handlers skip, conserving city resources.
The remaining handlers (Gateway, Signals, etc.) run unconditionally.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.KARMA")


def _build_dispatcher():
    """Build VenuDispatcher with all domain handlers + orchestrator.

    Dynamic registration: handlers register themselves. Future agents
    can add new handlers via PR without touching this file.

    If VenuOrchestrator is available, the dispatcher steps the flute
    once per KARMA and emits DIWEvent to all DIW-aware handlers.
    Falls back to plain dispatch if unavailable.
    """
    from city.karma_handlers import KarmaHandlerRegistry
    from city.karma_handlers.brain_health import BrainHealthHandler
    from city.karma_handlers.gateway import GatewayHandler
    from city.karma_handlers.sankalpa import SankalpaHandler
    from city.karma_handlers.initiative import InitiativeHandler
    from city.karma_handlers.cognition import CognitionHandler
    from city.karma_handlers.signals import SignalHandler
    from city.karma_handlers.marketplace import MarketplaceHandler
    from city.karma_handlers.heal import HealHandler
    from city.karma_handlers.council import CouncilHandler
    from city.karma_handlers.assistant import AssistantHandler
    from city.karma_handlers.triage import TriageHandler
    from city.karma_handlers.bounty_claim import BountyClaimHandler
    from city.karma_handlers.unstructured import UnstructuredSignalHandler
    from city.karma_handlers.diw_bridge import VenuDispatcher

    registry = KarmaHandlerRegistry()
    registry.register(BrainHealthHandler())
    registry.register(GatewayHandler())
    registry.register(TriageHandler())
    registry.register(SankalpaHandler())
    registry.register(InitiativeHandler())
    registry.register(CognitionHandler())
    registry.register(SignalHandler())
    registry.register(MarketplaceHandler())
    registry.register(HealHandler())
    registry.register(CouncilHandler())
    registry.register(AssistantHandler())
    registry.register(BountyClaimHandler())  # pri=15 (intercepts structured)
    registry.register(UnstructuredSignalHandler())  # pri=18 (intercepts natural language)

    # Use the mahamantra singleton VenuOrchestrator.
    # Persisted via to_bytes/from_bytes in heartbeat.py (8E), so ticks
    # accumulate across the city's lifetime. This gives DIW-gated handlers
    # meaningful energy values that cycle through the 21600-tick COSMIC_FRAME.
    orchestrator = None
    try:
        from vibe_core.mahamantra import mahamantra

        orchestrator = mahamantra.venu
        logger.debug("KARMA: VenuOrchestrator wired (tick=%d)", orchestrator.tick)
    except Exception as e:
        logger.debug("KARMA: VenuOrchestrator unavailable: %s", e)

    return VenuDispatcher(registry, orchestrator)


def execute(ctx: PhaseContext) -> list[str]:
    """KARMA: Step the flute, then dispatch handlers in priority order."""
    operations: list[str] = []

    dispatcher = _build_dispatcher()
    dispatcher.dispatch(ctx, operations)

    if operations:
        logger.info(
            "KARMA: %d operations via %d handlers",
            len(operations), dispatcher.handler_count,
        )
    return operations
