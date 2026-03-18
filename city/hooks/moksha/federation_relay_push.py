"""
MOKSHA Hook: Federation Relay Push — local outbox → Hub inbox.

Pushes local NADI outbox messages to steward-federation Hub
AFTER FederationReportHook flushes (priority 62 > 60).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.RELAY_PUSH")


class FederationRelayPushHook(BasePhaseHook):
    """Push local outbox to Hub inbox after NADI flush."""

    @property
    def name(self) -> str:
        return "federation_relay_push"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 62  # after FederationReportHook flush (60)

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation_nadi is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        try:
            from city.federation_relay import FederationRelay

            relay = FederationRelay(
                local_outbox=ctx.federation_nadi.outbox_path,
                local_inbox=ctx.federation_nadi.inbox_path,
            )
            pushed = relay.push_to_hub()
            if pushed:
                reflection = getattr(ctx, "_reflection", {})
                reflection["federation_relay_pushed"] = pushed
                operations.append(f"relay_push:{pushed}")
                logger.info("RELAY_PUSH: Pushed %d messages to Hub", pushed)
        except Exception as e:
            logger.debug("RELAY_PUSH: Failed (non-fatal): %s", e)
