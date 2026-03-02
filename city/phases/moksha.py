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

    # Hebbian learning: decay → trim → flush weights + stats
    if ctx.learning is not None:
        autonomy_cfg = get_config().get("autonomy", {})
        decay_factor = autonomy_cfg.get("decay_factor", 0.01)
        max_entries = autonomy_cfg.get("max_synapse_entries", 500)

        decayed = ctx.learning.decay(decay_factor)
        trimmed = ctx.learning.trim(max_entries)
        ctx.learning.flush()

        learning_stats = ctx.learning.stats()
        if learning_stats:
            learning_stats["decayed"] = decayed
            learning_stats["trimmed"] = trimmed
            reflection["learning_stats"] = learning_stats

    # Daemon metrics (if running in daemon mode)
    from city.registry import SVC_DAEMON

    daemon = ctx.registry.get(SVC_DAEMON)
    if daemon is not None:
        reflection["daemon_stats"] = daemon.stats()

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
            stats.get("total", 0),
            stats.get("events", 0),
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

                # Bridge: Reflection insights → Hebbian synapses
                if ctx.learning is not None:
                    for insight in insights:
                        insight_type = getattr(insight, "type", "")
                        insight_msg = getattr(insight, "message", "")[:40]
                        if insight_type == "failure_pattern":
                            ctx.learning.record_outcome(
                                f"pattern:{insight_msg}",
                                "repeat",
                                success=False,
                            )
                        elif insight_type == "performance":
                            ctx.learning.record_outcome(
                                f"pattern:{insight_msg}",
                                "optimize",
                                success=True,
                            )
                    reflection["synapse_bridge_updates"] = len(insights)

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

    # PR Lifecycle: check CI status, auto-merge, close stale
    from city.registry import SVC_PR_LIFECYCLE

    pr_mgr = ctx.registry.get(SVC_PR_LIFECYCLE)
    if pr_mgr is not None:
        pr_changes = pr_mgr.check_all(ctx.heartbeat_count)
        if pr_changes:
            reflection["pr_lifecycle_changes"] = pr_changes
        pr_stats = pr_mgr.stats()
        if pr_stats.get("total_tracked", 0) > 0:
            reflection["pr_lifecycle_stats"] = pr_stats

    # Spawner stats
    from city.registry import SVC_SPAWNER

    spawner = ctx.registry.get(SVC_SPAWNER)
    if spawner is not None:
        reflection["spawner_stats"] = spawner.stats()

    # CartridgeFactory stats
    from city.registry import SVC_CARTRIDGE_FACTORY

    cart_factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
    if cart_factory is not None:
        reflection["cartridge_factory_stats"] = cart_factory.stats()

    # CityBuilder: update cell snapshots + census
    from city.registry import SVC_CITY_BUILDER

    city_builder = ctx.registry.get(SVC_CITY_BUILDER)
    if city_builder is not None:
        for agent in ctx.pokedex.list_citizens():
            city_builder.update_cell(agent["name"])
        reflection["city_census"] = city_builder.census()

    # Issue lifecycle: close resolved issue missions
    if ctx.issues is not None and ctx.sankalpa is not None:
        closed_count = _close_resolved_issues(ctx)
        if closed_count > 0:
            reflection["issues_closed"] = closed_count

    # Mission hygiene: purge stale duplicates
    if ctx.sankalpa is not None:
        purged = _purge_stale_missions(ctx)
        if purged > 0:
            reflection["missions_purged"] = purged

    # Collect terminal missions (completed/failed) for [Mission Result] posts
    terminal_missions = _collect_terminal_missions(ctx)
    if terminal_missions:
        reflection["mission_results_terminal"] = terminal_missions

        # Mint rewards for completed missions (Phase 6)
        mint_results = _mint_mission_rewards(ctx, terminal_missions)
        if mint_results:
            reflection["assets_minted"] = mint_results

    # Marketplace stats (Phase 7)
    mkt_stats = ctx.pokedex.marketplace_stats()
    if mkt_stats.get("active_orders", 0) > 0 or mkt_stats.get("total_filled", 0) > 0:
        reflection["marketplace"] = mkt_stats

    # Governance stats (Phase 8)
    if ctx.council is not None:
        gov_stats = {
            "council_members": ctx.council.member_count,
            "elected_mayor": ctx.council.elected_mayor,
            "open_proposals": len(ctx.council.get_open_proposals()),
            "market_frozen": ctx.council.is_market_frozen,
            "effective_commission": ctx.council.effective_commission,
        }
        reflection["governance"] = gov_stats

    # Evaluate dormant agents for treasury-funded revival
    revival_results = _evaluate_dormant_revival(ctx)
    if revival_results:
        reflection["revival"] = revival_results

    # Brain reflection on cycle (1 optional call per MOKSHA)
    brain = ctx.brain
    if brain is not None and hasattr(brain, "reflect_on_cycle"):
        from city.brain_context import (
            build_context_snapshot,
            diff_snapshots,
            load_before_snapshot,
        )

        snapshot = build_context_snapshot(ctx)
        # Fix #1: Load before_snapshot from disk for outcome diffing
        before_snapshot = load_before_snapshot(ctx.state_path.parent)
        if before_snapshot is not None:
            outcome_diff = diff_snapshots(before_snapshot, snapshot)
            reflection["outcome_diff"] = outcome_diff
        cycle_thought = brain.reflect_on_cycle(
            snapshot, reflection, memory=ctx.brain_memory,
        )
        if cycle_thought is not None:
            reflection["brain_reflection"] = cycle_thought.to_dict()
            if ctx.brain_memory is not None:
                ctx.brain_memory.record(cycle_thought, ctx.heartbeat_count)
            # High-confidence improvements → Sankalpa mission
            if (
                cycle_thought.action_hint.startswith("create_mission:")
                and cycle_thought.confidence >= 0.7
                and ctx.sankalpa is not None
            ):
                mission_desc = cycle_thought.action_hint[len("create_mission:"):]
                proposal = type("BrainProposal", (), {
                    "id": f"brain_{ctx.heartbeat_count}",
                    "title": mission_desc[:60] or "Brain improvement",
                    "description": cycle_thought.comprehension,
                })()
                create_improvement_mission(ctx, proposal)

    # Flush brain memory to disk
    if ctx.brain_memory is not None:
        ctx.brain_memory.flush()

    # Layer 6: Federation Nadi — emit city state + flush outbox
    if ctx.federation_nadi is not None:
        nadi_payload = {
            "heartbeat": ctx.heartbeat_count,
            "population": stats.get("total", 0),
            "alive": stats.get("active", 0) + stats.get("citizen", 0),
            "chain_valid": chain_valid,
            "pr_results": reflection.get("pr_results", []),
            "mission_results": reflection.get("mission_results_terminal", []),
        }
        ctx.federation_nadi.emit(
            source="moksha",
            operation="city_report",
            payload=nadi_payload,
            priority=2,  # SATTVA
        )
        flushed = ctx.federation_nadi.flush()
        if flushed:
            reflection["federation_nadi_flushed"] = flushed

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

    # Moltbook Assistant: reflect on engagement metrics
    if ctx.moltbook_assistant is not None:
        reflection["moltbook_assistant"] = ctx.moltbook_assistant.on_moksha()

    # GitHub Discussions: post city report + cross-post mission results + pulse
    if ctx.discussions is not None and not ctx.offline_mode:
        report_posted = ctx.discussions.post_city_report(
            ctx.heartbeat_count,
            reflection,
        )
        reflection["discussions_report_posted"] = report_posted

        mission_results = reflection.get("mission_results_terminal", [])
        if mission_results:
            crossposted = ctx.discussions.cross_post_mission_results(mission_results)
            reflection["discussions_crossposted"] = crossposted

        # Delta-gated pulse: only fire when something happened this rotation
        delta = _count_rotation_delta(reflection)
        if delta > 0:
            pulse_stats = reflection.get("city_stats", {})
            pulsed = ctx.discussions.post_pulse(ctx.heartbeat_count, pulse_stats)
            reflection["discussions_pulse_posted"] = pulsed
            reflection["discussions_pulse_delta"] = delta

    if ctx.discussions is not None:
        reflection["discussions"] = ctx.discussions.stats()

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
        terminal.append(
            {
                "id": m.id,
                "name": m.name,
                "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                "owner": getattr(m, "owner", "unknown"),
            }
        )
        # Mark as reported to prevent re-posting
        m.owner = "reported"
        ctx.sankalpa.registry.add_mission(m)

    return terminal


def _collect_pr_results(ctx: PhaseContext) -> list[dict]:
    """Collect PR creation events from recent_events (set by KARMA)."""
    results: list[dict] = []
    for event in ctx.recent_events:
        if isinstance(event, dict) and event.get("type") == "pr_created":
            results.append(
                {
                    "issue_number": event.get("issue_number", 0),
                    "pr_url": event.get("pr_url", ""),
                    "branch": event.get("branch", ""),
                    "heartbeat": event.get("heartbeat", 0),
                }
            )
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
            _gh_run(
                [
                    "issue",
                    "close",
                    str(issue_number),
                    "--comment",
                    f"Auto-resolved: Mission {mission.id} completed.",
                ]
            )
            closed += 1
            logger.info("MOKSHA: Closed issue #%d (mission %s completed)", issue_number, mission.id)

        # Mark mission as processed to prevent re-processing
        mission.status = MissionStatus.ABANDONED
        ctx.sankalpa.registry.add_mission(mission)

    return closed


def _purge_stale_missions(ctx: PhaseContext) -> int:
    """Purge duplicate missions — keep only the latest per contract/source.

    Prevents mission spiral: same failing contract creating new mission every heartbeat.
    For each unique mission name, keep the one with highest heartbeat suffix, abandon rest.
    """
    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
    except Exception:
        return 0

    try:
        all_missions = ctx.sankalpa.registry.list_missions()
    except Exception:
        return 0

    # Group active missions by name
    by_name: dict[str, list] = {}
    for m in all_missions:
        if m.status != MissionStatus.ACTIVE:
            continue
        by_name.setdefault(m.name, []).append(m)

    purged = 0
    for name, missions in by_name.items():
        if len(missions) <= 1:
            continue

        # Sort by ID suffix (heartbeat number) — keep highest
        def _heartbeat_suffix(m):
            parts = m.id.rsplit("_", 1)
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                return 0

        missions.sort(key=_heartbeat_suffix, reverse=True)
        # Keep first (newest), abandon rest
        for m in missions[1:]:
            m.status = MissionStatus.ABANDONED
            ctx.sankalpa.registry.add_mission(m)
            purged += 1

    if purged:
        logger.info("MOKSHA: Purged %d stale duplicate missions", purged)
    return purged


def _count_rotation_delta(reflection: dict) -> int:
    """Count real events in this MURALI rotation. 0 = nothing happened."""
    delta = 0
    # Completed missions
    delta += len(reflection.get("mission_results_terminal", []))
    # Heal events
    immune = reflection.get("immune_stats", {})
    delta += immune.get("heals_attempted", 0)
    # New agents spawned
    spawner = reflection.get("spawner_stats", {})
    delta += spawner.get("spawned_this_cycle", 0)
    # Governance actions
    delta += len(reflection.get("council_executed", []))
    return delta


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
        heartbeat=ctx.heartbeat_count,
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
                mission_results.append(
                    {
                        "id": m.id,
                        "name": m.name,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                        "owner": getattr(m, "owner", "unknown"),
                    }
                )
        except Exception as e:
            logger.warning("MOKSHA: Failed to collect mission results for post: %s", e)

    directive_acks = ctx.federation.pending_acks if ctx.federation is not None else []

    return {
        "heartbeat": ctx.heartbeat_count,
        "population": stats.get("total", 0),
        "alive": stats.get("active", 0) + stats.get("citizen", 0),
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
    alive = stats.get("active", 0) + stats.get("citizen", 0)

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

    directive_acks = ctx.federation.pending_acks if ctx.federation is not None else []

    # Collect mission results from sankalpa registry
    mission_results: list[dict] = []
    if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
        try:
            all_missions = ctx.sankalpa.registry.list_missions()
            for m in all_missions:
                mission_results.append(
                    {
                        "id": m.id,
                        "name": m.name,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                        "owner": getattr(m, "owner", "unknown"),
                        "priority": m.priority.name
                        if hasattr(m.priority, "name")
                        else str(m.priority),
                    }
                )
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


def _evaluate_dormant_revival(ctx: PhaseContext) -> dict | None:
    """Evaluate dormant agents for treasury-funded revival.

    Runs during MOKSHA (reflection phase).  Selects frozen agents who lived
    long enough to have proven value (cell_cycle > threshold) and revives
    them with a REVIVE_DOSE funded from the zone treasury.

    Rate-limited: at most 1 revive per MOKSHA cycle to prevent treasury drain.
    """
    from city.seed_constants import REVIVE_COOLDOWN_CYCLES, REVIVE_DOSE

    dormant = ctx.pokedex.list_dormant()
    if not dormant:
        return None

    # Eligibility: agent must have lived at least REVIVE_COOLDOWN_CYCLES
    # heartbeats before going dormant (proof of prior value)
    eligible = [
        d
        for d in dormant
        if d["cell_cycle"] >= REVIVE_COOLDOWN_CYCLES and d["prana_class"] != "immortal"
    ]

    if not eligible:
        return {"dormant_count": len(dormant), "eligible": 0, "revived": []}

    # Sort by cell_cycle descending — most experienced agents first
    eligible.sort(key=lambda d: d["cell_cycle"], reverse=True)

    # Revive at most 1 per MOKSHA cycle (treasury protection)
    revived: list[str] = []
    candidate = eligible[0]

    # Determine which zone treasury funds the revival
    agent_data = ctx.pokedex.get(candidate["name"])
    zone = "discovery"  # fallback
    if agent_data and agent_data.get("zone"):
        zone = agent_data["zone"]

    from city.pokedex import ZONE_TREASURIES

    treasury_account = ZONE_TREASURIES.get(zone, "ZONE_DISCOVERY")

    try:
        ctx.pokedex.revive(
            candidate["name"],
            prana_dose=REVIVE_DOSE,
            sponsor=treasury_account,
            reason=f"revive:moksha_auto:cycle_{ctx.heartbeat_count}",
        )
        revived.append(candidate["name"])
        logger.info(
            "MOKSHA: Revived %s (cycle=%d, zone=%s, dose=%d)",
            candidate["name"],
            candidate["cell_cycle"],
            zone,
            REVIVE_DOSE,
        )
    except Exception as e:
        logger.warning("MOKSHA: Failed to revive %s: %s", candidate["name"], e)

    return {
        "dormant_count": len(dormant),
        "eligible": len(eligible),
        "revived": revived,
    }


def _mint_mission_rewards(ctx: PhaseContext, terminal_missions: list[dict]) -> list[dict]:
    """Mint semantic assets as rewards for completed missions.

    Each completed mission → MISSION_REWARD_TOKENS (1) capability_token
    for the mission's owner agent. The token matches the mission type
    (exec_ → execute, heal_ → validate, etc.).
    """
    from city.seed_constants import MISSION_REWARD_TOKENS

    _REWARD_CAP: dict[str, str] = {
        "heal_": "validate",
        "audit_": "audit",
        "improve_": "propose",
        "issue_": "execute",
        "exec_": "execute",
        "signal_": "observe",
        "fed_": "relay",
    }

    minted: list[dict] = []
    for mission in terminal_missions:
        if mission["status"] != "completed":
            continue

        owner = mission.get("owner", "")
        if not owner or owner in ("reported", "unknown"):
            continue

        # Determine reward type from mission prefix
        mission_id = mission["id"]
        reward_cap = "propose"  # default
        for prefix, cap in _REWARD_CAP.items():
            if mission_id.startswith(prefix):
                reward_cap = cap
                break

        try:
            ctx.pokedex.grant_asset(
                owner,
                "capability_token",
                reward_cap,
                quantity=MISSION_REWARD_TOKENS,
                source="mission_reward",
            )
            minted.append({"agent": owner, "asset": reward_cap, "mission": mission_id})
            logger.info(
                "MOKSHA: Minted %s token for %s (mission %s)",
                reward_cap,
                owner,
                mission_id,
            )
        except Exception as e:
            logger.warning("MOKSHA: Failed to mint reward for %s: %s", owner, e)

    return minted
