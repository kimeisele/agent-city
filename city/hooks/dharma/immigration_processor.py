"""
DHARMA Hook: Immigration Processor — Process pending applications.

Runs after Promotion (pri=10), before Elections (pri=20).
Processes the ImmigrationService application queue:
  1. Auto-review pending applications (KYC = agent exists in Pokedex)
  2. Move approved applications to council vote
  3. Grant citizenship for council-approved applications

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.IMMIGRATION")


class ImmigrationProcessorHook(BasePhaseHook):
    """Process pending immigration applications through the Rathaus pipeline."""

    @property
    def name(self) -> str:
        return "immigration_processor"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 12  # after promotion (10), before zone health (15)

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.immigration is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        immigration = ctx.immigration
        from city.immigration import ApplicationStatus

        # 1. Auto-review PENDING applications
        pending = immigration.list_applications(ApplicationStatus.PENDING)
        for app in pending:
            immigration.start_review(app.application_id, reviewer="rathaus_auto")

            # KYC: agent must be discovered in Pokedex
            existing = ctx.pokedex.get(app.agent_name)
            kyc_passed = existing is not None

            # Contracts: basic check — name is not empty, not exiled
            contracts_passed = bool(app.agent_name)
            if existing and existing.get("status") == "exiled":
                contracts_passed = False

            # Community score from Moltbook metadata (if available)
            community_score = 0.5  # default baseline
            if existing:
                moltbook = existing.get("moltbook") or {}
                karma = moltbook.get("karma", 0)
                followers = moltbook.get("followers", 0)
                if karma > 0 or followers > 0:
                    community_score = min(1.0, 0.5 + karma * 0.01 + followers * 0.005)

            immigration.complete_review(
                app.application_id,
                kyc_passed=kyc_passed,
                contracts_passed=contracts_passed,
                community_score=community_score,
                notes=f"auto-review: kyc={'pass' if kyc_passed else 'fail'}, "
                f"contracts={'pass' if contracts_passed else 'fail'}",
            )
            status = "approved" if kyc_passed and contracts_passed else "rejected"
            operations.append(f"immigration:review:{app.agent_name}:{status}")

        # 2. Move APPROVED applications to council
        approved = immigration.list_applications(ApplicationStatus.APPROVED)
        for app in approved:
            vote_id = f"immigration_{app.application_id}_{ctx.heartbeat_count}"
            immigration.move_to_council(app.application_id, vote_id)
            operations.append(f"immigration:council_pending:{app.agent_name}")

            # Auto-vote if council exists (for bootstrap — real councils
            # will vote through CouncilHandler in KARMA phase)
            if ctx.council is not None:
                seats = ctx.council.get_seats()
                if seats:
                    # Council members vote based on community score
                    yes_count = sum(
                        1 for _ in seats.values()
                        if app.community_score >= 0.3
                    )
                    no_count = len(seats) - yes_count
                    tally = {"yes": yes_count, "no": no_count, "abstain": 0}
                    approved_by_council = yes_count > no_count
                    immigration.record_council_vote(
                        app.application_id,
                        approved=approved_by_council,
                        vote_tally=tally,
                    )
                    if approved_by_council:
                        operations.append(
                            f"immigration:council_approved:{app.agent_name}"
                        )
                    else:
                        operations.append(
                            f"immigration:council_rejected:{app.agent_name}"
                        )

        # 3. Grant citizenship for COUNCIL_APPROVED
        council_approved = immigration.list_applications(
            ApplicationStatus.COUNCIL_APPROVED
        )
        for app in council_approved:
            visa = immigration.grant_citizenship(
                app.application_id, sponsor="council"
            )
            if visa:
                # Upgrade Pokedex status: discovered → citizen
                ctx.pokedex.register(app.agent_name)
                operations.append(
                    f"immigration:citizenship_granted:{app.agent_name}:"
                    f"class={visa.visa_class.value}"
                )
                logger.info(
                    "IMMIGRATION: Citizenship granted to %s (visa=%s)",
                    app.agent_name,
                    visa.visa_id[:12],
                )

        # Log stats
        stats = immigration.stats()
        if stats["pending_applications"] > 0 or stats["citizenship_granted"] > 0:
            logger.info(
                "IMMIGRATION: %d pending, %d granted, %d total visas",
                stats["pending_applications"],
                stats["citizenship_granted"],
                stats["total_visas"],
            )
