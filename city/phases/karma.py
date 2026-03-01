"""
KARMA Phase — Operations, Heal Intents, Council Governance.

Processes gateway queue, sankalpa strategic intents, heal failing contracts
via executor, and council auto-vote + proposal execution.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

from city.cognition import emit_event
from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.KARMA")


def _learn(ctx: PhaseContext, source: str, action: str, *, success: bool) -> None:
    """Record a Hebbian learning outcome if learning is wired."""
    if ctx.learning is not None:
        ctx.learning.record_outcome(source, action, success)


def execute(ctx: PhaseContext) -> list[str]:
    """KARMA: Process gateway queue, sankalpa, heal, council cycle."""
    operations: list[str] = []

    # Mark all living citizens as active (feeds energy during next DHARMA metabolize)
    from city.registry import SVC_SPAWNER

    spawner = ctx.registry.get(SVC_SPAWNER)
    if spawner is not None:
        active_count = spawner.mark_citizens_active(ctx.active_agents)
        if active_count:
            operations.append(f"citizens_active:{active_count}")

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
                    operations.append(f"dm_replied:{from_agent}:seed={result['seed']}")
                    _learn(ctx, source, "dm_reply", success=True)
                except Exception as e:
                    operations.append(f"dm_reply_failed:{from_agent}:{e}")
                    _learn(ctx, source, "dm_reply", success=False)
                    logger.warning(
                        "KARMA: DM reply failed for %s: %s",
                        from_agent,
                        e,
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
                    src,
                    confidence,
                )

    # Layer 3: Sankalpa strategic thinking
    if ctx.sankalpa is not None:
        intents = ctx.sankalpa.think()
        for intent in intents:
            operations.append(f"sankalpa_intent:{intent.title}")
            logger.info("KARMA: Sankalpa intent — %s", intent.title)

    # Collect agent specs ONCE for all routing decisions (shared across call sites)
    all_specs = _get_all_specs(ctx)

    # Cartridge routing: capability-scored agent dispatch
    _route_to_cartridges(ctx, operations, all_specs)

    # Issue-driven missions: process strategyless missions from DHARMA
    if ctx.sankalpa is not None:
        _process_issue_missions(ctx, operations, all_specs)

    # Layer 4: Execute HEAL intents on failing contracts (CAPABILITY GATED)
    if ctx.executor is not None and ctx.contracts is not None:
        from city.mission_router import authorize_mission

        heal_authorized = authorize_mission("heal_", all_specs, ctx.active_agents)
        if not heal_authorized:
            logger.info(
                "KARMA: Heal operations blocked — no agent with validate capability at contributor tier"
            )
        else:
            for contract in ctx.contracts.failing():
                details = contract.last_result.details if contract.last_result else []
                fix = ctx.executor.execute_heal(contract.name, details)
                operations.append(f"heal:{fix.contract_name}:{fix.action_taken}:{fix.success}")
                logger.info(
                    "KARMA: Heal %s — %s (success=%s)",
                    fix.contract_name,
                    fix.action_taken,
                    fix.success,
                )

                if fix.success and fix.files_changed:
                    pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
                    if pr is not None and pr.success:
                        operations.append(f"pr_created:{pr.pr_url}")
                        emit_event(
                            "ACTION",
                            "karma",
                            f"PR created: {pr.pr_url}",
                            {
                                "action": "pr_created",
                                "contract": contract.name,
                                "pr_url": pr.pr_url,
                                "heartbeat": ctx.heartbeat_count,
                            },
                        )
                        # Track PR for lifecycle management
                        from city.registry import SVC_PR_LIFECYCLE

                        pr_mgr = ctx.registry.get(SVC_PR_LIFECYCLE)
                        if pr_mgr is not None:
                            pr_mgr.track(pr.pr_url, pr.branch, contract.name, ctx.heartbeat_count)
                        logger.info("KARMA: PR created — %s", pr.pr_url)

    # Layer 5: Council governance cycle
    if ctx.council is not None and ctx.council.member_count > 0:
        _council_auto_vote(ctx)

        for proposal in ctx.council.get_passed_proposals():
            executed = _execute_proposal(ctx, proposal)
            operations.append(f"council_executed:{proposal.id}:{executed}")
            ctx.council.mark_executed(proposal.id)

    # Moltbook Assistant: execute planned actions (invites, posts, upvotes)
    if ctx.moltbook_assistant is not None:
        assistant_result = ctx.moltbook_assistant.on_karma(
            ctx.heartbeat_count,
            ctx.pokedex.stats(),
        )
        if assistant_result.get("invites_sent"):
            operations.append(f"assistant:invites={assistant_result['invites_sent']}")
        if assistant_result.get("post_created"):
            operations.append("assistant:post_created")

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
                params["target"],
                f"council_proposal:{proposal.id}",
            )
            return True
        except (ValueError, Exception) as e:
            logger.warning("Proposal %s failed: %s", proposal.id, e)
            return False

    if action_type == "unfreeze" and params.get("target"):
        try:
            ctx.pokedex.unfreeze(
                params["target"],
                f"council_proposal:{proposal.id}",
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
                proposal.id,
                contract_name,
                fix.action_taken,
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
            gsa.commit(
                f"council-approved({proposal.id}): integrity update — " + ", ".join(files),
            )
            logger.info(
                "Proposal %s: integrity approved — committed %d file(s)",
                proposal.id,
                len(files),
            )
            return True
        except Exception as e:
            logger.warning("Proposal %s: integrity commit failed: %s", proposal.id, e)
            return False

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
                    proposal.id,
                    member_name,
                    choice,
                    prana,
                )
        ctx.council.tally(proposal.id)


def _process_issue_missions(
    ctx: PhaseContext, operations: list[str], all_specs: dict[str, dict]
) -> None:
    """Process Sankalpa missions created from GitHub Issues and federation directives.

    Issue/exec missions have no strategies (fire-once), so they won't
    appear in sankalpa.think(). Process them directly in KARMA.

    CAPABILITY GATED: each mission must pass authorize_mission() before
    the dedicated processor runs. No bypass.
    """
    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
    except Exception:
        return

    from city.mission_router import authorize_mission

    try:
        active = ctx.sankalpa.registry.get_active_missions()
    except Exception:
        return

    for mission in active:
        # Handle federation execute_code missions
        if mission.id.startswith("exec_"):
            # CAPABILITY GATE: must have at least one agent with execute + verified tier
            if not authorize_mission(mission.id, all_specs, ctx.active_agents):
                operations.append(f"exec_blocked:{mission.id}:capability_gate")
                logger.info(
                    "KARMA: Exec mission %s blocked — no agent with execute capability",
                    mission.id,
                )
                continue

            success = _execute_code_mission(ctx, mission)
            operations.append(f"exec_mission:{mission.id}:{'success' if success else 'pending'}")
            if success:
                mission.status = MissionStatus.COMPLETED
                ctx.sankalpa.registry.add_mission(mission)
                emit_event(
                    "ACTION",
                    "karma",
                    f"Mission completed: {mission.name}",
                    {
                        "action": "mission_completed",
                        "mission_id": mission.id,
                        "mission_name": mission.name,
                        "owner": getattr(mission, "owner", ""),
                    },
                )
            _learn(ctx, mission.id, "exec_mission", success=success)
            logger.info(
                "KARMA: Exec mission %s — %s",
                mission.id,
                "completed" if success else "pending",
            )
            continue

        # Only process issue-driven missions
        if not mission.id.startswith("issue_"):
            continue

        # CAPABILITY GATE: must have at least one agent with execute + verified tier
        if not authorize_mission(mission.id, all_specs, ctx.active_agents):
            operations.append(f"issue_blocked:{mission.id}:capability_gate")
            logger.info(
                "KARMA: Issue mission %s blocked — no agent with execute capability",
                mission.id,
            )
            continue

        # Extract issue number from mission id (format: "issue_42_heartbeat")
        parts = mission.id.split("_")
        if len(parts) < 2:
            continue
        try:
            issue_number = int(parts[1])
        except ValueError:
            continue

        # Determine action based on mission name prefix
        if mission.name.startswith("IssueAudit"):
            success = _execute_issue_audit(ctx, issue_number)
        else:
            success = _execute_issue_heal(ctx, issue_number)

        operations.append(f"issue_mission:{mission.id}:{'success' if success else 'pending'}")

        # Update mission status
        if success:
            mission.status = MissionStatus.COMPLETED
            ctx.sankalpa.registry.add_mission(mission)
            emit_event(
                "ACTION",
                "karma",
                f"Issue mission completed: #{issue_number}",
                {
                    "action": "mission_completed",
                    "mission_id": mission.id,
                    "issue_number": issue_number,
                    "owner": getattr(mission, "owner", ""),
                },
            )
            # Close the issue↔mission binding loop
            if ctx.issues is not None:
                ctx.issues.resolve_issue(issue_number, mission.id)

        # Learn from outcome
        _learn(ctx, f"issue_{issue_number}", "issue_mission", success=success)
        logger.info(
            "KARMA: Issue mission %s — %s",
            mission.id,
            "completed" if success else "pending",
        )


def _execute_issue_audit(ctx: PhaseContext, issue_number: int) -> bool:
    """Execute an audit-needed issue mission."""
    if ctx.audit is None:
        return False
    try:
        ctx.audit.run_all()
        logger.info("KARMA: Issue #%d audit executed", issue_number)
        return True
    except Exception as e:
        logger.warning("KARMA: Issue #%d audit failed: %s", issue_number, e)
        return False


def _execute_issue_heal(ctx: PhaseContext, issue_number: int) -> bool:
    """Execute a heal-needed issue mission via immune system → executor escalation."""
    # Step 1: Try immune system (fast, no git involvement)
    if ctx.immune is not None:
        diagnosis = ctx.immune.diagnose(f"issue_low_prana:{issue_number}")
        if diagnosis.healable:
            result = ctx.immune.heal(diagnosis)
            if result.success:
                logger.info("KARMA: Issue #%d healed by immune system", issue_number)
                return True

    # Step 2: Escalate to executor (ruff fix → PR creation)
    if ctx.executor is not None:
        fix = ctx.executor.execute_heal("ruff_clean", [f"issue_{issue_number}"])
        if fix.success and fix.files_changed:
            pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
            if pr is not None and pr.success:
                _record_pr_event(ctx, issue_number, pr)
                logger.info(
                    "KARMA: Issue #%d → PR created: %s",
                    issue_number,
                    pr.pr_url,
                )
                return True
            if fix.success:
                # Fixed but no PR (dry run or no git changes)
                logger.info("KARMA: Issue #%d fixed (no PR needed)", issue_number)
                return True

    # No immune, no executor, or nothing healable — stay pending
    return False


def _execute_code_mission(ctx: PhaseContext, mission: object) -> bool:
    """Execute a federation code-execution mission via executor.

    Mission description format: "Federation directive: {contract_name}"
    """
    if ctx.executor is None:
        return False

    # Extract contract name from mission name (format: "Execute: ruff_clean")
    contract = "ruff_clean"  # default
    if mission.name.startswith("Execute: "):
        contract = mission.name[len("Execute: ") :]

    try:
        fix = ctx.executor.execute_heal(contract, [f"mission_{mission.id}"])
        if fix.success and fix.files_changed:
            pr = ctx.executor.create_fix_pr(fix, ctx.heartbeat_count)
            if pr is not None and pr.success:
                _record_pr_event(ctx, 0, pr)
                logger.info(
                    "KARMA: Exec mission %s → PR created: %s",
                    mission.id,
                    pr.pr_url,
                )
                return True
            if fix.success:
                logger.info("KARMA: Exec mission %s fixed (no PR needed)", mission.id)
                return True
    except Exception as e:
        logger.warning("KARMA: Exec mission %s failed: %s", mission.id, e)

    return False


def _route_to_cartridges(
    ctx: PhaseContext, operations: list[str], all_specs: dict[str, dict]
) -> None:
    """Route domain missions to best-fit agents via capability scoring + hard enforcement.

    ZERO BYPASS: every mission is scored against all agents. Hard gate
    blocks agents without required capabilities. Best-fit agent selected
    by 4-dimensional scoring (domain, capability coverage, protocol, QoS).
    """
    from city.registry import SVC_CARTRIDGE_LOADER

    from city.mission_router import route_mission

    loader = ctx.registry.get(SVC_CARTRIDGE_LOADER)
    if loader is None or ctx.sankalpa is None:
        return

    try:
        active = ctx.sankalpa.registry.get_active_missions()
    except Exception:
        return

    for mission in active:
        # Skip types handled by dedicated processors (which have their own gates)
        if mission.id.startswith(("issue_", "exec_")):
            continue

        result = route_mission(mission, all_specs, ctx.active_agents)

        if result["blocked"]:
            operations.append(f"route_blocked:{mission.id}:no_qualified_agent")
            logger.info(
                "KARMA: Mission %s blocked — %d agents failed capability gate",
                mission.id,
                result["blocked_count"],
            )
            continue

        agent_name = result["agent_name"]
        if agent_name is None:
            continue

        cartridge = loader.get(agent_name)
        if cartridge is None:
            continue

        try:
            if hasattr(cartridge, "process"):
                cartridge.process(mission.description)
                operations.append(f"routed:{agent_name}:{mission.id}:score={result['score']:.2f}")
                logger.info(
                    "KARMA: Routed %s → %s (score=%.2f, %d candidates)",
                    mission.id,
                    agent_name,
                    result["score"],
                    result["candidates_count"],
                )
        except Exception as e:
            logger.warning(
                "KARMA: Agent %s failed for mission %s: %s",
                agent_name,
                mission.id,
                e,
            )


def _get_all_specs(ctx: PhaseContext) -> dict[str, dict]:
    """Collect all agent specs from CartridgeFactory.

    Shared across routing functions — called once per KARMA cycle.
    """
    from city.registry import SVC_CARTRIDGE_FACTORY

    factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
    if factory is None:
        return {}
    specs: dict[str, dict] = {}
    for name in factory.list_generated():
        spec = factory.get_spec(name)
        if spec is not None:
            specs[name] = spec
    return specs


def _record_pr_event(ctx: PhaseContext, issue_number: int, pr: object) -> None:
    """Record a PR creation event for MOKSHA to pick up."""
    ctx.recent_events.append(
        {
            "type": "pr_created",
            "issue_number": issue_number,
            "pr_url": pr.pr_url,
            "branch": pr.branch,
            "commit_hash": pr.commit_hash,
            "heartbeat": ctx.heartbeat_count,
        }
    )
