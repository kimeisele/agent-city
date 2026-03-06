"""Council Handler — Auto-vote + proposal execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.COUNCIL")


class CouncilHandler(BaseKarmaHandler):
    """Council governance cycle: auto-vote + execute passed proposals."""

    @property
    def name(self) -> str:
        return "council"

    @property
    def priority(self) -> int:
        return 80

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.council is not None and ctx.council.member_count > 0

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        _council_auto_vote(ctx)

        for proposal in ctx.council.get_passed_proposals():
            executed = _execute_proposal(ctx, proposal)
            operations.append(f"council_executed:{proposal.id}:{executed}")
            ctx.council.mark_executed(proposal.id)


def _council_auto_vote(ctx: PhaseContext) -> None:
    """Council members vote on all open proposals (buddhi-driven)."""
    from city.council import VoteChoice

    try:
        from vibe_core.mahamantra.substrate.buddhi import get_buddhi
        buddhi = get_buddhi()
    except Exception:
        buddhi = None

    open_proposals = ctx.council.get_open_proposals()
    for proposal in open_proposals:
        cognition = None
        if buddhi is not None:
            try:
                cognition = buddhi.think(proposal.title)
            except Exception as e:
                logger.debug("Buddhi think failed for '%s': %s", proposal.title, e)

        for seat_idx, member_name in ctx.council.seats.items():
            cell = ctx.pokedex.get_cell(member_name)
            prana = cell.prana if cell is not None and cell.is_alive else 0
            if prana > 0:
                if cognition is not None:
                    if cognition.integrity > 0.7 and cognition.is_alive:
                        choice = VoteChoice.YES
                    elif cognition.integrity > 0.4:
                        choice = VoteChoice.ABSTAIN
                    else:
                        choice = VoteChoice.NO
                else:
                    choice = VoteChoice.YES

                ctx.council.vote(proposal.id, member_name, choice, prana)
        ctx.council.tally(proposal.id)


def _execute_proposal(ctx: PhaseContext, proposal: object) -> bool:
    """Execute a passed council proposal. Returns True on success."""
    action_type = proposal.action.get("type")
    params = proposal.action.get("params", {})

    allowed, reason = _authorize_proposal_execution(ctx, action_type)
    if not allowed:
        logger.warning(
            "Proposal %s denied during execution (action=%s, reason=%s)",
            proposal.id,
            action_type,
            reason,
        )
        return False

    if action_type == "freeze" and params.get("target"):
        try:
            ctx.pokedex.freeze(params["target"], f"council_proposal:{proposal.id}")
            return True
        except (ValueError, Exception) as e:
            logger.warning("Proposal %s failed: %s", proposal.id, e)
            return False

    if action_type == "unfreeze" and params.get("target"):
        try:
            ctx.pokedex.unfreeze(params["target"], f"council_proposal:{proposal.id}")
            return True
        except (ValueError, Exception) as e:
            logger.warning("Proposal %s failed: %s", proposal.id, e)
            return False

    if action_type == "heal" and ctx.executor is not None:
        contract_name = proposal.action.get("contract", "")
        details = params.get("details", [])
        fix = ctx.executor.execute_heal(contract_name, details)
        if fix.success:
            logger.info(
                "Proposal %s: healed %s via %s",
                proposal.id, contract_name, fix.action_taken,
            )
        return fix.success

    if action_type == "integrity":
        files = proposal.action.get("files", [])
        if not files:
            logger.warning("Proposal %s: integrity action with no files", proposal.id)
            return False
        try:
            from city.git_client import GitStateAuthority
            gsa = GitStateAuthority()
            gsa.stage(files)
            msg = (
                f"council-approved({proposal.id}): integrity update — "
                + ", ".join(files)
            )
            gsa.commit(msg)
            logger.info(
                "Proposal %s: integrity approved — committed %d file(s)",
                proposal.id, len(files),
            )
            return True
        except Exception as e:
            logger.warning("Proposal %s: integrity commit failed: %s", proposal.id, e)
            return False

    if action_type == "improve":
        logger.info("Proposal %s: improvement noted — %s", proposal.id, proposal.title)
        return True

    if action_type in ("set_commission", "freeze_market", "unfreeze_market"):
        if ctx.council is not None:
            success = ctx.council.apply_marketplace_action(proposal.action)
            if success:
                logger.info("Proposal %s: marketplace action %s applied", proposal.id, action_type)
            return success
        return False

    logger.warning("Unknown proposal action: %s", action_type)
    return False


def _authorize_proposal_execution(
    ctx: PhaseContext,
    action_type: str | None,
) -> tuple[bool, str]:
    requirement = _proposal_authority_requirement(action_type)
    if requirement is None:
        return True, "ok"

    from city.membrane import authorize_ingress, internal_membrane_snapshot

    return authorize_ingress(
        ctx,
        membrane=internal_membrane_snapshot(source_class="governance"),
        requirement=requirement,
    )


def _proposal_authority_requirement(action_type: str | None):
    from city.access import AccessClass
    from city.membrane import AuthorityRequirement

    if action_type == "integrity":
        return AuthorityRequirement(access_class=AccessClass.STEWARD)
    if action_type in {
        "freeze",
        "unfreeze",
        "heal",
        "set_commission",
        "freeze_market",
        "unfreeze_market",
    }:
        return AuthorityRequirement(access_class=AccessClass.OPERATOR)
    return None
