"""
DHARMA Hook: Contracts + Issues — quality contracts, issue lifecycle, community triage.

Extracted from dharma.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from city.missions import create_healing_mission, create_issue_mission
from city.phase_hook import DHARMA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.CONTRACTS")


class ContractsHook(BasePhaseHook):
    """Quality contract checks + healing missions + council proposals."""

    @property
    def name(self) -> str:
        return "contracts"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 40

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.contracts is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        results = ctx.contracts.check_all()
        for r in results:
            if r.status.value == "failing":
                operations.append(f"contract_failing:{r.name}:{r.message}")
                create_healing_mission(ctx, r)
                _submit_contract_proposal(ctx, r)


class IssueLifecycleHook(BasePhaseHook):
    """Issue lifecycle intents + structured IssueDirective consumption."""

    @property
    def name(self) -> str:
        return "issue_lifecycle"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 45

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.issues is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        issue_actions = ctx.issues.metabolize_issues()
        operations.extend(issue_actions)

        # Consume structured IssueDirectives (replaces string parsing)
        if ctx.sankalpa is not None:
            for directive in ctx.issues.directives:
                _process_issue_directive(ctx, directive)


class MoltbookAssistantDharmaHook(BasePhaseHook):
    """Moltbook Assistant: strategic planning for KARMA."""

    @property
    def name(self) -> str:
        return "moltbook_assistant_dharma"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 50

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.moltbook_assistant is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        ctx.moltbook_assistant.on_dharma(ctx)


class CommunityTriageHook(BasePhaseHook):
    """Plan which discussion threads need attention this cycle."""

    @property
    def name(self) -> str:
        return "community_triage"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 60

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.thread_state is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.community_triage import triage_threads

        seed_threads = {}
        if ctx.discussions is not None and hasattr(ctx.discussions, "_seed_threads"):
            seed_threads = ctx.discussions._seed_threads

        # Threads enqueued by GENESIS for Gateway processing (AgentRuntime+Browser).
        # Triage must NOT steal these — Gateway has the full cognitive pipeline,
        # Triage has templates. If both respond, we get duplicate template spam.
        gateway_disc_nums: set[int] = getattr(ctx, "_gateway_disc_nums", set())

        triage_items = triage_threads(
            ctx.thread_state,
            ctx.pokedex,
            seed_threads=seed_threads,
            exclude_threads=gateway_disc_nums,
        )
        if triage_items:
            existing = getattr(ctx, "_triage_items", [])
            ctx._triage_items = existing + triage_items  # type: ignore[attr-defined]


# ── Helpers ──────────────────────────────────────────────────────────


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

    prefix = "Integrity violation" if is_integrity else "Heal contract"
    ptype = ProposalType.CONSTITUTIONAL if is_integrity else ProposalType.POLICY
    ctx.council.propose(
        title=f"{prefix}: {contract_result.name}",
        description=f"Contract failing: {contract_result.message}",
        proposer=proposer,
        proposal_type=ptype,
        action={
            "type": "integrity" if is_integrity else "heal",
            "contract": contract_result.name,
            "files": contract_result.details if is_integrity else [],
            "params": {"details": contract_result.details},
        },
        timestamp=time.time(),
        heartbeat=ctx.heartbeat_count,
    )


def _process_issue_directive(ctx: PhaseContext, directive: object) -> None:
    """Consume an IssueDirective and create a bound Sankalpa mission.

    Only actionable directives (intent_needed, contract_check) produce missions.
    Informational (ashrama, closed) are skipped.
    """
    if directive.action not in ("intent_needed", "contract_check"):
        return

    mission_type = "audit_needed" if directive.action == "contract_check" else "intent_needed"
    mission_id = create_issue_mission(ctx, directive.issue_number, directive.title, mission_type)

    # Bind mission↔issue for lifecycle tracking
    if mission_id is not None and ctx.issues is not None:
        ctx.issues.bind_mission(directive.issue_number, mission_id)


