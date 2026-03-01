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

    # Cognition: EventBus history + stats
    if ctx.event_bus is not None:
        from city.cognition import get_bus_stats, get_event_history
        bus_stats = get_bus_stats()
        if bus_stats:
            reflection["event_bus_stats"] = bus_stats
        recent_bus_events = get_event_history(limit=20)
        if recent_bus_events:
            reflection["event_bus_recent"] = len(recent_bus_events)

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

    # Layer 6: Federation report
    if ctx.federation is not None:
        report = _build_city_report(ctx, reflection)
        sent = ctx.federation.send_report(report)
        reflection["federation_report_sent"] = sent

    # Layer 6: Moltbook city update (m/agent-city)
    if ctx.moltbook_bridge is not None and not ctx.offline_mode:
        post_data = _build_post_data(ctx, reflection)
        posted = ctx.moltbook_bridge.post_city_update(post_data)
        reflection["moltbook_update_posted"] = posted

    return reflection


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
        mission_results=[],
        directive_acks=directive_acks,
    )
