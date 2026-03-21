"""
Initiative Handler — Svadharma-driven autonomous agent initiative.

Agents create their OWN missions based on their nature (Guardian × Domain × Protocol).
The VenuOrchestrator gives the rhythm (WHEN). The Svadharma table gives the duty (WHAT).
Prana gates whether they can afford it. Zero LLM. Pure deterministic substrate.

    domain(ENGINEERING) + protocol(infer)   → code_health_audit
    domain(RESEARCH)    + protocol(enforce) → knowledge_synthesis
    domain(GOVERNANCE)  + protocol(infer)   → evaluate_proposals
    domain(DISCOVERY)   + protocol(parse)   → scan_federation_peers

Priority 35: after Sankalpa(30) creates external missions,
before Cognition(40) routes them. Initiative fills the gap.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler
from city.karma_handlers.diw_bridge import DIWAwareHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.INITIATIVE")

# ── Svadharma Table ──────────────────────────────────────────────────────
#
# Deterministic lookup: (domain, capability_protocol) → initiative.
# Derived from the 16 Guardians. Not heuristic. Not LLM. Table.
#
# The combination of WHERE an agent works (domain) and HOW it works
# (protocol) determines WHAT it should seek when idle. This is dharma.

SVADHARMA_TABLE: dict[tuple[str, str], dict[str, str]] = {
    # DISCOVERY — genesis quarter (vyasa, brahma, narada, shambhu)
    ("DISCOVERY", "parse"): {
        "name": "Scan federation peers",
        "description": "Discover new federation nodes, fetch authority feeds, update peer registry",
    },
    ("DISCOVERY", "validate"): {
        "name": "Verify peer health",
        "description": "Validate known peer descriptors, check liveness, flag stale entries",
    },
    # GOVERNANCE — dharma quarter (prithu, kumaras, kapila, manu)
    ("GOVERNANCE", "validate"): {
        "name": "Check policy compliance",
        "description": "Audit active agents against governance policies, flag violations",
    },
    ("GOVERNANCE", "infer"): {
        "name": "Evaluate open proposals",
        "description": "Analyze pending governance proposals, prepare council recommendations",
    },
    # ENGINEERING — karma quarter (parashurama, prahlada, janaka, bhishma)
    ("ENGINEERING", "infer"): {
        "name": "Code health audit",
        "description": "Assess code quality contracts, identify failing checks, prioritize fixes",
    },
    ("ENGINEERING", "route"): {
        "name": "Extend capabilities",
        "description": "Identify capability gaps in the agent population, propose new cartridge specs",
    },
    ("ENGINEERING", "enforce"): {
        "name": "Fix bottlenecks",
        "description": "Address known bottlenecks from Brain escalations, prepare fix proposals",
    },
    # RESEARCH — moksha quarter (nrisimha, bali, shuka, yamaraja)
    ("RESEARCH", "enforce"): {
        "name": "Knowledge synthesis",
        "description": "Synthesize observations from recent heartbeats into actionable knowledge",
    },
}

# ── Thresholds ───────────────────────────────────────────────────────────

# VENU energy gate: initiative requires moderate energy (between cognition=16 and heal=32)
_INITIATIVE_VENU_THRESHOLD: int = 24

# Prana gate: agent must be able to afford the initiative (metabolic_cost × 3 cycles)
_INITIATIVE_PRANA_FLOOR: int = 30

# Max initiatives per heartbeat (prevent flooding the mission queue)
_MAX_INITIATIVES_PER_TICK: int = 4


# ── Handler ──────────────────────────────────────────────────────────────


class InitiativeHandler(DIWAwareHandler, BaseKarmaHandler):
    """Agents create missions from their own nature. Svadharma.

    Flow:
    1. VENU gate: only fire when orchestrator energy >= 24
    2. For each active agent with enough prana:
       a. Look up (domain, protocol) in SVADHARMA_TABLE
       b. Dedup: skip if active mission for this initiative already exists
       c. Create mission with agent as owner
    3. Cognition handler (priority 40) will route these missions next
    """

    @property
    def name(self) -> str:
        return "initiative"

    @property
    def priority(self) -> int:
        return 35  # after Sankalpa(30), before Cognition(40)

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.sankalpa is None:
            return False
        # DIW gate: require moderate energy
        if self.current_diw is not None and self.venu_energy < _INITIATIVE_VENU_THRESHOLD:
            logger.debug(
                "INITIATIVE: skipped — venu energy %d < %d",
                self.venu_energy,
                _INITIATIVE_VENU_THRESHOLD,
            )
            return False
        return True

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        all_specs = ctx.all_specs
        if not all_specs:
            return

        from vibe_core.mahamantra.protocols.sankalpa.types import (
            MissionPriority,
            MissionStatus,
            SankalpaMission,
        )

        # Collect active mission IDs for dedup
        active_missions = ctx.sankalpa.registry.get_active_missions()
        active_prefixes = {m.id.rsplit("_", 1)[0] for m in active_missions}

        created = 0
        for agent_name in ctx.active_agents:
            if created >= _MAX_INITIATIVES_PER_TICK:
                break

            spec = all_specs.get(agent_name)
            if spec is None:
                continue

            # Prana gate
            prana = _get_agent_prana(ctx, agent_name)
            if prana < _INITIATIVE_PRANA_FLOOR:
                continue

            # Svadharma lookup
            domain = spec.get("domain", "")
            protocol = spec.get("capability_protocol", "")
            svadharma = SVADHARMA_TABLE.get((domain, protocol))
            if svadharma is None:
                continue

            # Dedup: one initiative per (domain, protocol) per heartbeat
            mission_prefix = f"initiative_{domain}_{protocol}"
            if mission_prefix in active_prefixes:
                continue

            mission_id = f"{mission_prefix}_{ctx.heartbeat_count}"
            mission = SankalpaMission(
                id=mission_id,
                name=svadharma["name"],
                description=svadharma["description"],
                priority=MissionPriority.MEDIUM,
                status=MissionStatus.ACTIVE,
                owner=agent_name,
            )
            ctx.sankalpa.registry.add_mission(mission)
            active_prefixes.add(mission_prefix)  # prevent same-tick dupes
            created += 1

            logger.info(
                "INITIATIVE: %s (guardian=%s) created '%s' — svadharma(%s, %s)",
                agent_name,
                spec.get("guardian", "?"),
                svadharma["name"],
                domain,
                protocol,
            )
            operations.append(
                f"initiative:{agent_name}:{domain}.{protocol}:{svadharma['name']}"
            )

        if created:
            operations.append(f"initiative_total:{created}")
            logger.info("INITIATIVE: %d missions created by agent initiative", created)


def _get_agent_prana(ctx: PhaseContext, agent_name: str) -> int:
    """Get agent's prana balance from CivicBank."""
    try:
        return ctx.pokedex._bank.get_balance(agent_name)
    except Exception:
        return 0
