"""
KARMA Phase — Operations, Heal Intents, Council Governance.

Processes gateway queue, sankalpa strategic intents, heal failing contracts
via executor, and council auto-vote + proposal execution.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

import time as _time

from config import get_config

from city.cognition import emit_event
from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.PHASES.KARMA")

# ── Cognitive Action Map ──────────────────────────────────────────────
# Maps buddhi function × agent capability → existing city operation.
# No new infrastructure — reuses council, sankalpa, nadi, audit, immune.
_ACTION_MAP: dict[str, dict[str, str]] = {
    "BRAHMA": {  # Create
        "propose": "council_propose",
        "create": "create_mission",
        "observe": "emit_observation",
    },
    "VISHNU": {  # Sustain
        "observe": "emit_observation",
        "monitor": "emit_observation",
        "relay": "nadi_dispatch",
    },
    "SHIVA": {  # Transform
        "validate": "trigger_audit",
        "execute": "trigger_heal",
        "transform": "trigger_audit",
    },
}


def _learn(ctx: PhaseContext, source: str, action: str, *, success: bool) -> None:
    """Record a Hebbian learning outcome if learning is wired."""
    if ctx.learning is not None:
        ctx.learning.record_outcome(source, action, success)


def execute(ctx: PhaseContext) -> list[str]:
    """KARMA: Process gateway queue, sankalpa, heal, council cycle."""
    operations: list[str] = []

    # Mark citizens active (redundant with DHARMA, but keeps the set warm
    # for intra-run KARMA operations that check active_agents)
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

    # Collect agent specs ONCE for discussion routing (reused below)
    all_specs = _get_all_specs(ctx)
    all_inventories = _get_all_inventories(ctx)

    # Reset discussions per-cycle counter
    if ctx.discussions is not None:
        ctx.discussions.reset_cycle()

    for item in queue_items:
        source = item.get("source", "unknown")
        text = item.get("text", "")
        conversation_id = item.get("conversation_id", "")
        from_agent = item.get("from_agent", "")

        # Agent introduction: bypass gateway processing (pure transport)
        if source == "agent_intro":
            _handle_agent_intro(ctx, item, all_specs, operations)
            continue

        try:
            # Enrich text with KG context if available
            enriched_text = f"{text}\n\n{kg_context}" if kg_context else text
            result = ctx.gateway.process(enriched_text, source)

            # Discussion messages: route to agents, post response
            discussion_number = item.get("discussion_number")
            if discussion_number and source == "discussion":
                _handle_discussion_item(
                    ctx,
                    item,
                    result,
                    all_specs,
                    all_inventories,
                    operations,
                )
                continue

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
    # idle_minutes = real wall-clock gap between KARMA executions.
    # Cron fires every 15min, 4 cycles/run, KARMA = cycle 2 → runs once per 15min.
    # Accumulates: heartbeat_count / 4 gives completed rotations × 15min.
    if ctx.sankalpa is not None:
        rotations = ctx.heartbeat_count // 4
        idle_minutes = rotations * 15
        intents = ctx.sankalpa.think(idle_minutes=idle_minutes)
        for intent in intents:
            operations.append(f"sankalpa_intent:{intent.title}")
            logger.info("KARMA: Sankalpa intent — %s (idle=%dmin)", intent.title, idle_minutes)

    # Cartridge routing: capability-scored agent dispatch
    _route_to_cartridges(ctx, operations, all_specs, all_inventories)

    # Issue-driven missions: process strategyless missions from DHARMA
    if ctx.sankalpa is not None:
        _process_issue_missions(ctx, operations, all_specs, all_inventories)

    # Marketplace: auto-list surplus + need-driven auto-match
    _process_marketplace(ctx, operations, all_specs, all_inventories)

    # Layer 4: Execute HEAL intents on failing contracts (CAPABILITY GATED)
    if ctx.executor is not None and ctx.contracts is not None:
        from city.mission_router import authorize_mission

        heal_authorized = authorize_mission("heal_", all_specs, ctx.active_agents, all_inventories)
        if not heal_authorized:
            logger.info(
                "KARMA: No agent with validate capability — executor handles heal as system service"
            )
        # Gate is advisory: IntentExecutor is a system service, not an agent.
        # Even without a citizen holding 'validate', the executor heals.
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

    # Cross-post terminal mission results happens in MOKSHA (reflection phase)
    # MOKSHA marks missions as "reported" — doing it here would double-post.

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

    # Marketplace governance actions (Phase 8)
    if action_type in ("set_commission", "freeze_market", "unfreeze_market"):
        if ctx.council is not None:
            success = ctx.council.apply_marketplace_action(proposal.action)
            if success:
                logger.info(
                    "Proposal %s: marketplace action %s applied",
                    proposal.id,
                    action_type,
                )
            return success
        return False

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
    ctx: PhaseContext,
    operations: list[str],
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]] | None = None,
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
            # CAPABILITY GATE (advisory): log if no agent qualifies, but executor handles it
            if not authorize_mission(mission.id, all_specs, ctx.active_agents, all_inventories):
                logger.info(
                    "KARMA: No agent with execute capability — executor handles exec mission %s as system service",
                    mission.id,
                )

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
        if not authorize_mission(mission.id, all_specs, ctx.active_agents, all_inventories):
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
    ctx: PhaseContext,
    operations: list[str],
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]] | None = None,
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

    # Per-cycle throttle: limit cognitive actions to prevent runaway
    autonomy_cfg = get_config().get("autonomy", {})
    max_cognitive_actions = autonomy_cfg.get("max_actions_per_cycle", 3)
    cognitive_count = 0

    # Discussion action posts: rate-limited per cycle
    disc_cfg = get_config().get("discussions", {})
    max_action_posts = disc_cfg.get("max_action_posts_per_cycle", 1)
    action_post_count = 0

    for mission in active:
        # Skip types handled by dedicated processors (which have their own gates)
        if mission.id.startswith(("issue_", "exec_")):
            continue

        result = route_mission(mission, all_specs, ctx.active_agents, all_inventories)

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
                cognitive_action = cartridge.process(mission.description)

                if cognitive_action.get("status") != "cognized":
                    operations.append(f"routed_passive:{agent_name}:{mission.id}")
                    continue

                # Throttle: max cognitive actions per cycle
                if cognitive_count >= max_cognitive_actions:
                    operations.append(f"cognition_throttled:{agent_name}")
                    continue

                # Act on cognitive decision
                operation_name = _execute_cognitive_action(
                    ctx, cognitive_action, mission, operations,
                )
                executed = operation_name is not None
                _learn(ctx, f"cognition:{agent_name}", cognitive_action["function"], success=executed)

                if executed:
                    cognitive_count += 1

                    # Surface cognitive action in Discussions (rate-limited)
                    if (
                        ctx.discussions is not None
                        and not ctx.offline_mode
                        and action_post_count < max_action_posts
                    ):
                        spec = _get_agent_spec(ctx, agent_name)
                        if spec is not None:
                            cognitive_action["_operation"] = operation_name
                            posted = ctx.discussions.post_agent_action(
                                spec, cognitive_action, mission.id,
                            )
                            if posted:
                                action_post_count += 1
                                operations.append(f"disc_action:{agent_name}:{cognitive_action['function']}")

                operations.append(
                    f"routed:{agent_name}:{mission.id}:score={result['score']:.2f}"
                    f":cognized={cognitive_action['function']}"
                )
                logger.info(
                    "KARMA: Routed %s \u2192 %s (score=%.2f, function=%s, executed=%s)",
                    mission.id,
                    agent_name,
                    result["score"],
                    cognitive_action["function"],
                    executed,
                )
        except Exception as e:
            logger.warning(
                "KARMA: Agent %s failed for mission %s: %s",
                agent_name,
                mission.id,
                e,
            )


def _execute_cognitive_action(
    ctx: PhaseContext,
    action: dict,
    mission: object,
    operations: list[str],
) -> str | None:
    """Map CognitiveAction -> existing city operation. Execute it.

    Gates: confidence (synapse weight), prana (cell alive), capability map.
    Returns operation name on success, None on failure.
    """
    function = action.get("function", "")
    caps = action.get("capabilities", [])
    agent_name = action.get("agent", "")
    autonomy_cfg = get_config().get("autonomy", {})

    # Confidence gate: skip if historical weight too low
    min_confidence = autonomy_cfg.get("min_confidence", 0.2)
    if ctx.learning is not None:
        confidence = ctx.learning.get_confidence(f"cognition:{agent_name}", function)
        if confidence < min_confidence:
            operations.append(
                f"cognition_low_confidence:{agent_name}:{function}:{confidence:.2f}"
            )
            return None

    # Prana gate: agent must be alive to act
    cell = ctx.pokedex.get_cell(agent_name)
    if cell is None or not cell.is_alive:
        return None

    # Find matching operation via capability x function map
    function_map = _ACTION_MAP.get(function, {})
    operation = None
    for cap in caps:
        if cap in function_map:
            operation = function_map[cap]
            break

    if operation is None:
        operations.append(f"cognition_no_op:{agent_name}:{function}")
        return None

    # Execute the operation
    success = False
    if operation == "council_propose" and ctx.council is not None:
        success = _cognitive_propose(ctx, action, mission)
    elif operation == "create_mission" and ctx.sankalpa is not None:
        success = _cognitive_create_mission(ctx, action, mission)
    elif operation == "emit_observation":
        emit_event(
            "OBSERVATION",
            agent_name,
            action.get("composed", ""),
            {
                "function": function,
                "chapter": action.get("chapter", 0),
                "mission": mission.id,
            },
        )
        success = True
    elif operation == "nadi_dispatch" and ctx.agent_nadi is not None:
        success = _cognitive_nadi_dispatch(ctx, action, agent_name)
    elif operation == "trigger_audit" and ctx.audit is not None:
        try:
            ctx.audit.run_all()
            success = True
        except Exception:
            success = False
    elif operation == "trigger_heal" and ctx.immune is not None:
        diagnosis = ctx.immune.diagnose(f"mission:{mission.id}")
        if diagnosis.healable:
            result = ctx.immune.heal(diagnosis)
            success = result.success

    if success:
        operations.append(f"cognition:{agent_name}:{function}\u2192{operation}")
        emit_event(
            "ACTION",
            agent_name,
            f"Cognitive action: {operation}",
            {
                "action": "cognitive_exec",
                "function": function,
                "operation": operation,
                "mission": mission.id,
                "composed": action.get("composed", ""),
            },
        )
        return operation

    return None


def _cognitive_propose(ctx: PhaseContext, action: dict, mission: object) -> bool:
    """Submit a council proposal from cognitive action."""
    if ctx.council is None or ctx.council.elected_mayor is None:
        return False

    from city.council import ProposalType

    ctx.council.propose(
        title=f"Agent Proposal: {action.get('composed', mission.name)[:60]}",
        description=mission.description,
        proposer=action["agent"],
        proposal_type=ProposalType.POLICY,
        action={"type": "improve", "source": "cognitive"},
        timestamp=_time.time(),
    )
    return True


def _cognitive_create_mission(ctx: PhaseContext, action: dict, mission: object) -> bool:
    """Create an improvement mission from cognitive action."""
    from city.missions import create_improvement_mission

    proposal = type(
        "Proposal",
        (),
        {
            "id": f"cog_{mission.id}",
            "title": action.get("composed", "")[:60] or mission.name,
            "description": mission.description,
        },
    )()
    create_improvement_mission(ctx, proposal)
    return True


def _cognitive_nadi_dispatch(ctx: PhaseContext, action: dict, agent_name: str) -> bool:
    """Broadcast observation to AgentNadi for other agents to see."""
    composed = action.get("composed", "")
    function = action.get("function", "")
    chapter = action.get("chapter", 0)
    text = f"[{function}] ch.{chapter}: {composed}" if composed else f"[{function}] ch.{chapter}"
    ctx.agent_nadi.broadcast(agent_name, text)
    return True


def _handle_discussion_item(
    ctx: PhaseContext,
    item: dict,
    result: dict,
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]],
    operations: list[str],
) -> None:
    """Route a discussion queue item to an agent and post response.

    Two routing paths:
    - Direct: @mention → known agent (bypass scoring)
    - Capability: buddhi intent → best-fit agent via scoring
    """
    from city.discussions_inbox import (
        DiscussionSignal,
        classify_discussion_intent,
        dispatch_discussion,
    )

    discussion_number = item["discussion_number"]
    direct_agent = item.get("direct_agent", "")

    # Build signal
    signal = DiscussionSignal(
        discussion_number=discussion_number,
        title=item.get("discussion_title", ""),
        body=item.get("text", ""),
        author=item.get("from_agent", ""),
        mentioned_agents=[direct_agent] if direct_agent else [],
    )

    agent_name: str | None = None
    agent_spec: dict | None = None

    if direct_agent:
        # DIRECT ROUTING — @mention bypass (but still tier-gated below)
        spec = all_specs.get(direct_agent)
        if spec is not None:
            from city.mission_router import MISSION_REQUIREMENTS, check_capability_gate

            req = MISSION_REQUIREMENTS.get("disc_", {})
            if check_capability_gate(spec, req):
                agent_name = direct_agent
                agent_spec = spec
            else:
                logger.info(
                    "KARMA: @%s blocked by tier gate for discussion #%d",
                    direct_agent,
                    discussion_number,
                )
        else:
            logger.debug(
                "KARMA: @%s not in specs for discussion #%d",
                direct_agent,
                discussion_number,
            )
    else:
        # CAPABILITY ROUTING — standard scoring
        intent = classify_discussion_intent(result)
        agent_name, agent_spec = _route_discussion_to_agent(
            ctx,
            intent,
            all_specs,
            all_inventories,
        )

    if agent_name is None or agent_spec is None:
        operations.append(f"disc_no_agent:#{discussion_number}")
        _learn(ctx, "discussion", "route", success=False)
        return

    # Build response
    city_stats = ctx.pokedex.stats()
    response = dispatch_discussion(signal, result, agent_spec, city_stats)

    # Rate limit + post
    if ctx.discussions is not None and ctx.discussions.can_respond(discussion_number):
        if not ctx.offline_mode:
            posted = ctx.discussions.comment(discussion_number, response.body)
        else:
            posted = False
            logger.info("KARMA: Discussion #%d response (offline, not posted)", discussion_number)

        if posted:
            ctx.discussions.record_response(discussion_number)
            emit_event(
                "ACTION",
                agent_name,
                f"Discussion #{discussion_number} response",
                {
                    "action": "discussion_reply",
                    "discussion_number": discussion_number,
                    "agent": agent_name,
                    "intent": result.get("buddhi_function", "?"),
                },
            )
            operations.append(f"disc_replied:{agent_name}:#{discussion_number}")
            _learn(ctx, "discussion", "reply", success=True)
        else:
            operations.append(f"disc_post_failed:#{discussion_number}")
            _learn(ctx, "discussion", "reply", success=False)
    else:
        operations.append(f"disc_rate_limited:#{discussion_number}")


def _handle_agent_intro(
    ctx: PhaseContext,
    item: dict,
    all_specs: dict[str, dict],
    operations: list[str],
) -> None:
    """Post an agent self-introduction to the Discussions registry thread.

    SSOT: Pokedex `has_asset("word_token", "introduced")` is the truth.
    Asset granted ONLY after successful post. Rate-limited agents stay
    un-introduced and will be retried next GENESIS cycle.
    """
    agent_name = item.get("agent_name", "")
    if not agent_name:
        return

    # Double-check: already introduced? (Nadi may have stale items)
    if ctx.pokedex.has_asset(agent_name, "word_token", "introduced"):
        return

    spec = all_specs.get(agent_name)
    if spec is None:
        # Try generating spec on the fly
        from city.registry import SVC_CARTRIDGE_FACTORY

        factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
        if factory is not None:
            factory.generate(agent_name)
            spec = factory.get_spec(agent_name)

    if spec is None:
        operations.append(f"intro_no_spec:{agent_name}")
        return

    if ctx.discussions is not None and not ctx.offline_mode:
        posted = ctx.discussions.post_agent_intro(spec)
        if posted:
            ctx.pokedex.grant_asset(
                agent_name,
                "word_token",
                "introduced",
                source="discussion_intro",
            )
            operations.append(f"agent_intro:{agent_name}")
            emit_event(
                "ACTION",
                agent_name,
                f"Introduced in Discussions",
                {
                    "action": "discussion_intro",
                    "agent": agent_name,
                },
            )
            _learn(ctx, "agent_intro", "post", success=True)
        else:
            operations.append(f"intro_rate_limited:{agent_name}")


def _route_discussion_to_agent(
    ctx: PhaseContext,
    intent: str,
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]],
) -> tuple[str | None, dict | None]:
    """Find the best agent for a discussion intent via capability scoring.

    Hard gate on required_caps from INTENT_REQUIREMENTS, then score via
    shared score_agent_for_discussion() (city.diagnostics).
    """
    from city.diagnostics import score_agent_for_discussion
    from city.discussions_inbox import INTENT_REQUIREMENTS
    from city.mission_router import check_capability_gate

    reqs = INTENT_REQUIREMENTS.get(intent, INTENT_REQUIREMENTS["observe"])

    # Build a MissionRequirement-compatible dict for the tier gate
    gate_req = {
        "required": reqs.get("required_caps", []),
        "preferred": [],
        "min_tier": "contributor",
    }

    best_name: str | None = None
    best_spec: dict | None = None
    best_score = -1.0

    for name, spec in all_specs.items():
        if name not in ctx.active_agents:
            continue

        inventory = all_inventories.get(name)
        if not check_capability_gate(spec, gate_req, inventory):
            continue

        score = score_agent_for_discussion(spec, intent)

        if score > best_score:
            best_score = score
            best_name = name
            best_spec = spec

    if best_name is not None:
        logger.info(
            "KARMA: Discussion routed to %s (score=%.2f, intent=%s)",
            best_name,
            best_score,
            intent,
        )
    return best_name, best_spec


def _get_agent_spec(ctx: PhaseContext, agent_name: str) -> dict | None:
    """Get a single agent's spec from CartridgeFactory."""
    from city.registry import SVC_CARTRIDGE_FACTORY

    factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
    if factory is None:
        return None
    return factory.get_spec(agent_name)


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


def _get_all_inventories(ctx: PhaseContext) -> dict[str, list[dict]]:
    """Collect inventories for all active agents.

    Shared across routing functions — called once per KARMA cycle.
    Returns {agent_name: [asset_dicts]} for agents with assets.
    """
    inventories: dict[str, list[dict]] = {}
    for name in ctx.active_agents:
        inv = ctx.pokedex.get_inventory(name)
        if inv:
            inventories[name] = inv
    return inventories


def _process_marketplace(
    ctx: PhaseContext,
    operations: list[str],
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]] | None = None,
) -> None:
    """Marketplace: expire stale orders, auto-list surplus, need-driven auto-match.

    Anti-Pac-Man: agents only buy capabilities they NEED (mission-blocked
    or domain-aligned). Rich agents cannot blindly hoard.
    """
    # Check marketplace governance freeze (Phase 8)
    if ctx.council is not None and ctx.council.is_market_frozen:
        operations.append("marketplace:frozen_by_council")
        return

    from city.seed_constants import WORKER_VISA_STIPEND

    # Step 1: Expire stale orders
    expired = ctx.pokedex.expire_orders(ctx.heartbeat_count)
    if expired:
        operations.append(f"marketplace:expired={expired}")

    # Step 2: Auto-list surplus capability_tokens (quantity > 1 → sell excess)
    for agent_name in ctx.active_agents:
        inv = (all_inventories or {}).get(agent_name, [])
        for asset in inv:
            if asset["asset_type"] == "capability_token" and asset["quantity"] > 1:
                surplus = asset["quantity"] - 1
                ctx.pokedex.create_order(
                    agent_name,
                    "capability_token",
                    asset["asset_id"],
                    quantity=surplus,
                    price=WORKER_VISA_STIPEND,
                    heartbeat=ctx.heartbeat_count,
                )
                operations.append(f"marketplace:listed={asset['asset_id']}x{surplus}:{agent_name}")

    # Step 3: Need-driven auto-match (anti-Pac-Man)
    open_orders = ctx.pokedex.get_active_orders(asset_type="capability_token")
    if not open_orders:
        return

    # Build mission-blocked needs (caps required by active missions)
    mission_needs: set[str] = set()
    if ctx.sankalpa is not None:
        try:
            from city.mission_router import get_requirement

            active_missions = ctx.sankalpa.registry.get_active_missions()
            for mission in active_missions:
                req = get_requirement(mission.id)
                for cap in req["required"]:
                    mission_needs.add(cap)
        except Exception:
            pass

    from city.guardian_spec import ELEMENT_CAPABILITIES

    for agent_name in ctx.active_agents:
        spec = all_specs.get(agent_name)
        if spec is None:
            continue

        # Agent's current capabilities (static + inventory tokens)
        agent_caps = set(spec.get("capabilities", []))
        inv = (all_inventories or {}).get(agent_name, [])
        for asset in inv:
            if asset.get("asset_type") == "capability_token":
                agent_caps.add(asset["asset_id"])

        # Build NEEDS: mission-blocked + domain-aligned only
        needed_caps: set[str] = set()

        # 1. Mission-blocked: caps required by active missions that agent lacks
        for cap in mission_needs:
            if cap not in agent_caps:
                needed_caps.add(cap)

        # 2. Domain-aligned: caps from agent's element family
        element = spec.get("element", "")
        domain_caps = set(ELEMENT_CAPABILITIES.get(element, []))
        for cap in domain_caps:
            if cap not in agent_caps:
                needed_caps.add(cap)

        if not needed_caps:
            continue

        # Match: only buy what agent NEEDS
        for order in open_orders:
            if order["status"] != "open":
                continue
            if order["seller"] == agent_name:
                continue
            if order["asset_id"] not in needed_caps:
                continue

            buyer_balance = ctx.pokedex._bank.get_balance(agent_name)
            if buyer_balance < order["price"]:
                continue

            commission_pct = None
            if ctx.council is not None:
                commission_pct = ctx.council.effective_commission
            receipt = ctx.pokedex.fill_order(
                order["id"],
                agent_name,
                ctx.heartbeat_count,
                commission_pct=commission_pct,
            )
            if receipt:
                operations.append(
                    f"marketplace:trade={order['asset_id']}:"
                    f"{order['seller']}\u2192{agent_name}:"
                    f"price={receipt['price']}"
                )
                logger.info(
                    "KARMA: Trade filled \u2014 %s bought %s from %s for %d prana",
                    agent_name,
                    order["asset_id"],
                    order["seller"],
                    receipt["price"],
                )
                break  # one trade per agent per cycle


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
