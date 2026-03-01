"""
DHARMA Phase — Governance, Elections, Contracts, Issue Lifecycle.

Cell homeostasis, zone health, council elections, quality contracts,
and issue lifecycle processing.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time

from city.missions import create_healing_mission, create_issue_mission
from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.DHARMA")


def execute(ctx: PhaseContext) -> list[str]:
    """DHARMA: Cell homeostasis, governance, contracts, issues."""
    actions: list[str] = []

    # Metabolize all living agents
    dead = ctx.pokedex.metabolize_all(active_agents=ctx.active_agents)
    for name in dead:
        actions.append(f"archived:{name}:prana_exhaustion")
        logger.info("DHARMA: Agent %s archived (prana exhaustion)", name)

    # Immune scan: diagnose why agents died
    if ctx.immune is not None and dead:
        for name in dead:
            diagnosis = ctx.immune.diagnose(f"agent_death:{name}:prana_exhaustion")
            if diagnosis.healable:
                result = ctx.immune.heal(diagnosis)
                if result.success:
                    actions.append(f"immune_healed:{name}:{diagnosis.rule_id}")

    # Clear active set for next cycle
    ctx.active_agents.clear()

    # Zone health check
    stats = ctx.pokedex.stats()
    zones = stats.get("zones", {})
    for zone, count in zones.items():
        if count == 0:
            actions.append(f"warning:zone_{zone}_empty")
            logger.warning("DHARMA: Zone %s has 0 agents", zone)

    # Layer 5: Council Election (before contracts, so proposals have a council)
    if ctx.council is not None:
        if ctx.council.election_due(ctx.heartbeat_count):
            candidates = _get_election_candidates(ctx)
            if candidates:
                result = ctx.council.run_election(
                    candidates, ctx.heartbeat_count,
                )
                if result["elected_mayor"]:
                    actions.append(
                        f"election:mayor={result['elected_mayor']}"
                    )
                actions.append(
                    f"election:seats={len(result['council_seats'])}"
                )

    # Cognition: constraint checking via KnowledgeGraph
    if ctx.knowledge_graph is not None:
        from city.cognition import check_constraints
        violations = check_constraints("governance_cycle", {
            "heartbeat": ctx.heartbeat_count,
            "dead_agents": len(dead),
            "empty_zones": [z for z, c in zones.items() if c == 0],
        })
        for v in violations:
            actions.append(f"constraint_violated:{v}")
            logger.warning("DHARMA: Constraint violated — %s", v)

    # Layer 3: Quality Contracts
    if ctx.contracts is not None:
        results = ctx.contracts.check_all()
        for r in results:
            if r.status.value == "failing":
                actions.append(f"contract_failing:{r.name}:{r.message}")
                create_healing_mission(ctx, r)
                _submit_contract_proposal(ctx, r)

    # Layer 3: Issue lifecycle intents
    if ctx.issues is not None:
        issue_actions = ctx.issues.metabolize_issues()
        actions.extend(issue_actions)

        # Parse issue actions into Sankalpa missions
        if ctx.sankalpa is not None:
            for action in issue_actions:
                _process_issue_action(ctx, action)

    if actions:
        logger.info("DHARMA: %d governance actions", len(actions))
    return actions


def _get_election_candidates(ctx: PhaseContext) -> list[dict]:
    """Build candidate list from living citizens with multi-dimensional ranking.

    Composite rank_score: 50% prana + 40% integrity + 10% guna bonus.
    Falls back to prana-only if steward-protocol modules unavailable.
    """
    # Try to load Guna module for multi-dimensional ranking
    try:
        from vibe_core.mahamantra.substrate.core.guna import Guna, get_guna_by_position
        guna_available = True
    except Exception:
        guna_available = False

    citizens = ctx.pokedex.list_citizens()
    candidates = []
    for c in citizens:
        cell = ctx.pokedex.get_cell(c["name"])
        if cell is not None and cell.is_alive:
            position = c["classification"]["position"]
            prana_norm = cell.prana / 21600  # Normalize to 0-1

            if guna_available:
                try:
                    guna = get_guna_by_position(position)
                    integrity = getattr(cell, "membrane_integrity", cell.prana) / 21600
                    # Composite: 50% prana + 40% integrity + 10% guna bonus
                    rank_score = prana_norm * 0.5 + integrity * 0.4
                    if guna == Guna.SATTVA:
                        rank_score += 0.1
                    elif guna == Guna.RAJAS:
                        rank_score += 0.05
                except Exception:
                    rank_score = prana_norm
            else:
                rank_score = prana_norm

            candidates.append({
                "name": c["name"],
                "prana": cell.prana,
                "guardian": c["classification"]["guardian"],
                "position": position,
                "rank_score": rank_score,
            })
    return candidates


def _submit_contract_proposal(ctx: PhaseContext, contract_result: object) -> None:
    """Submit a failing contract as a council proposal for democratic vote.

    Integrity contract violations require CONSTITUTIONAL supermajority (67%)
    because they affect protected core files. All other contracts use POLICY (50%).
    """
    if ctx.council is None or ctx.council.member_count == 0:
        return

    proposer = ctx.council.elected_mayor
    if proposer is None:
        return

    from city.council import ProposalType

    is_integrity = contract_result.name == "integrity"

    ctx.council.propose(
        title=f"{'Integrity violation' if is_integrity else 'Heal contract'}: {contract_result.name}",
        description=f"Contract failing: {contract_result.message}",
        proposer=proposer,
        proposal_type=ProposalType.CONSTITUTIONAL if is_integrity else ProposalType.POLICY,
        action={
            "type": "integrity" if is_integrity else "heal",
            "contract": contract_result.name,
            "files": contract_result.details if is_integrity else [],
            "params": {"details": contract_result.details},
        },
        timestamp=time.time(),
    )


def _process_issue_action(ctx: PhaseContext, action: str) -> None:
    """Parse an issue action string and create a Sankalpa mission if warranted.

    Action format: "type:#number:reason"
    - "intent_needed:#42:low_prana" → create HEAL mission
    - "contract_check:#42:audit_needed" → create AUDIT mission
    - "closed:#42:prana_exhaustion" → no action (already handled)
    - "ashrama:#42:brahmachari" → no action (informational)
    """
    parts = action.split(":")
    if len(parts) < 2:
        return

    action_type = parts[0]
    issue_ref = parts[1] if len(parts) > 1 else ""

    # Only create missions for actionable types
    if action_type not in ("intent_needed", "contract_check"):
        return

    # Extract issue number from "#42" format
    if not issue_ref.startswith("#"):
        return
    try:
        issue_number = int(issue_ref[1:])
    except ValueError:
        return

    # Get issue title from CityIssueManager cell cache
    title = f"Issue #{issue_number}"
    if ctx.issues is not None:
        cell = ctx.issues._issue_cells.get(issue_number)
        if cell is not None:
            title = getattr(cell, "name", title)

    mission_type = "audit_needed" if action_type == "contract_check" else "intent_needed"
    create_issue_mission(ctx, issue_number, title, mission_type)
