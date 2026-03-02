"""
DHARMA Hook: Governance — council elections, cognition constraints, proposals.

Extracted from dharma.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook
from city.seed_constants import PRANA_NORM_MAX

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.GOVERNANCE")


class ElectionHook(BasePhaseHook):
    """Council elections + stipend compensation."""

    @property
    def name(self) -> str:
        return "election"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 20

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.council is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        if ctx.council.election_due(ctx.heartbeat_count):
            candidates = _get_election_candidates(ctx)
            if candidates:
                result = ctx.council.run_election(
                    candidates,
                    ctx.heartbeat_count,
                )
                if result["elected_mayor"]:
                    operations.append(f"election:mayor={result['elected_mayor']}")
                operations.append(f"election:seats={len(result['council_seats'])}")

                # Council compensation (idempotent per election heartbeat)
                from city.seed_constants import WORKER_VISA_STIPEND

                stipend_key = f"_stipend_paid_{ctx.heartbeat_count}"
                if not getattr(ctx.council, stipend_key, False):
                    for _seat_idx, member_name in result["council_seats"].items():
                        try:
                            ctx.pokedex._bank.transfer(
                                "MINT",
                                member_name,
                                WORKER_VISA_STIPEND,
                                "council_stipend",
                                "governance",
                            )
                            operations.append(
                                f"council_stipend:{member_name}:{WORKER_VISA_STIPEND}",
                            )
                        except Exception as e:
                            logger.warning(
                                "DHARMA: Stipend failed for %s: %s",
                                member_name,
                                e,
                            )
                    setattr(ctx.council, stipend_key, True)


class CognitionConstraintsHook(BasePhaseHook):
    """Cognition constraint checking via KnowledgeGraph."""

    @property
    def name(self) -> str:
        return "cognition_constraints"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 25

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.knowledge_graph is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.cognition import check_constraints

        dead = getattr(ctx, "_dharma_dead", [])
        stats = ctx.pokedex.stats()
        zones = stats.get("zones", {})

        violations = check_constraints(
            "governance_cycle",
            {
                "heartbeat": ctx.heartbeat_count,
                "dead_agents": len(dead),
                "empty_zones": [z for z, c in zones.items() if c == 0],
            },
        )
        for v in violations:
            operations.append(f"constraint_violated:{v}")
            logger.warning("DHARMA: Constraint violated — %s", v)


class ProposalExpiryHook(BasePhaseHook):
    """Expire stale council proposals."""

    @property
    def name(self) -> str:
        return "proposal_expiry"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 30

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.council is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        expired = ctx.council.expire_proposals(ctx.heartbeat_count)
        if expired:
            operations.append(f"proposals_expired:{expired}")


# ── Helpers ──────────────────────────────────────────────────────────


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
            prana_norm = cell.prana / PRANA_NORM_MAX  # COSMIC_FRAME (21600)

            if guna_available:
                try:
                    guna = get_guna_by_position(position)
                    integrity = getattr(cell, "membrane_integrity", cell.prana) / PRANA_NORM_MAX
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

            candidates.append(
                {
                    "name": c["name"],
                    "prana": cell.prana,
                    "guardian": c["classification"]["guardian"],
                    "position": position,
                    "rank_score": rank_score,
                }
            )
    return candidates
