"""Cognition Handler — Cartridge routing + cognitive action execution.

8E: DIW-aware — cognitive actions only run when venu energy >= 16 (moderate).
Cognitive work (proposals, missions, nadi dispatch) is moderately expensive.
In very low-energy ticks, the city defers non-essential cognition.
"""

from __future__ import annotations

import logging
import time as _time
from typing import TYPE_CHECKING

from config import get_config

from city.cognition import emit_event
from city.karma_handlers import BaseKarmaHandler
from city.karma_handlers.diw_bridge import DIWAwareHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.COGNITION")

# Minimum venu energy to run cognition (0-63 scale).
# 16 = quarter-point — more permissive than heal (32) but still
# gates out the lowest-energy ticks where the city should rest.
_COGNITION_VENU_THRESHOLD: int = 16

# Maps buddhi function × agent capability → existing city operation.
_ACTION_MAP: dict[str, dict[str, str]] = {
    "BRAHMA": {
        "propose": "council_propose",
        "create": "create_mission",
        "observe": "emit_observation",
    },
    "source": {
        "propose": "council_propose",
        "create": "create_mission",
        "observe": "emit_observation",
    },
    "VISHNU": {
        "observe": "emit_observation",
        "monitor": "emit_observation",
        "relay": "nadi_dispatch",
    },
    "carrier": {
        "observe": "emit_observation",
        "monitor": "emit_observation",
        "relay": "nadi_dispatch",
    },
    "SHIVA": {
        "validate": "trigger_audit",
        "execute": "trigger_heal",
        "transform": "trigger_audit",
    },
    "deliverer": {
        "validate": "trigger_audit",
        "execute": "trigger_heal",
        "transform": "trigger_audit",
    },
}


def _learn(ctx: PhaseContext, source: str, action: str, *, success: bool) -> None:
    if ctx.learning is not None:
        ctx.learning.record_outcome(source, action, success)


class CognitionHandler(DIWAwareHandler, BaseKarmaHandler):
    """Route domain missions to best-fit agents via capability scoring.

    DIW-gated: requires venu energy >= 16 (moderate-energy tick).
    """

    @property
    def name(self) -> str:
        return "cognition"

    @property
    def priority(self) -> int:
        return 40

    def should_run(self, ctx: PhaseContext) -> bool:
        if self.current_diw is not None and self.venu_energy < _COGNITION_VENU_THRESHOLD:
            logger.debug(
                "COGNITION: Skipped — venu energy %d < %d (low-energy tick)",
                self.venu_energy, _COGNITION_VENU_THRESHOLD,
            )
            return False
        return True

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        all_specs = ctx.all_specs
        all_inventories = ctx.all_inventories
        _route_to_cartridges(ctx, operations, all_specs, all_inventories)


def _route_to_cartridges(
    ctx: PhaseContext,
    operations: list[str],
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]] | None = None,
) -> None:
    """Route domain missions to best-fit agents via capability scoring + hard enforcement."""
    from city.registry import SVC_CARTRIDGE_LOADER
    from city.mission_router import route_mission

    loader = ctx.registry.get(SVC_CARTRIDGE_LOADER)
    if loader is None or ctx.sankalpa is None:
        return

    try:
        active = ctx.sankalpa.registry.get_active_missions()
    except Exception:
        return

    autonomy_cfg = get_config().get("autonomy", {})
    max_cognitive_actions = autonomy_cfg.get("max_actions_per_cycle", 3)
    cognitive_count = 0

    disc_cfg = get_config().get("discussions", {})
    max_action_posts = disc_cfg.get("max_action_posts_per_cycle", 1)
    action_post_count = 0

    for mission in active:
        if mission.id.startswith(("issue_", "exec_")):
            continue

        result = route_mission(mission, all_specs, ctx.active_agents, all_inventories)

        if result["blocked"]:
            operations.append(f"route_blocked:{mission.id}:no_qualified_agent")
            logger.info(
                "KARMA: Mission %s blocked — %d agents failed capability gate",
                mission.id, result["blocked_count"],
            )
            continue

        agent_name = result["agent_name"]
        if agent_name is None:
            continue

        cartridge = loader.get(agent_name)
        if cartridge is None:
            continue

        try:
            if hasattr(cartridge, "process"):
                cognitive_action = cartridge.process(mission.description)

                if cognitive_action.get("status") != "cognized":
                    operations.append(f"routed_passive:{agent_name}:{mission.id}")
                    continue

                if cognitive_count >= max_cognitive_actions:
                    operations.append(f"cognition_throttled:{agent_name}")
                    continue

                operation_name = _execute_cognitive_action(
                    ctx, cognitive_action, mission, operations,
                )
                executed = operation_name is not None
                _learn(
                    ctx, f"cognition:{agent_name}",
                    cognitive_action["function"], success=executed,
                )

                if executed:
                    cognitive_count += 1
                    if (
                        ctx.discussions is not None
                        and not ctx.offline_mode
                        and action_post_count < max_action_posts
                    ):
                        spec = _get_agent_spec(ctx, agent_name)
                        if spec is not None:
                            cognitive_action["_operation"] = operation_name
                            posted = ctx.discussions.post_agent_action(
                                spec, cognitive_action, mission.id,
                            )
                            if posted:
                                action_post_count += 1
                                operations.append(f"disc_action:{agent_name}:{cognitive_action['function']}")

                operations.append(
                    f"routed:{agent_name}:{mission.id}:score={result['score']:.2f}"
                    f":cognized={cognitive_action['function']}"
                )
                logger.info(
                    "KARMA: Routed %s → %s (score=%.2f, function=%s, executed=%s)",
                    mission.id, agent_name, result["score"], cognitive_action["function"], executed,
                )
        except Exception as e:
            logger.warning("KARMA: Agent %s failed for mission %s: %s", agent_name, mission.id, e)


def _execute_cognitive_action(
    ctx: PhaseContext,
    action: dict,
    mission: object,
    operations: list[str],
) -> str | None:
    """Map CognitiveAction -> existing city operation. Execute it."""
    function = action.get("function", "")
    caps = action.get("capabilities", [])
    agent_name = action.get("agent", "")
    autonomy_cfg = get_config().get("autonomy", {})

    min_confidence = autonomy_cfg.get("min_confidence", 0.2)
    if ctx.learning is not None:
        confidence = ctx.learning.get_confidence(f"cognition:{agent_name}", function)
        if confidence < min_confidence:
            operations.append(f"cognition_low_confidence:{agent_name}:{function}:{confidence:.2f}")
            return None

    cell = ctx.pokedex.get_cell(agent_name)
    if cell is None or not cell.is_alive:
        return None

    function_map = _ACTION_MAP.get(function, {})
    operation = None
    for cap in caps:
        if cap in function_map:
            operation = function_map[cap]
            break

    if operation is None:
        operations.append(f"cognition_no_op:{agent_name}:{function}")
        return None

    success = False
    if operation == "council_propose" and ctx.council is not None:
        success = _cognitive_propose(ctx, action, mission)
    elif operation == "create_mission" and ctx.sankalpa is not None:
        success = _cognitive_create_mission(ctx, action, mission)
    elif operation == "emit_observation":
        emit_event(
            "OBSERVATION", agent_name, action.get("composed", ""),
            {"function": function, "chapter": action.get("chapter", 0), "mission": mission.id},
        )
        success = True
    elif operation == "nadi_dispatch" and ctx.agent_nadi is not None:
        success = _cognitive_nadi_dispatch(ctx, action, agent_name)
    elif operation == "trigger_audit" and ctx.audit is not None:
        try:
            ctx.audit.run_all()
            success = True
        except Exception:
            success = False
    elif operation == "trigger_heal" and ctx.immune is not None:
        diagnosis = ctx.immune.diagnose(f"mission:{mission.id}")
        if diagnosis.healable:
            result = ctx.immune.heal(diagnosis)
            success = result.success

    if success:
        operations.append(f"cognition:{agent_name}:{function}→{operation}")
        emit_event(
            "ACTION", agent_name, f"Cognitive action: {operation}",
            {
                "action": "cognitive_exec",
                "function": function,
                "operation": operation,
                "mission": mission.id,
                "composed": action.get("composed", ""),
            },
        )
        return operation

    return None


def _cognitive_propose(ctx: PhaseContext, action: dict, mission: object) -> bool:
    if ctx.council is None or ctx.council.elected_mayor is None:
        return False
    from city.council import ProposalType
    ctx.council.propose(
        title=f"Agent Proposal: {action.get('composed', mission.name)[:60]}",
        description=mission.description,
        proposer=action["agent"],
        proposal_type=ProposalType.POLICY,
        action={"type": "improve", "source": "cognitive"},
        timestamp=_time.time(),
    )
    return True


def _cognitive_create_mission(ctx: PhaseContext, action: dict, mission: object) -> bool:
    from city.missions import create_improvement_mission
    proposal = type("Proposal", (), {
        "id": f"cog_{mission.id}",
        "title": action.get("composed", "")[:60] or mission.name,
        "description": mission.description,
    })()
    create_improvement_mission(ctx, proposal)
    return True


def _cognitive_nadi_dispatch(ctx: PhaseContext, action: dict, agent_name: str) -> bool:
    """Dispatch cognitive observation via AgentNadi with signal protocol."""
    composed = action.get("composed", "")
    function = action.get("function", "")
    chapter = action.get("chapter", 0)
    text = f"[{function}] ch.{chapter}: {composed}" if composed else f"[{function}] ch.{chapter}"

    try:
        from city.signal_encoder import encode_signal
        from city.signal_router import route_signal
        from city.jiva import derive_jiva

        sender_jiva = derive_jiva(agent_name)
        signal = encode_signal(text, sender_jiva)
        candidates = _build_candidate_jivas(ctx, exclude=agent_name)

        if candidates:
            routes = route_signal(signal, candidates, top_n=3)
            for route in routes:
                ctx.agent_nadi.send(agent_name, route.receiver_name, text, signal=signal)
            return True
    except Exception as e:
        logger.debug("Signal encoding failed for %s, falling back to broadcast: %s", agent_name, e)

    ctx.agent_nadi.broadcast(agent_name, text)
    return True


_MAX_CANDIDATE_JIVAS = 10


def _build_candidate_jivas(ctx: PhaseContext, exclude: str = "") -> dict:
    from city.jiva import derive_jiva
    candidates = {}
    for name in list(ctx.active_agents)[:_MAX_CANDIDATE_JIVAS + 1]:
        if name == exclude:
            continue
        if len(candidates) >= _MAX_CANDIDATE_JIVAS:
            break
        try:
            candidates[name] = derive_jiva(name)
        except Exception:
            continue
    return candidates


def _get_agent_spec(ctx: PhaseContext, agent_name: str) -> dict | None:
    from city.registry import SVC_CARTRIDGE_FACTORY
    factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
    if factory is None:
        return None
    return factory.get_spec(agent_name)
