"""
KARMA Phase — Operations, Heal Intents, Council Governance.

Processes gateway queue, sankalpa strategic intents, heal failing contracts
via executor, and council auto-vote + proposal execution.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.KARMA")


def _learn(ctx: PhaseContext, source: str, action: str, *, success: bool) -> None:
    """Record a Hebbian learning outcome if learning is wired."""
    if ctx.learning is not None:
        ctx.learning.record_outcome(source, action, success)


def execute(ctx: PhaseContext) -> list[str]:
    """KARMA: Process gateway queue, sankalpa, heal, council cycle."""
    operations: list[str] = []

    # Cognition: compile KG context for this KARMA cycle
    kg_context = ""
    if ctx.knowledge_graph is not None:
        from city.cognition import compile_context
        kg_context = compile_context("process gateway queue operations")

    # Drain from Nadi (priority-sorted) + fallback gateway_queue
    queue_items: list[dict] = []
    if ctx.city_nadi is not None:
        queue_items = ctx.city_nadi.drain()
    # Also drain legacy gateway_queue (backward compat)
    while ctx.gateway_queue:
        queue_items.append(ctx.gateway_queue.pop(0))

    for item in queue_items:
        source = item.get("source", "unknown")
        text = item.get("text", "")
        conversation_id = item.get("conversation_id", "")
        from_agent = item.get("from_agent", "")

        try:
            # Enrich text with KG context if available
            enriched_text = f"{text}\n\n{kg_context}" if kg_context else text
            result = ctx.gateway.process(enriched_text, source)

            # DM messages: generate response and send back
            if conversation_id and from_agent and ctx.moltbook_client is not None:
                from city.inbox import InboxMessage, dispatch

                msg = InboxMessage(
                    from_agent=from_agent,
                    text=text,
                    conversation_id=conversation_id,
                )
                response = dispatch(msg, result, ctx.pokedex)

                try:
                    ctx.moltbook_client.sync_send_dm(
                        response.conversation_id,
                        response.text,
                    )
                    operations.append(
                        f"dm_replied:{from_agent}:seed={result['seed']}"
                    )
                    _learn(ctx, source, "dm_reply", success=True)
                except Exception as e:
                    operations.append(f"dm_reply_failed:{from_agent}:{e}")
                    _learn(ctx, source, "dm_reply", success=False)
                    logger.warning(
                        "KARMA: DM reply failed for %s: %s", from_agent, e,
                    )
            else:
                operations.append(f"processed:{source}:seed={result['seed']}")
                _learn(ctx, source, "process", success=True)

        except Exception as e:
            operations.append(f"error:{source}:{e}")
            _learn(ctx, source, "process", success=False)
            logger.warning("KARMA: Gateway processing failed for %s: %s", source, e)

    # Log learning confidence for queue items (informational)
    if ctx.learning is not None and queue_items:
        for item in queue_items:
            src = item.get("source", "unknown")
            confidence = ctx.learning.get_confidence(src, "process")
            if confidence < 0.2:
                logger.warning(
                    "KARMA: Low confidence for %s→process (%.2f)",
                    src, confidence,
                )

    # Layer 3: Sankalpa strategic thinking
    if ctx.sankalpa is not None:
        intents = ctx.sankalpa.think()
        for intent in intents:
            operations.append(f"sankalpa_intent:{intent.title}")
            logger.info("KARMA: Sankalpa intent — %s", intent.title)

    # Layer 4: Execute HEAL intents on failing contracts
    if ctx.executor is not None and ctx.contracts is not None:
        for contract in ctx.contracts.failing():
            details = contract.last_result.details if contract.last_result else []
            fix = ctx.executor.execute_heal(contract.name, details)
            operations.append(
                f"heal:{fix.contract_name}:{fix.action_taken}:{fix.success}"
            )
            logger.info(
                "KARMA: Heal %s — %s (success=%s)",
                fix.contract_name, fix.action_taken, fix.success,
            )

            if fix.success and fix.files_changed:
                pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
                if pr is not None and pr.success:
                    operations.append(f"pr_created:{pr.pr_url}")
                    logger.info("KARMA: PR created — %s", pr.pr_url)

    # Layer 5: Council governance cycle
    if ctx.council is not None and ctx.council.member_count > 0:
        _council_auto_vote(ctx)

        for proposal in ctx.council.get_passed_proposals():
            executed = _execute_proposal(ctx, proposal)
            operations.append(
                f"council_executed:{proposal.id}:{executed}"
            )
            ctx.council.mark_executed(proposal.id)

    if operations:
        logger.info("KARMA: %d operations processed", len(operations))
    return operations


def _execute_proposal(ctx: PhaseContext, proposal: object) -> bool:
    """Execute a passed council proposal. Returns True on success."""
    action_type = proposal.action.get("type")
    params = proposal.action.get("params", {})

    if action_type == "freeze" and params.get("target"):
        try:
            ctx.pokedex.freeze(
                params["target"], f"council_proposal:{proposal.id}",
            )
            return True
        except (ValueError, Exception) as e:
            logger.warning("Proposal %s failed: %s", proposal.id, e)
            return False

    if action_type == "unfreeze" and params.get("target"):
        try:
            ctx.pokedex.unfreeze(
                params["target"], f"council_proposal:{proposal.id}",
            )
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

    if action_type == "improve":
        logger.info("Proposal %s: improvement noted — %s", proposal.id, proposal.title)
        return True

    logger.warning("Unknown proposal action: %s", action_type)
    return False


def _council_auto_vote(ctx: PhaseContext) -> None:
    """Council members vote on all open proposals (buddhi-driven).

    Instead of blindly voting YES, each member consults buddhi.think()
    to discriminate proposal quality via integrity + mode signals.
    """
    if ctx.council is None:
        return

    from city.council import VoteChoice

    # Buddhi-driven voting: real discrimination, not rubber-stamping
    try:
        from vibe_core.mahamantra.substrate.buddhi import get_buddhi
        buddhi = get_buddhi()
    except Exception:
        buddhi = None

    open_proposals = ctx.council.get_open_proposals()
    for proposal in open_proposals:
        # Run buddhi once per proposal (deterministic for same title)
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
                    # Buddhi-driven: integrity + mode signals
                    if cognition.integrity > 0.7 and cognition.is_alive:
                        choice = VoteChoice.YES
                    elif cognition.integrity > 0.4:
                        choice = VoteChoice.ABSTAIN
                    else:
                        choice = VoteChoice.NO
                else:
                    # Fallback: auto-YES (backward compatible)
                    choice = VoteChoice.YES

                ctx.council.vote(
                    proposal.id, member_name, choice, prana,
                )
        ctx.council.tally(proposal.id)
