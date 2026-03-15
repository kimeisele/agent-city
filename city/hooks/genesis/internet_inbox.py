"""
GENESIS Hook: Agent-Internet Inbox.

Receives messages from agent-internet via InternetNadi and routes
them through the AGENT_INTERNET membrane surface into CityNadi.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.membrane import IngressSurface, enqueue_ingress
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.INTERNET")


class InternetNadiHook(BasePhaseHook):
    """Receive messages from agent-internet via Internet Nadi.

    Routes external content (web research results, API responses,
    health probes) through the AGENT_INTERNET membrane into the
    city gateway for KARMA processing.
    """

    @property
    def name(self) -> str:
        return "internet_nadi_inbox"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 25  # after submolt (20), before federation (30)

    def should_run(self, ctx: PhaseContext) -> bool:
        from city.registry import SVC_AGENT_INTERNET
        return ctx.registry.get(SVC_AGENT_INTERNET) is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.registry import SVC_AGENT_INTERNET
        internet_nadi = ctx.registry.get(SVC_AGENT_INTERNET)

        messages = internet_nadi.receive()
        for msg in messages:
            enqueue_ingress(
                ctx,
                IngressSurface.AGENT_INTERNET,
                {
                    "source": f"internet:{msg.source}",
                    "text": msg.payload.get("text", msg.operation),
                    "internet_payload": msg.payload,
                    "correlation_id": msg.correlation_id,
                    "operation": msg.operation,
                },
            )
            operations.append(f"internet_nadi:{msg.source}:{msg.operation}")

        if messages:
            logger.info(
                "GENESIS: %d agent-internet messages received", len(messages),
            )
