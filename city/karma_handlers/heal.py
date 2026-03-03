"""Heal Handler — Execute HEAL intents on failing contracts + PR creation.

8E: DIW-aware — healing only runs when venu energy >= 32 (high energy).
Healing is resource-intensive (executor, PRs, git ops). In low-energy
ticks, the city conserves resources by deferring heals to the next cycle.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.cognition import emit_event
from city.karma_handlers import BaseKarmaHandler
from city.karma_handlers.diw_bridge import DIWAwareHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.HEAL")

# Minimum venu energy to run healing (0-63 scale).
# 32 = midpoint — only heal in the upper half of the energy cycle.
_HEAL_VENU_THRESHOLD: int = 32


class HealHandler(DIWAwareHandler, BaseKarmaHandler):
    """Heal failing contracts via executor, create PRs for fixes.

    DIW-gated: requires venu energy >= 32 (high-energy tick).
    """

    @property
    def name(self) -> str:
        return "heal"

    @property
    def priority(self) -> int:
        return 70

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.executor is None or ctx.contracts is None:
            return False
        if self.current_diw is not None and self.venu_energy < _HEAL_VENU_THRESHOLD:
            logger.debug(
                "HEAL: Skipped — venu energy %d < %d (low-energy tick)",
                self.venu_energy, _HEAL_VENU_THRESHOLD,
            )
            return False
        return True

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        all_specs = getattr(ctx, "_all_specs", {})
        all_inventories = getattr(ctx, "_all_inventories", {})

        from city.mission_router import authorize_mission

        heal_authorized = authorize_mission("heal_", all_specs, ctx.active_agents, all_inventories)
        if not heal_authorized:
            logger.info(
                "KARMA: No agent with validate capability — executor handles heal as system service"
            )

        for contract in ctx.contracts.failing():
            details = contract.last_result.details if contract.last_result else []
            fix = ctx.executor.execute_heal(contract.name, details)
            operations.append(f"heal:{fix.contract_name}:{fix.action_taken}:{fix.success}")
            logger.info(
                "KARMA: Heal %s — %s (success=%s)",
                fix.contract_name, fix.action_taken, fix.success,
            )

            if fix.success and fix.files_changed:
                pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
                if pr is not None and pr.success:
                    operations.append(f"pr_created:{pr.pr_url}")
                    emit_event(
                        "ACTION", "karma", f"PR created: {pr.pr_url}",
                        {
                            "action": "pr_created",
                            "contract": contract.name,
                            "pr_url": pr.pr_url,
                            "heartbeat": ctx.heartbeat_count,
                        },
                    )
                    from city.registry import SVC_PR_LIFECYCLE
                    pr_mgr = ctx.registry.get(SVC_PR_LIFECYCLE)
                    if pr_mgr is not None:
                        pr_mgr.track(pr.pr_url, pr.branch, contract.name, ctx.heartbeat_count)
                    logger.info("KARMA: PR created — %s", pr.pr_url)
