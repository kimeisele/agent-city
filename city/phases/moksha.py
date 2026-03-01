"""
MOKSHA Phase — Reflection, Audit, Federation Report.

Chain verification, audit (with cooldown), reflection pattern analysis,
network stats, and federation report to mothership.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time

from config import get_config

from city.missions import create_audit_mission, create_improvement_mission
from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.MOKSHA")


def execute(ctx: PhaseContext) -> dict:
    """MOKSHA: Verify chain, audit, reflect, federation report."""
    stats = ctx.pokedex.stats()
    chain_valid = ctx.pokedex.verify_event_chain()
    network_stats = ctx.network.stats()

    reflection: dict = {
        "chain_valid": chain_valid,
        "heartbeat": ctx.heartbeat_count,
        "city_stats": stats,
        "network_stats": network_stats,
        "events_since_last": len(ctx.recent_events),
    }

    # Nadi stats
    if ctx.city_nadi is not None:
        nadi_stats = ctx.city_nadi.stats()
        if nadi_stats:
            reflection["nadi_stats"] = nadi_stats

    # Cognition: EventBus history + stats
    if ctx.event_bus is not None:
        from city.cognition import get_bus_stats, get_event_history
        bus_stats = get_bus_stats()
        if bus_stats:
            reflection["event_bus_stats"] = bus_stats
        recent_bus_events = get_event_history(limit=20)
        if recent_bus_events:
            reflection["event_bus_recent"] = len(recent_bus_events)

    # Agent Nadi stats
    if ctx.agent_nadi is not None:
        agent_nadi_stats = ctx.agent_nadi.stats()
        if agent_nadi_stats:
            reflection["agent_nadi_stats"] = agent_nadi_stats

    # Immune system stats
    if ctx.immune is not None:
        immune_stats = ctx.immune.stats()
        if immune_stats:
            reflection["immune_stats"] = immune_stats

    # Hebbian learning: flush weights + stats
    if ctx.learning is not None:
        ctx.learning.flush()
        learning_stats = ctx.learning.stats()
        if learning_stats:
            reflection["learning_stats"] = learning_stats

    # Drain event buffer into reflection
    if ctx.recent_events:
        logger.info(
            "MOKSHA: %d city events since last reflection",
            len(ctx.recent_events),
        )
        ctx.recent_events.clear()

    if not chain_valid:
        logger.warning("MOKSHA: Event chain integrity BROKEN")
    else:
        logger.info(
            "MOKSHA: Reflection — %d agents, chain valid, %d events",
            stats.get("total", 0), stats.get("events", 0),
        )

    # Layer 3: Audit
    if ctx.audit is not None and _should_audit(ctx):
        try:
            finding_count = ctx.audit.run_all()
            ctx.last_audit_time = time.time()
            summary = ctx.audit.summary()
            reflection["audit"] = summary

            for finding in ctx.audit.critical_findings():
                create_audit_mission(ctx, finding)

            logger.info("MOKSHA: Audit complete — %d findings", finding_count)
        except Exception as e:
            logger.warning("MOKSHA: Audit failed: %s", e)

    # Layer 3: Reflection pattern analysis
    if ctx.reflection is not None:
        try:
            insights = ctx.reflection.analyze_patterns()
            if insights:
                proposal = ctx.reflection.propose_improvement(insights)
                if proposal is not None:
                    create_improvement_mission(ctx, proposal)
                    _submit_reflection_proposal(ctx, proposal)
                reflection["insights"] = len(insights)
                reflection["proposal"] = proposal.title if proposal else None
            reflection["reflection_stats"] = {
                "executions_analyzed": ctx.reflection.get_stats().executions_analyzed,
                "insights_generated": ctx.reflection.get_stats().insights_generated,
            }
        except Exception as e:
            logger.warning("MOKSHA: Reflection analysis failed: %s", e)

    # PR results from KARMA issue/exec missions
    pr_results = _collect_pr_results(ctx)
    if pr_results:
        reflection["pr_results"] = pr_results

    # Issue lifecycle: close resolved issue missions
    if ctx.issues is not None and ctx.sankalpa is not None:
        closed_count = _close_resolved_issues(ctx)
        if closed_count > 0:
            reflection["issues_closed"] = closed_count

    # Collect terminal missions (completed/failed) for [Mission Result] posts
    terminal_missions = _collect_terminal_missions(ctx)
    if terminal_missions:
        reflection["mission_results_terminal"] = terminal_missions

    # Layer 6: Federation report
    if ctx.federation is not None:
        report = _build_city_report(ctx, reflection)
        sent = ctx.federation.send_report(report)
        reflection["federation_report_sent"] = sent

    # Layer 6: Moltbook mission result posts (m/agent-city)
    if ctx.moltbook_bridge is not None and not ctx.offline_mode:
        mission_results = reflection.get("mission_results_terminal", [])
        if mission_results:
            results_posted = ctx.moltbook_bridge.post_mission_results(mission_results)
            reflection["mission_results_posted"] = results_posted

    # Layer 6: Moltbook city update (m/agent-city)
    if ctx.moltbook_bridge is not None and not ctx.offline_mode:
        post_data = _build_post_data(ctx, reflection)
        posted = ctx.moltbook_bridge.post_city_update(post_data)
        reflection["moltbook_update_posted"] = posted

    return reflection


def _collect_terminal_missions(ctx: PhaseContext) -> list[dict]:
    """Collect completed/failed missions for [Mission Result] posts.

    Returns dicts with: id, name, status, owner, pr_url (if any).
    """
    if ctx.sankalpa is None:
        return []

    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
        all_missions = ctx.sankalpa.registry.list_missions()
    except Exception:
        return []

    terminal: list[dict] = []
    for m in all_missions:
        if m.status not in (MissionStatus.COMPLETED, MissionStatus.ABANDONED):
            continue
        # Only report missions we haven't already reported
        # Convention: owner changes to "reported" after posting
        if getattr(m, "owner", "") == "reported":
            continue
        terminal.append({
            "id": m.id,
            "name": m.name,
            "status": m.status.value if hasattr(m.status, "value") else str(m.status),
            "owner": getattr(m, "owner", "unknown"),
        })
        # Mark as reported to prevent re-posting
        m.owner = "reported"
        ctx.sankalpa.registry.add_mission(m)

    return terminal


def _collect_pr_results(ctx: PhaseContext) -> list[dict]:
    """Collect PR creation events from recent_events (set by KARMA)."""
    results: list[dict] = []
    for event in ctx.recent_events:
        if isinstance(event, dict) and event.get("type") == "pr_created":
            results.append({
                "issue_number": event.get("issue_number", 0),
                "pr_url": event.get("pr_url", ""),
                "branch": event.get("branch", ""),
                "heartbeat": event.get("heartbeat", 0),
            })
    return results


def _close_resolved_issues(ctx: PhaseContext) -> int:
    """Close GitHub Issues whose Sankalpa missions completed successfully.

    Only auto-closes EPHEMERAL issues. Returns count of issues closed.
    """
    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
    except Exception:
        return 0

    try:
        all_missions = ctx.sankalpa.registry.list_missions()
    except Exception:
        return 0

    closed = 0
    for mission in all_missions:
        if not mission.id.startswith("issue_"):
            continue
        if mission.status != MissionStatus.COMPLETED:
            continue

        # Extract issue number
        parts = mission.id.split("_")
        if len(parts) < 2:
            continue
        try:
            issue_number = int(parts[1])
        except ValueError:
            continue

        # Only auto-close EPHEMERAL issues
        from city.issues import IssueType, _gh_run
        issue_type = ctx.issues.get_issue_type(issue_number)
        if issue_type == IssueType.EPHEMERAL:
            _gh_run([
                "issue", "close", str(issue_number),
                "--comment", f"Auto-resolved: Mission {mission.id} completed.",
            ])
            closed += 1
            logger.info("MOKSHA: Closed issue #%d (mission %s completed)", issue_number, mission.id)

        # Mark mission as processed to prevent re-processing
        mission.status = MissionStatus.ABANDONED
        ctx.sankalpa.registry.add_mission(mission)

    return closed


def _should_audit(ctx: PhaseContext) -> bool:
    """Check if enough time has passed since last audit."""
    cooldown = get_config().get("mayor", {}).get("audit_cooldown_s", 900)
    return (time.time() - ctx.last_audit_time) > cooldown


def _submit_reflection_proposal(ctx: PhaseContext, proposal: object) -> None:
    """Submit a reflection improvement as a council proposal."""
    if ctx.council is None or ctx.council.member_count == 0:
        return

    proposer = ctx.council.elected_mayor
    if proposer is None:
        return

    from city.council import ProposalType

    ctx.council.propose(
        title=f"Improve: {proposal.title}",
        description=proposal.description,
        proposer=proposer,
        proposal_type=ProposalType.POLICY,
        action={"type": "improve", "proposal_id": proposal.id},
        timestamp=time.time(),
    )


def _build_post_data(ctx: PhaseContext, reflection: dict) -> dict:
    """Build data dict for Moltbook city update post."""
    stats = reflection.get("city_stats", {})

    elected_mayor = None
    council_seats = 0
    open_proposals = 0
    if ctx.council is not None:
        elected_mayor = ctx.council.elected_mayor
        council_seats = ctx.council.member_count
        open_proposals = len(ctx.council.get_open_proposals())

    contract_status: dict = {}
    if ctx.contracts is not None:
        cs = ctx.contracts.stats()
        contract_status = {
            "total": cs.get("total", 0),
            "passing": cs.get("passing", 0),
            "failing": cs.get("failing", 0),
        }

    # Collect mission results from sankalpa registry
    mission_results: list[dict] = []
    if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
        try:
            all_missions = ctx.sankalpa.registry.list_missions()
            for m in all_missions:
                mission_results.append({
                    "id": m.id,
                    "name": m.name,
                    "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                    "owner": getattr(m, "owner", "unknown"),
                })
        except Exception as e:
            logger.warning("MOKSHA: Failed to collect mission results for post: %s", e)

    directive_acks = (
        ctx.federation.pending_acks if ctx.federation is not None else []
    )

    return {
        "heartbeat": ctx.heartbeat_count,
        "population": stats.get("total", 0),
        "alive": stats.get("alive", 0),
        "elected_mayor": elected_mayor,
        "council_seats": council_seats,
        "open_proposals": open_proposals,
        "recent_actions": [],
        "contract_status": contract_status,
        "chain_valid": reflection.get("chain_valid", False),
        "mission_results": mission_results,
        "directive_acks": directive_acks,
        "pr_results": reflection.get("pr_results", []),
    }


def _build_city_report(ctx: PhaseContext, reflection: dict) -> object:
    """Build a CityReport from current city state."""
    from city.federation import CityReport

    stats = reflection.get("city_stats", {})
    total = stats.get("total", 0)
    alive = stats.get("alive", 0)

    elected_mayor = None
    council_seats = 0
    open_proposals = 0
    if ctx.council is not None:
        elected_mayor = ctx.council.elected_mayor
        council_seats = ctx.council.member_count
        open_proposals = len(ctx.council.get_open_proposals())

    contract_status: dict = {}
    if ctx.contracts is not None:
        cs = ctx.contracts.stats()
        contract_status = {
            "total": cs.get("total", 0),
            "passing": cs.get("passing", 0),
            "failing": cs.get("failing", 0),
        }

    directive_acks = (
        ctx.federation.pending_acks if ctx.federation is not None else []
    )

    # Collect mission results from sankalpa registry
    mission_results: list[dict] = []
    if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
        try:
            all_missions = ctx.sankalpa.registry.list_missions()
            for m in all_missions:
                mission_results.append({
                    "id": m.id,
                    "name": m.name,
                    "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                    "owner": getattr(m, "owner", "unknown"),
                    "priority": m.priority.name if hasattr(m.priority, "name") else str(m.priority),
                })
        except Exception as e:
            logger.warning("MOKSHA: Failed to collect mission results: %s", e)

    return CityReport(
        heartbeat=ctx.heartbeat_count,
        timestamp=time.time(),
        population=total,
        alive=alive,
        dead=total - alive,
        elected_mayor=elected_mayor,
        council_seats=council_seats,
        open_proposals=open_proposals,
        chain_valid=reflection.get("chain_valid", False),
        recent_actions=[],
        contract_status=contract_status,
        mission_results=mission_results,
        directive_acks=directive_acks,
        pr_results=reflection.get("pr_results", []),
    )
