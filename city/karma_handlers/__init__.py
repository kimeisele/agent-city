"""
KARMA HANDLERS — Plugin-based Operation Dispatch.

Each handler is an isolated domain concern extracted from the monolithic karma.py.
Handlers register dynamically via KarmaHandlerRegistry. The phase dispatcher
calls them in priority order. No hardcoded imports in karma.py.

Future: Each handler implements DIWSubscriberProtocol and registers with
VenuOrchestrator. The 19-bit DIW controls which handlers wake up per tick.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA_HANDLERS")


# ── Handler Protocol ─────────────────────────────────────────────────


@runtime_checkable
class KarmaHandler(Protocol):
    """Protocol for karma phase handlers.

    Each handler owns one domain concern. Handlers are called in
    priority order by the dispatcher. Lower priority = runs first.

    name: unique identifier (used for logging + dedup)
    priority: execution order (0=first, 100=last)
    execute(ctx, ops): perform operations, append to ops list
    should_run(ctx): optional gate — return False to skip this tick
    """

    @property
    def name(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def should_run(self, ctx: PhaseContext) -> bool: ...

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None: ...


class BaseKarmaHandler(ABC):
    """Base class for karma handlers with sensible defaults."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def priority(self) -> int:
        return 50  # default middle priority

    def should_run(self, ctx: PhaseContext) -> bool:
        return True  # always run by default

    @abstractmethod
    def execute(self, ctx: PhaseContext, operations: list[str]) -> None: ...


# ── Handler Registry ─────────────────────────────────────────────────


class KarmaHandlerRegistry:
    """Dynamic registry for karma handlers.

    Handlers register at boot (or later). The dispatcher iterates
    them in priority order. This replaces 1400 lines of inline code
    in karma.py with isolated, testable, PR-safe modules.
    """

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: list[KarmaHandler] = []

    def register(self, handler: KarmaHandler) -> None:
        """Register a handler. Deduplicates by name."""
        for existing in self._handlers:
            if existing.name == handler.name:
                logger.debug("Handler %s already registered, skipping", handler.name)
                return
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.priority)
        logger.debug("Registered karma handler: %s (priority=%d)", handler.name, handler.priority)

    def unregister(self, name: str) -> bool:
        """Remove a handler by name."""
        before = len(self._handlers)
        self._handlers = [h for h in self._handlers if h.name != name]
        return len(self._handlers) < before

    def dispatch(self, ctx: PhaseContext, operations: list[str]) -> None:
        """Execute all handlers in priority order, respecting gates."""
        for handler in self._handlers:
            try:
                if not handler.should_run(ctx):
                    logger.debug("Handler %s skipped (gate)", handler.name)
                    continue
                handler.execute(ctx, operations)
            except Exception as e:
                logger.warning(
                    "Handler %s failed: %s", handler.name, e,
                )
                operations.append(f"handler_error:{handler.name}:{e}")

    @property
    def handler_names(self) -> list[str]:
        return [h.name for h in self._handlers]

    @property
    def handler_count(self) -> int:
        return len(self._handlers)

    def stats(self) -> dict:
        return {
            "handlers": self.handler_count,
            "names": self.handler_names,
        }
