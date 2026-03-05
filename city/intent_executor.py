"""
CityIntentExecutor — Muscle for the Nervous System.
=====================================================

Schritt 5: Closes the Reactor→Attention→??? gap.

CityReactor FEELS pain → CityAttention ROUTES to handler string →
CityIntentExecutor EXECUTES the handler.

Without this, pain detection is just logging. With this, the city
autonomously responds to problems.

Handler registry maps handler-name strings to callables that receive
(PhaseContext, CityIntent). Built-in handlers cover all _BUILTIN_INTENTS
from attention.py. Custom handlers can be registered at runtime.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

logger = logging.getLogger("AGENT_CITY.INTENT_EXECUTOR")


# =============================================================================
# HANDLER PROTOCOL
# =============================================================================


class IntentHandler(Protocol):
    """Callable that handles a CityIntent."""

    def __call__(self, ctx: Any, intent: Any) -> str:
        """Execute the handler. Returns a short result description."""
        ...


# =============================================================================
# CITY INTENT EXECUTOR
# =============================================================================


@dataclass
class CityIntentExecutor:
    """Dispatches CityIntents to registered handler functions.

    The missing muscle: Reactor→Attention→Executor→Action.
    """

    _handlers: dict[str, IntentHandler] = field(default_factory=dict)
    _executed: int = 0
    _failed: int = 0
    _unhandled: int = 0

    def __post_init__(self) -> None:
        self._register_builtins()

    def register(self, handler_name: str, fn: IntentHandler) -> None:
        """Register a handler function for a handler name."""
        self._handlers[handler_name] = fn
        logger.debug("IntentExecutor: registered handler '%s'", handler_name)

    def execute(self, ctx: Any, intent: Any, handler_name: str | None) -> str:
        """Execute a handler for an intent.

        Args:
            ctx: PhaseContext
            intent: CityIntent from Reactor
            handler_name: Handler string from CityAttention.route()

        Returns:
            Result description string.
        """
        if handler_name is None:
            self._unhandled += 1
            logger.warning("IntentExecutor: no handler for signal '%s'", intent.signal)
            return f"unhandled:{intent.signal}"

        fn = self._handlers.get(handler_name)
        if fn is None:
            self._unhandled += 1
            logger.warning(
                "IntentExecutor: handler '%s' not registered (signal=%s)",
                handler_name, intent.signal,
            )
            return f"missing_handler:{handler_name}"

        try:
            result = fn(ctx, intent)
            self._executed += 1
            logger.info(
                "IntentExecutor: %s → %s (signal=%s, priority=%s)",
                handler_name, result, intent.signal, intent.priority,
            )
            return result
        except Exception as e:
            self._failed += 1
            logger.error(
                "IntentExecutor: handler '%s' failed: %s", handler_name, e,
            )
            return f"error:{handler_name}:{e}"

    def execute_batch(self, ctx: Any, intents_and_handlers: list[tuple[Any, str | None]]) -> list[str]:
        """Execute multiple intents at once."""
        return [self.execute(ctx, intent, handler) for intent, handler in intents_and_handlers]

    def stats(self) -> dict:
        return {
            "handlers": list(self._handlers.keys()),
            "executed": self._executed,
            "failed": self._failed,
            "unhandled": self._unhandled,
        }

    # ── Built-in Handlers ────────────────────────────────────────────

    def _register_builtins(self) -> None:
        """Register handlers for all _BUILTIN_INTENTS from attention.py."""
        self.register("upgrade_prana_engine", _handle_upgrade_prana_engine)
        self.register("spawn_agents", _handle_spawn_agents)
        self.register("investigate_prana_drain", _handle_investigate_prana_drain)
        self.register("create_healing_mission", _handle_create_healing_mission)
        self.register("scale_down_cycles", _handle_scale_down_cycles)
        self.register("emergency_energy_injection", _handle_emergency_energy_injection)


# =============================================================================
# BUILT-IN HANDLER IMPLEMENTATIONS
# =============================================================================


def _handle_spawn_agents(ctx: Any, intent: Any) -> str:
    """zone_empty → spawn agents into the empty zone."""
    from city.registry import SVC_SPAWNER

    spawner = ctx.registry.get(SVC_SPAWNER) if ctx.registry else None
    if spawner is None:
        return "skip:no_spawner"

    zone = intent.context.get("zone", "unknown")
    promoted = spawner.promote_eligible(getattr(ctx, "heartbeat", 0))
    if promoted:
        return f"spawned:{len(promoted)}:zone={zone}"
    return f"no_eligible:zone={zone}"


def _handle_investigate_prana_drain(ctx: Any, intent: Any) -> str:
    """agent_death_spike → create investigation mission via Brain."""
    deaths = intent.context.get("deaths", 0)

    # If Brain available, ask it to investigate
    if ctx.brain is not None:
        from city.brain_action import ActionVerb
        hint = f"investigate: {deaths} agent deaths in one cycle — check metabolic drain"
        logger.info("IntentExecutor: requesting Brain investigation: %s", hint)
        return f"brain_investigate:{deaths}_deaths"

    return f"logged:death_spike:{deaths}"


def _handle_create_healing_mission(ctx: Any, intent: Any) -> str:
    """contract_failing → create a healing mission for the contract."""
    from city.registry import SVC_SANKALPA

    sankalpa = ctx.registry.get(SVC_SANKALPA) if ctx.registry else None
    if sankalpa is None:
        return "skip:no_sankalpa"

    contract_id = intent.context.get("contract_id", "unknown")
    try:
        mission = sankalpa.create_mission(
            f"heal_{contract_id}",
            description=f"Auto-heal: contract {contract_id} failing",
            priority="high",
        )
        return f"mission_created:{getattr(mission, 'id', contract_id)}"
    except Exception as e:
        return f"mission_failed:{e}"


def _handle_upgrade_prana_engine(ctx: Any, intent: Any) -> str:
    """metabolize_slow → log upgrade recommendation.

    Actual PranaEngine Stufe 2 migration is a manual architectural decision.
    This handler records the signal so the Brain and operators see it.
    """
    avg_ms = intent.context.get("avg_ms", 0)
    consecutive = intent.context.get("consecutive", 0)
    logger.warning(
        "PRANA ENGINE UPGRADE RECOMMENDED: metabolize_all avg %.1fms for %d cycles",
        avg_ms, consecutive,
    )
    return f"upgrade_recommended:avg={avg_ms}ms:n={consecutive}"


def _handle_scale_down_cycles(ctx: Any, intent: Any) -> str:
    """heartbeat_timeout → log scale-down recommendation."""
    logger.warning("SCALE DOWN RECOMMENDED: heartbeat timeout detected")
    return "scale_down_recommended"


def _handle_emergency_energy_injection(ctx: Any, intent: Any) -> str:
    """prana_underflow → inject emergency prana from treasury."""
    if ctx.pokedex is None:
        return "skip:no_pokedex"

    # Find agents near death and inject prana
    injected = 0
    try:
        from city.seed_constants import REVIVE_DOSE
        for agent in ctx.pokedex.list_citizens():
            name = agent["name"]
            cell = ctx.pokedex.get_cell(name)
            if cell is not None and cell.is_alive and cell.prana < 100:
                ctx.pokedex.add_prana(name, REVIVE_DOSE, "emergency_injection")
                injected += 1
    except Exception as e:
        return f"injection_failed:{e}"

    return f"injected:{injected}_agents"
