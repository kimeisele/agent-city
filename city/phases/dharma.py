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

from city.missions import create_healing_mission
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
    """Submit a failing contract as a council proposal for democratic vote."""
    if ctx.council is None or ctx.council.member_count == 0:
        return

    proposer = ctx.council.elected_mayor
    if proposer is None:
        return

    from city.council import ProposalType

    ctx.council.propose(
        title=f"Heal contract: {contract_result.name}",
        description=f"Contract failing: {contract_result.message}",
        proposer=proposer,
        proposal_type=ProposalType.POLICY,
        action={
            "type": "heal",
            "contract": contract_result.name,
            "params": {"details": contract_result.details},
        },
        timestamp=time.time(),
    )
