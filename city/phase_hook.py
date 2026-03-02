"""
PhaseHook — Generalized Plugin Protocol for All MURALI Phases.

Extracted from KarmaHandlerRegistry pattern (Phase 6A).
Each phase (GENESIS, KARMA, MOKSHA, DHARMA) becomes a thin dispatcher
that runs registered hooks in priority order.

Adding a feature = adding a hook file. Not editing a monolith.

Priority bands (per Gemini's Senior Advice):
  0-10:  Setup & Context Validation
  11-80: Core Logic
  81-100: Cleanup & State Commit

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASE_HOOK")


# ── Phase Constants ──────────────────────────────────────────────────

GENESIS = "genesis"
KARMA = "karma"
MOKSHA = "moksha"
DHARMA = "dharma"

ALL_PHASES = frozenset({GENESIS, KARMA, MOKSHA, DHARMA})


# ── PhaseHook Protocol ───────────────────────────────────────────────


@runtime_checkable
class PhaseHook(Protocol):
    """Protocol for phase hooks across all MURALI phases.

    name:     unique identifier (logging + dedup)
    phase:    which phase this hook belongs to
    priority: execution order (0=first, 100=last)
    should_run(ctx): gate — return False to skip this tick
    execute(ctx, ops): perform operations, append to ops list
    """

    @property
    def name(self) -> str: ...

    @property
    def phase(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def should_run(self, ctx: PhaseContext) -> bool: ...

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None: ...


class BasePhaseHook(ABC):
    """Base class for phase hooks with sensible defaults."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def phase(self) -> str: ...

    @property
    def priority(self) -> int:
        return 50

    def should_run(self, ctx: PhaseContext) -> bool:
        return True

    @abstractmethod
    def execute(self, ctx: PhaseContext, operations: list[str]) -> None: ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} phase={self.phase} pri={self.priority}>"


# ── PhaseHookRegistry ────────────────────────────────────────────────


class PhaseHookRegistry:
    """Registry for hooks across all phases.

    Hooks register at boot. The dispatcher for each phase calls
    registry.dispatch(phase, ctx, ops) which runs only the hooks
    for that phase, in priority order.

    This replaces monolithic execute() functions with composable,
    testable, independently deployable hook files.
    """

    __slots__ = ("_hooks",)

    def __init__(self) -> None:
        self._hooks: dict[str, list[PhaseHook]] = {
            p: [] for p in ALL_PHASES
        }

    def register(self, hook: PhaseHook) -> None:
        """Register a hook. Deduplicates by name within phase."""
        phase = hook.phase
        if phase not in self._hooks:
            logger.warning("PhaseHookRegistry: unknown phase %r, creating", phase)
            self._hooks[phase] = []

        hooks = self._hooks[phase]
        for existing in hooks:
            if existing.name == hook.name:
                logger.debug("Hook %s already registered in %s, skipping", hook.name, phase)
                return

        hooks.append(hook)
        hooks.sort(key=lambda h: h.priority)
        logger.debug(
            "Registered hook: %s (phase=%s, priority=%d)",
            hook.name, phase, hook.priority,
        )

    def unregister(self, phase: str, name: str) -> bool:
        """Remove a hook by phase and name."""
        if phase not in self._hooks:
            return False
        before = len(self._hooks[phase])
        self._hooks[phase] = [h for h in self._hooks[phase] if h.name != name]
        return len(self._hooks[phase]) < before

    def dispatch(self, phase: str, ctx: PhaseContext, operations: list[str]) -> None:
        """Execute all hooks for a phase in priority order, respecting gates."""
        hooks = self._hooks.get(phase, [])
        for hook in hooks:
            try:
                if not hook.should_run(ctx):
                    logger.debug("Hook %s skipped (gate)", hook.name)
                    continue
                hook.execute(ctx, operations)
            except Exception as e:
                logger.warning("Hook %s failed: %s", hook.name, e)
                operations.append(f"hook_error:{hook.name}:{e}")

    def get_hooks(self, phase: str) -> list[PhaseHook]:
        """Get all hooks for a phase (sorted by priority)."""
        return list(self._hooks.get(phase, []))

    def hook_count(self, phase: str | None = None) -> int:
        """Count hooks, optionally filtered by phase."""
        if phase is not None:
            return len(self._hooks.get(phase, []))
        return sum(len(hooks) for hooks in self._hooks.values())

    def hook_names(self, phase: str) -> list[str]:
        """List hook names for a phase."""
        return [h.name for h in self._hooks.get(phase, [])]

    def stats(self) -> dict:
        """Registry statistics."""
        return {
            phase: {
                "count": len(hooks),
                "names": [h.name for h in hooks],
            }
            for phase, hooks in self._hooks.items()
        }
