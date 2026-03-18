"""
MOKSHA Hook: City Diary — hourly summary posted to Announcements.

Posts a deterministic summary of what happened this heartbeat cycle.
Zero LLM. Just data. Posted every 4th heartbeat (~1 hour).

A visitor reading Announcements sees the city reporting on itself
honestly — proof of life, not marketing.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.CITY_DIARY")

# Post every Nth heartbeat (4 = ~hourly with 15-min crons)
_POST_EVERY_N = 4
# Announcements thread ID (Discussion #134)
_ANNOUNCEMENTS_THREAD = 134


class CityDiaryHook(BasePhaseHook):
    """Post hourly city diary to Announcements — proof of life."""

    @property
    def name(self) -> str:
        return "city_diary"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 72  # After discussions outbound (70), before wiki (75)

    def should_run(self, ctx: PhaseContext) -> bool:
        return (
            ctx.discussions is not None
            and not ctx.offline_mode
            and ctx.heartbeat_count % _POST_EVERY_N == 0
        )

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        stats = reflection.get("city_stats", {})
        total = stats.get("total", 0)
        active = stats.get("active", 0) + stats.get("citizen", 0)

        # Collect data from this cycle
        imm_stats = ctx.immigration.stats() if ctx.immigration else {}
        granted = imm_stats.get("citizenship_granted", 0)
        pending = imm_stats.get("pending_applications", 0)

        nadi_stats = {}
        if ctx.federation_nadi is not None:
            nadi_stats = ctx.federation_nadi.stats()

        ops = reflection.get("operations_log", [])
        disc_stats = reflection.get("discussions", {})
        wiki_synced = reflection.get("wiki_synced", False)

        # Count operations by type
        relay_count = sum(1 for o in ops if "relay" in o)
        immigration_count = sum(1 for o in ops if "immigration" in o)

        diary = (
            f"**Heartbeat #{ctx.heartbeat_count}** — City Diary\n\n"
            f"**Population**: {total} agents, {active} active\n"
            f"**Immigration**: {granted} citizens total, {pending} pending\n"
            f"**NADI**: {nadi_stats.get('outbox_on_disk', 0)} outbound, "
            f"{nadi_stats.get('inbox_on_disk', 0)} inbound\n"
            f"**Discussions**: {disc_stats.get('responses_posted', 0)} responses this cycle\n"
            f"**Wiki**: {'updated' if wiki_synced else 'unchanged'}\n"
            f"**Operations**: {len(ops)} this cycle"
        )

        if relay_count:
            diary += f" ({relay_count} relay, {immigration_count} immigration)"

        try:
            # Post to Announcements thread (#134) via discussions bridge
            posted = ctx.discussions._comment_on_discussion(_ANNOUNCEMENTS_THREAD, diary)
            if posted:
                operations.append("city_diary:posted")
                logger.info("CITY_DIARY: posted to #%d", _ANNOUNCEMENTS_THREAD)
            else:
                operations.append("city_diary:skipped")
        except Exception as e:
            logger.debug("CITY_DIARY: failed (non-fatal): %s", e)
