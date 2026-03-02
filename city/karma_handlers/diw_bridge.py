"""
DIW Bridge — KarmaHandler ↔ DIWSubscriberProtocol.

Bridges the KarmaHandler plugin architecture (Phase 6A) with the
VenuOrchestrator's 19-bit Divine Instruction Word (Phase 6C).

Each KarmaHandler that extends DIWAwareHandler:
1. Receives DIWEvent on every VenuOrchestrator.step()
2. Can inspect venu/vamsi/murali bits in should_run()
3. Participates in the Mahamantra cycle without code changes

The VenuDispatcher wraps the KarmaHandlerRegistry and steps the
orchestrator once per KARMA phase, emitting the DIWEvent to all
DIW-aware handlers before dispatch.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vibe_core.mahamantra.substrate.vm.venu_orchestrator import (
    DIWEvent,
    VenuOrchestrator,
)

if TYPE_CHECKING:
    from city.karma_handlers import KarmaHandlerRegistry
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.DIW_BRIDGE")


# ── DIW-Aware Handler Mixin ─────────────────────────────────────────────


class DIWAwareHandler:
    """Mixin that makes a KarmaHandler a DIWSubscriber.

    Stores the latest DIWEvent so handlers can read the 19-bit state
    in their should_run() and execute() methods.

    Usage:
        class MyHandler(DIWAwareHandler, BaseKarmaHandler):
            def should_run(self, ctx):
                # Only run when venu mood >= 32 (high energy)
                if self.current_diw and self.current_diw["venu"] < 32:
                    return False
                return True
    """

    def __init__(self) -> None:
        self._current_diw: DIWEvent | None = None

    @property
    def current_diw(self) -> DIWEvent | None:
        """The most recent DIWEvent from the VenuOrchestrator."""
        return self._current_diw

    @property
    def subscriber_name(self) -> str:
        """Name for DIWSubscriberProtocol."""
        return getattr(self, "name", type(self).__name__)

    def on_diw(self, event: DIWEvent) -> None:
        """Receive the DIWEvent from VenuOrchestrator.step().

        Stores the event for inspection by should_run()/execute().
        """
        self._current_diw = event


# ── Venu Dispatcher ─────────────────────────────────────────────────────


class VenuDispatcher:
    """Steps VenuOrchestrator once per KARMA, then dispatches handlers.

    Flow:
    1. orchestrator.step() → emits DIWEvent to all DIW-aware handlers
    2. registry.dispatch(ctx, operations) → normal priority-ordered dispatch
    3. Handlers that extend DIWAwareHandler can read self.current_diw

    If no VenuOrchestrator is available, falls back to plain dispatch
    (backward compatible with pre-6C behavior).
    """

    def __init__(
        self,
        registry: KarmaHandlerRegistry,
        orchestrator: VenuOrchestrator | None = None,
    ) -> None:
        self._registry = registry
        self._orchestrator = orchestrator
        self._wired = False

    def _wire_subscribers(self) -> None:
        """Register all DIW-aware handlers with the orchestrator."""
        if self._wired or self._orchestrator is None:
            return
        for handler in self._registry._handlers:
            if isinstance(handler, DIWAwareHandler):
                try:
                    self._orchestrator.subscribe(handler)
                    logger.debug(
                        "DIW: subscribed %s to VenuOrchestrator",
                        handler.subscriber_name,
                    )
                except TypeError:
                    logger.debug(
                        "DIW: %s not a valid DIWSubscriber, skipping",
                        getattr(handler, "name", "?"),
                    )
        self._wired = True

    def dispatch(self, ctx: PhaseContext, operations: list[str]) -> None:
        """Step the flute, then dispatch handlers."""
        if self._orchestrator is not None:
            self._wire_subscribers()
            diw = self._orchestrator.step()
            operations.append(f"venu_tick:diw={diw:#07x}")
            logger.debug("DIW: step → %s", hex(diw))

        self._registry.dispatch(ctx, operations)

    @property
    def handler_count(self) -> int:
        """Number of registered handlers."""
        return self._registry.handler_count
