"""Signal Handler — A2A semantic signal processing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.SIGNALS")

_SIGNAL_AFFINITY_EXECUTOR_THRESHOLD = 0.8
_SIGNAL_AFFINITY_MIN = 0.3
_MAX_SIGNAL_REPLIES_PER_CYCLE = 5
_MAX_CANDIDATE_JIVAS = 10


class SignalHandler(BaseKarmaHandler):
    """Drain agent nadi inboxes, decode signals, reply or create missions."""

    @property
    def name(self) -> str:
        return "signals"

    @property
    def priority(self) -> int:
        return 50

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.agent_nadi is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        _process_agent_signals(ctx, operations)


def _process_agent_signals(ctx: PhaseContext, operations: list[str]) -> None:
    """Drain agent nadi inboxes, decode signals, reply or create missions.

    Three gates:
    - affinity < 0.3 → ignore (noise)
    - affinity >= 0.8 → create Sankalpa mission (signal → karma)
    - hop_count >= MAX_SIGNAL_HOPS → no reply (prevents infinite ping-pong)
    """
    from city.signal import MAX_SIGNAL_HOPS
    from city.signal_decoder import decode_signal
    from city.signal_composer import compose_response_signal
    from city.semantic import compose_prose
    from city.jiva import derive_jiva
    from city.missions import create_a2a_signal_mission
    from city.karma_handlers.brain_health import brain_budget_ok

    replies_this_cycle = 0

    for agent_name in list(ctx.active_agents)[:_MAX_CANDIDATE_JIVAS]:
        msgs = ctx.agent_nadi.drain(agent_name)
        for msg in msgs:
            sig = msg.get("signal")
            if sig is None:
                continue

            try:
                receiver_jiva = derive_jiva(agent_name)
                decoded = decode_signal(sig, receiver_jiva)
            except Exception as e:
                logger.debug("Signal decode failed for %s: %s", agent_name, e)
                continue

            if decoded.affinity < _SIGNAL_AFFINITY_MIN:
                continue

            # HIGH affinity → create Sankalpa mission
            if decoded.affinity >= _SIGNAL_AFFINITY_EXECUTOR_THRESHOLD:
                create_a2a_signal_mission(ctx, decoded, agent_name)
                operations.append(
                    f"signal_mission:{msg['source']}→{agent_name}"
                    f":affinity={decoded.affinity:.2f}"
                )

            # MEDIUM affinity → brain comprehension (0.3-0.8)
            brain = ctx.brain
            if (
                decoded.affinity < _SIGNAL_AFFINITY_EXECUTOR_THRESHOLD
                and brain is not None
                and brain_budget_ok(ctx)
            ):
                from city.registry import SVC_CARTRIDGE_FACTORY

                factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
                receiver_spec = (
                    factory.get_spec(agent_name) if factory is not None else {}
                ) or {}
                signal_thought = brain.comprehend_signal(decoded, receiver_spec)
                if signal_thought is not None:
                    ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1
                    operations.append(
                        f"brain_signal:{agent_name}"
                        f":intent={signal_thought.intent}"
                        f":confidence={signal_thought.confidence:.2f}"
                    )
                else:
                    operations.append(f"brain_signal_noop:{agent_name}")

            # Reply (if under hop limit and cycle budget)
            if (
                sig.hop_count < MAX_SIGNAL_HOPS
                and replies_this_cycle < _MAX_SIGNAL_REPLIES_PER_CYCLE
            ):
                reply = compose_response_signal(decoded, receiver_jiva)
                if reply is not None:
                    prose = compose_prose(reply) or ""
                    ctx.agent_nadi.send(
                        agent_name, msg["source"], prose, signal=reply,
                    )
                    replies_this_cycle += 1
                    operations.append(
                        f"signal_reply:{agent_name}→{msg['source']}"
                        f":hop{reply.hop_count}"
                    )
