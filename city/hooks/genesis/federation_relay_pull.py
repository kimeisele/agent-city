"""
GENESIS Hook: Federation Relay Pull — Hub outbox → local inbox.

Pulls new messages from steward-federation Hub into local NADI inbox
BEFORE FederationNadiHook reads them (priority 28 < 30).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.RELAY_PULL")


class FederationRelayPullHook(BasePhaseHook):
    """Pull messages from Hub outbox into local inbox before NADI reads them."""

    @property
    def name(self) -> str:
        return "federation_relay_pull"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 28  # before FederationNadiHook (30)

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation_nadi is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        try:
            from city.federation_relay import FederationRelay

            relay = FederationRelay(
                local_outbox=ctx.federation_nadi.outbox_path,
                local_inbox=ctx.federation_nadi.inbox_path,
            )
            pulled = relay.pull_from_hub()
            if pulled:
                operations.append(f"relay_pull:{pulled}")
                logger.info("RELAY_PULL: Pulled %d messages from Hub", pulled)
        except Exception as e:
            logger.debug("RELAY_PULL: Failed (non-fatal): %s", e)
