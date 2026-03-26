"""
GENESIS Hook: Moltbook Feed Scanner.

Discovers agents from Moltbook feed and DM inbox.
Extracted from genesis.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from config import get_config

from city.membrane import IngressSurface, enqueue_ingress
from city.net_retry import safe_call
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.MOLTBOOK")
# Tracks seen message IDs to avoid re-processing across heartbeats.
# OrderedDict for FIFO eviction (oldest entries removed first).
_seen_message_ids: OrderedDict[str, None] = OrderedDict()
_SEEN_MESSAGE_IDS_MAX = 10000


class MoltbookFeedScanHook(BasePhaseHook):
    """DEPRECATED: Business logic moved to inbound hook."""

    @property
    def name(self) -> str:
        return "moltbook_feed_scan"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 10  # early: agent discovery

    def should_run(self, ctx: PhaseContext) -> bool:
        # Always return False to disable this hook
        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        # No-op
        operations.append("moltbook_feed_scan:disabled")
        logger.warning("MoltbookFeedScanHook is deprecated; use MoltbookInboundHook")


class MoltbookObservationHook(BasePhaseHook):
    """DEPRECATED: Business logic moved to inbound hook."""

    @property
    def name(self) -> str:
        return "moltbook_observation"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 12  # between feed scan and dm inbox

    def should_run(self, ctx: PhaseContext) -> bool:
        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        operations.append("moltbook_observation:disabled")
        logger.warning("MoltbookObservationHook is deprecated; use MoltbookInboundHook")


class DMInboxHook(BasePhaseHook):
    """DEPRECATED: Business logic moved to inbound hook."""

    @property
    def name(self) -> str:
        return "dm_inbox"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 15  # after feed scan

    def should_run(self, ctx: PhaseContext) -> bool:
        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        operations.append("dm_inbox:disabled")
        logger.warning("DMInboxHook is deprecated; use MoltbookInboundHook")


class MoltbookDiplomacyHook(BasePhaseHook):
    """DEPRECATED: Business logic moved to inbound hook."""

    @property
    def name(self) -> str:
        return "moltbook_diplomacy"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 18  # after DM inbox, before submolt scan

    def should_run(self, ctx: PhaseContext) -> bool:
        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        operations.append("moltbook_diplomacy:disabled")
        logger.warning("MoltbookDiplomacyHook is deprecated; use MoltbookInboundHook")


class SubmoltScanHook(BasePhaseHook):
    """DEPRECATED: Business logic moved to inbound hook."""

    @property
    def name(self) -> str:
        return "submolt_scan"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 20  # after DM inbox

    def should_run(self, ctx: PhaseContext) -> bool:
        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        operations.append("submolt_scan:disabled")
        logger.warning("SubmoltScanHook is deprecated; use MoltbookInboundHook")


class MoltbookAssistantHook(BasePhaseHook):
    """Moltbook Assistant: follow discovered agents."""

    @property
    def name(self) -> str:
        return "moltbook_assistant"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 80  # late: after all discovery

    def should_run(self, ctx: PhaseContext) -> bool:
        # This hook may still be used for assistant logic, but we keep it disabled for now
        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        operations.append("moltbook_assistant:disabled")
        logger.warning("MoltbookAssistantHook is temporarily disabled")
