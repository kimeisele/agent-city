"""Sankalpa Handler — Strategic thinking + issue mission processing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.cognition import emit_event
from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.SANKALPA")


def _learn(ctx: PhaseContext, source: str, action: str, *, success: bool) -> None:
    if ctx.learning is not None:
        ctx.learning.record_outcome(source, action, success)


class SankalpaHandler(BaseKarmaHandler):
    """Sankalpa strategic thinking + issue/exec mission processing."""

    @property
    def name(self) -> str:
        return "sankalpa"

    @property
    def priority(self) -> int:
        return 30

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.sankalpa is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        rotations = ctx.heartbeat_count // 4
        idle_minutes = rotations * 15
        intents = ctx.sankalpa.think(idle_minutes=idle_minutes)
        for intent in intents:
            operations.append(f"sankalpa_intent:{intent.title}")
            logger.info("KARMA: Sankalpa intent — %s (idle=%dmin)", intent.title, idle_minutes)

        # Process issue/exec missions
        all_specs = getattr(ctx, "_all_specs", {})
        all_inventories = getattr(ctx, "_all_inventories", {})
        _process_issue_missions(ctx, operations, all_specs, all_inventories)


def _process_issue_missions(
    ctx: PhaseContext,
    operations: list[str],
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]] | None = None,
) -> None:
    """Process Sankalpa missions created from GitHub Issues and federation directives."""
    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
    except Exception:
        return

    from city.mission_router import authorize_mission

    try:
        active = ctx.sankalpa.registry.get_active_missions()
    except Exception:
        return

    for mission in active:
        if mission.id.startswith("exec_"):
            if not authorize_mission(mission.id, all_specs, ctx.active_agents, all_inventories):
                logger.info(
                    "KARMA: No agent with execute capability"
                    " — executor handles exec mission %s as system service",
                    mission.id,
                )
            success = _execute_code_mission(ctx, mission)
            operations.append(f"exec_mission:{mission.id}:{'success' if success else 'pending'}")
            if success:
                mission.status = MissionStatus.COMPLETED
                ctx.sankalpa.registry.add_mission(mission)
                emit_event(
                    "ACTION", "karma", f"Mission completed: {mission.name}",
                    {
                        "action": "mission_completed",
                        "mission_id": mission.id,
                        "mission_name": mission.name,
                        "owner": getattr(mission, "owner", ""),
                    },
                )
            _learn(ctx, mission.id, "exec_mission", success=success)
            logger.info(
                "KARMA: Exec mission %s — %s",
                mission.id, "completed" if success else "pending",
            )
            continue

        if not mission.id.startswith("issue_"):
            continue

        if not authorize_mission(mission.id, all_specs, ctx.active_agents, all_inventories):
            operations.append(f"issue_blocked:{mission.id}:capability_gate")
            logger.info(
                "KARMA: Issue mission %s blocked — no agent with execute capability",
                mission.id,
            )
            continue

        parts = mission.id.split("_")
        if len(parts) < 2:
            continue
        try:
            issue_number = int(parts[1])
        except ValueError:
            continue

        if mission.name.startswith("IssueAudit"):
            success = _execute_issue_audit(ctx, issue_number)
        else:
            success = _execute_issue_heal(ctx, issue_number)

        operations.append(f"issue_mission:{mission.id}:{'success' if success else 'pending'}")

        if success:
            mission.status = MissionStatus.COMPLETED
            ctx.sankalpa.registry.add_mission(mission)
            emit_event(
                "ACTION",
                "karma",
                f"Issue mission completed: #{issue_number}",
                {
                    "action": "mission_completed",
                    "mission_id": mission.id,
                    "issue_number": issue_number,
                    "owner": getattr(mission, "owner", ""),
                },
            )
            if ctx.issues is not None:
                ctx.issues.resolve_issue(issue_number, mission.id)

        _learn(ctx, f"issue_{issue_number}", "issue_mission", success=success)
        logger.info(
            "KARMA: Issue mission %s — %s",
            mission.id, "completed" if success else "pending",
        )


def _execute_issue_audit(ctx: PhaseContext, issue_number: int) -> bool:
    if ctx.audit is None:
        return False
    try:
        ctx.audit.run_all()
        logger.info("KARMA: Issue #%d audit executed", issue_number)
        return True
    except Exception as e:
        logger.warning("KARMA: Issue #%d audit failed: %s", issue_number, e)
        return False


def _execute_issue_heal(ctx: PhaseContext, issue_number: int) -> bool:
    """Execute a heal-needed issue mission via immune system → executor escalation."""
    if ctx.immune is not None:
        diagnosis = ctx.immune.diagnose(f"issue_low_prana:{issue_number}")
        if diagnosis.healable:
            result = ctx.immune.heal(diagnosis)
            if result.success:
                logger.info("KARMA: Issue #%d healed by immune system", issue_number)
                return True

    if ctx.executor is not None:
        fix = ctx.executor.execute_heal("ruff_clean", [f"issue_{issue_number}"])
        if fix.success and fix.files_changed:
            pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
            if pr is not None and pr.success:
                _record_pr_event(ctx, issue_number, pr)
                logger.info("KARMA: Issue #%d → PR created: %s", issue_number, pr.pr_url)
                return True
            if fix.success:
                logger.info("KARMA: Issue #%d fixed (no PR needed)", issue_number)
                return True

    return False


def _execute_code_mission(ctx: PhaseContext, mission: object) -> bool:
    if ctx.executor is None:
        return False

    contract = "ruff_clean"
    if mission.name.startswith("Execute: "):
        contract = mission.name[len("Execute: "):]

    try:
        fix = ctx.executor.execute_heal(contract, [f"mission_{mission.id}"])
        if fix.success and fix.files_changed:
            pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
            if pr is not None and pr.success:
                _record_pr_event(ctx, 0, pr)
                logger.info("KARMA: Exec mission %s → PR created: %s", mission.id, pr.pr_url)
                return True
            if fix.success:
                logger.info("KARMA: Exec mission %s fixed (no PR needed)", mission.id)
                return True
    except Exception as e:
        logger.warning("KARMA: Exec mission %s failed: %s", mission.id, e)
    return False


def _record_pr_event(ctx: PhaseContext, issue_number: int, pr: object) -> None:
    ctx.recent_events.append({
        "type": "pr_created",
        "issue_number": issue_number,
        "pr_url": pr.pr_url,
        "branch": pr.branch,
        "commit_hash": pr.commit_hash,
        "heartbeat": ctx.heartbeat_count,
    })
