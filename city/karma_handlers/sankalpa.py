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
    from city.registry import SVC_ROUTER

    router = ctx.registry.get(SVC_ROUTER) if ctx.registry else None

    try:
        active = ctx.sankalpa.registry.get_active_missions()
    except Exception:
        return

    for mission in active:
        if mission.id.startswith("exec_"):
            if not authorize_mission(mission.id, all_specs, ctx.active_agents, all_inventories, router=router):
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

        if not authorize_mission(mission.id, all_specs, ctx.active_agents, all_inventories, router=router):
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

    # 7C-1: Route mission to best agent and run Cartridge process()
    all_specs = getattr(ctx, "_all_specs", {})
    all_inventories = getattr(ctx, "_all_inventories", {})
    agent_name = None
    cartridge_result = None

    if all_specs:
        from city.mission_router import route_mission
        routing = route_mission(mission, all_specs, ctx.active_agents, all_inventories)
        if routing["agent_name"] is not None:
            agent_name = routing["agent_name"]
            # Call Cartridge process() for agent-specific cognition
            try:
                from city.registry import SVC_CARTRIDGE_FACTORY
                factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
                if factory is not None:
                    cartridge = factory.get(agent_name)
                    if cartridge is not None and hasattr(cartridge, "process"):
                        task_desc = getattr(mission, "description", getattr(mission, "name", str(mission)))
                        cartridge_result = cartridge.process(task_desc)
                        logger.info(
                            "KARMA: Agent %s processed mission %s (status=%s)",
                            agent_name, mission.id,
                            cartridge_result.get("status", "?") if isinstance(cartridge_result, dict) else "?",
                        )
            except Exception as e:
                logger.debug("Cartridge process() skipped for %s: %s", agent_name, e)

    contract = "ruff_clean"
    if mission.name.startswith("Execute: "):
        contract = mission.name[len("Execute: "):]

    try:
        details = [f"mission_{mission.id}"]
        if agent_name:
            details.append(f"agent:{agent_name}")
        if cartridge_result and isinstance(cartridge_result, dict):
            fn = cartridge_result.get("function", "")
            if fn:
                details.append(f"cognitive_function:{fn}")

        fix = ctx.executor.execute_heal(contract, details)
        if fix.success and fix.files_changed:
            pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count, agent_name=agent_name)
            if pr is not None and pr.success:
                _record_pr_event(ctx, 0, pr, agent_name=agent_name)
                logger.info(
                    "KARMA: Exec mission %s → PR created by %s: %s",
                    mission.id, agent_name or "mayor", pr.pr_url,
                )
                # 7B-3: Cross-post agent PR to Moltbook
                if agent_name and ctx.moltbook_bridge is not None:
                    try:
                        ctx.moltbook_bridge.post_agent_update(
                            agent_name=agent_name,
                            action=f"created PR for {fix.contract_name}",
                            detail=fix.message or "",
                            pr_url=pr.pr_url or "",
                        )
                    except Exception:
                        pass
                return True
            if fix.success:
                logger.info("KARMA: Exec mission %s fixed (no PR needed)", mission.id)
                return True
    except Exception as e:
        logger.warning("KARMA: Exec mission %s failed: %s", mission.id, e)
    return False


def _record_pr_event(
    ctx: PhaseContext,
    issue_number: int,
    pr: object,
    agent_name: str | None = None,
) -> None:
    ctx.recent_events.append({
        "type": "pr_created",
        "issue_number": issue_number,
        "pr_url": pr.pr_url,
        "branch": pr.branch,
        "commit_hash": pr.commit_hash,
        "heartbeat": ctx.heartbeat_count,
        "agent_name": agent_name or "mayor",
    })
