"""
KARMA Phase — Thin Dispatcher.

All domain logic lives in city.karma_handlers.* plugins.
This file is the dispatcher: it builds the handler registry,
calls handlers in priority order, and returns operations.

Phase 6A: God Object → Plugin Architecture.
Former monolith (1491 LOC) → 9 isolated handlers + this 80-line dispatcher.

Future (Phase 6C): VenuOrchestrator.step() emits DIWEvent to subscribers.
Each handler implements DIWSubscriberProtocol and wakes based on 19-bit state.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.KARMA")


def _build_registry():
    """Build handler registry with all domain handlers.

    Dynamic registration: handlers register themselves. Future agents
    can add new handlers via PR without touching this file.
    """
    from city.karma_handlers import KarmaHandlerRegistry
    from city.karma_handlers.brain_health import BrainHealthHandler
    from city.karma_handlers.gateway import GatewayHandler
    from city.karma_handlers.sankalpa import SankalpaHandler
    from city.karma_handlers.cognition import CognitionHandler
    from city.karma_handlers.signals import SignalHandler
    from city.karma_handlers.marketplace import MarketplaceHandler
    from city.karma_handlers.heal import HealHandler
    from city.karma_handlers.council import CouncilHandler
    from city.karma_handlers.assistant import AssistantHandler

    registry = KarmaHandlerRegistry()
    registry.register(BrainHealthHandler())
    registry.register(GatewayHandler())
    registry.register(SankalpaHandler())
    registry.register(CognitionHandler())
    registry.register(SignalHandler())
    registry.register(MarketplaceHandler())
    registry.register(HealHandler())
    registry.register(CouncilHandler())
    registry.register(AssistantHandler())
    return registry


def execute(ctx: PhaseContext) -> list[str]:
    """KARMA: Dispatch to registered handlers in priority order."""
    operations: list[str] = []

    registry = _build_registry()
    registry.dispatch(ctx, operations)

    if operations:
        logger.info("KARMA: %d operations via %d handlers", len(operations), registry.handler_count)
    return operations
