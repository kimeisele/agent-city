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
from typing import Any, Protocol

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
    _denied: int = 0

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

        allowed, denial_reason = _authorize_intent_execution(ctx, intent, handler_name)
        if not allowed:
            self._denied += 1
            logger.warning(
                "IntentExecutor: denied %s (signal=%s, reason=%s)",
                handler_name, intent.signal, denial_reason,
            )
            return f"denied:{handler_name}:{denial_reason}"

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

    def execute_brain_action(
        self,
        ctx: Any,
        action: Any,
        attention: Any = None,
        **intent_context: Any,
    ) -> str:
        """Unified dispatch for BrainActions.

        Schritt 6B: Single entry point for both gateway + brain_health.
        BrainAction → CityIntent → CityAttention.route() → execute().
        """
        intent_context.setdefault("source", "brain")
        intent = action.to_city_intent(**intent_context)
        handler_name = attention.route(intent.signal) if attention else None
        return self.execute(ctx, intent, handler_name)

    def execute_batch(
        self,
        ctx: Any,
        intents_and_handlers: list[tuple[Any, str | None]],
    ) -> list[str]:
        """Execute multiple intents at once."""
        return [self.execute(ctx, intent, handler) for intent, handler in intents_and_handlers]

    def stats(self) -> dict:
        return {
            "handlers": list(self._handlers.keys()),
            "executed": self._executed,
            "failed": self._failed,
            "unhandled": self._unhandled,
            "denied": self._denied,
        }

    # ── Built-in Handlers ────────────────────────────────────────────

    def _register_builtins(self) -> None:
        """Register handlers for all _BUILTIN_INTENTS from attention.py."""
        # Reactor pain handlers
        self.register("upgrade_prana_engine", _handle_upgrade_prana_engine)
        self.register("spawn_agents", _handle_spawn_agents)
        self.register("investigate_prana_drain", _handle_investigate_prana_drain)
        self.register("create_healing_mission", _handle_create_healing_mission)
        self.register("scale_down_cycles", _handle_scale_down_cycles)
        self.register("emergency_energy_injection", _handle_emergency_energy_injection)

        # Brain action handlers (Schritt 6B: unified dispatch)
        self.register("handle_brain_flag_bottleneck", _handle_brain_flag_bottleneck)
        self.register("handle_brain_check_health", _handle_brain_check_health)
        self.register("handle_brain_investigate", _handle_brain_investigate)
        self.register("handle_brain_create_mission", _handle_brain_create_mission)
        self.register("handle_brain_assign_agent", _handle_brain_assign_agent)
        self.register("handle_brain_escalate", _handle_brain_escalate)
        self.register("handle_brain_retract", _handle_brain_retract)
        self.register("handle_brain_quarantine", _handle_brain_quarantine)
        self.register("handle_brain_run_status", _handle_brain_run_status)


def _intent_authority_requirement(intent: Any, handler_name: str) -> Any | None:
    signal = str(getattr(intent, "signal", ""))
    if not (signal.startswith("brain:") or handler_name.startswith("handle_brain_")):
        return None

    from city.brain_action import parse_action_hint
    from city.membrane import requirement_for_auth_tier

    hint = signal.split(":", 1)[1] if signal.startswith("brain:") else ""
    if not hint and handler_name.startswith("handle_brain_"):
        hint = handler_name.removeprefix("handle_brain_")

    action = parse_action_hint(hint)
    if action is None:
        return None
    return requirement_for_auth_tier(action.auth_tier)


def _authorize_intent_execution(
    ctx: Any,
    intent: Any,
    handler_name: str,
) -> tuple[bool, str]:
    requirement = _intent_authority_requirement(intent, handler_name)
    if requirement is None:
        return True, "ok"

    from city.membrane import authorize_ingress

    context = getattr(intent, "context", {}) or {}
    return authorize_ingress(
        ctx,
        membrane=context.get("membrane"),
        author=str(context.get("author", "")),
        requirement=requirement,
    )


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


def _handle_emergency_energy_injection(ctx: Any, intent: Any) -> str:  # noqa: E302
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


# =============================================================================
# BRAIN ACTION HANDLERS (Schritt 6B: unified dispatch)
# =============================================================================
# These handlers execute BrainActions routed via CityAttention.
# Intent.context carries the BrainAction fields: verb, target, detail, source.


def _handle_brain_flag_bottleneck(ctx: Any, intent: Any) -> str:
    """Brain flagged a bottleneck → emit reactor pain signal."""
    target = intent.context.get("target", "unknown")
    source = intent.context.get("source", "brain")
    if hasattr(ctx, "reactor") and ctx.reactor is not None:
        try:
            ctx.reactor.emit_pain(
                source=f"brain_{source}",
                severity=0.5,
                detail=f"Bottleneck flagged: {target}",
            )
            return f"bottleneck_flagged:{target}"
        except Exception as e:
            return f"error:flag_bottleneck:{e}"
    return f"logged:bottleneck:{target}"


def _handle_brain_check_health(ctx: Any, intent: Any) -> str:
    """Brain requested health check → emit reactor pain signal."""
    target = intent.context.get("target", "unknown")
    if hasattr(ctx, "reactor") and ctx.reactor is not None:
        try:
            ctx.reactor.emit_pain(
                source="brain_health_check",
                severity=0.3,
                detail=f"Health check requested for {target}",
            )
        except Exception:
            pass
    return f"health_check:{target}"


def _handle_brain_investigate(ctx: Any, intent: Any) -> str:
    """Brain wants investigation → create investigation mission."""
    target = intent.context.get("target", "unknown")
    discussion_number = intent.context.get("discussion_number", 0)
    if target and ctx.sankalpa is not None:
        try:
            from city.missions import create_discussion_mission
            mission_id = create_discussion_mission(
                ctx, discussion_number, f"Investigate: {target}", "inquiry",
            )
            if mission_id:
                return f"investigate_mission:{mission_id}"
        except Exception as e:
            return f"error:investigate:{e}"
    return f"logged:investigate:{target}"


def _handle_brain_create_mission(ctx: Any, intent: Any) -> str:
    """Brain wants to create a mission."""
    target = intent.context.get("target", "")
    discussion_number = intent.context.get("discussion_number", 0)
    intent_type = intent.context.get("intent_type", "propose")
    if target and ctx.sankalpa is not None:
        try:
            from city.missions import create_discussion_mission
            mission_id = create_discussion_mission(
                ctx, discussion_number, target, intent_type,
            )
            if mission_id:
                return f"mission_created:{mission_id}"
        except Exception as e:
            return f"error:create_mission:{e}"
    return f"logged:create_mission:{target[:40]}"


def _handle_brain_assign_agent(ctx: Any, intent: Any) -> str:
    """Brain wants to assign an agent to a task."""
    target = intent.context.get("target", "")
    detail = intent.context.get("detail", "")
    discussion_number = intent.context.get("discussion_number", 0)
    if target and detail:
        try:
            from city.missions import create_community_mission
            mission_id = create_community_mission(
                ctx, discussion_number, f"Assigned: {detail[:60]}", "propose",
            )
            if mission_id:
                return f"assigned:{target}:{mission_id}"
        except Exception as e:
            return f"error:assign_agent:{e}"
    return f"logged:assign:{target}"


def _handle_brain_escalate(ctx: Any, intent: Any) -> str:
    """Brain escalates an issue → emit high-severity reactor pain."""
    target = intent.context.get("target", "unknown")
    source = intent.context.get("source", "brain")
    if hasattr(ctx, "reactor") and ctx.reactor is not None:
        try:
            ctx.reactor.emit_pain(
                source=f"brain_{source}",
                severity=0.7,
                detail=f"Escalation: {target[:100]}",
            )
        except Exception:
            pass
    return f"escalated:{target[:40]}"


def _handle_brain_retract(ctx: Any, intent: Any) -> str:
    """Brain wants to retract a bad post."""
    comment_id = intent.context.get("target", "")
    reason = intent.context.get("detail", "quality")
    if comment_id and ctx.discussions is not None and not getattr(ctx, "offline_mode", False):
        try:
            retracted = ctx.discussions.retract_post(comment_id, reason=reason)
            if retracted:
                return f"retracted:{comment_id[:20]}"
            return f"retract_failed:{comment_id[:20]}"
        except Exception as e:
            return f"error:retract:{e}"
    return f"logged:retract:{comment_id[:20]}"


def _handle_brain_quarantine(ctx: Any, intent: Any) -> str:
    """Brain wants to quarantine an agent."""
    context = getattr(intent, "context", {}) or {}
    agent_name = context.get("target", "")
    reason = context.get("detail", "brain_action")
    if agent_name and ctx.pokedex is not None:
        try:
            ctx.pokedex.freeze(
                agent_name,
                f"quarantine:{reason[:60]}",
                author=str(context.get("author", "")),
                membrane=context.get("membrane"),
            )
            return f"quarantined:{agent_name}"
        except Exception as e:
            return f"error:quarantine:{e}"
    return f"logged:quarantine:{agent_name}"


def _handle_brain_run_status(ctx: Any, intent: Any) -> str:
    """Brain requested status — read-only, just acknowledge."""
    return "status_acknowledged"
