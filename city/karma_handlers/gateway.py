"""Gateway Handler — Drain nadi/queue, process via gateway, route discussions/DMs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.cognition import emit_event
from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.GATEWAY")


def _learn(ctx: PhaseContext, source: str, action: str, *, success: bool) -> None:
    """Record a Hebbian learning outcome if learning is wired."""
    if ctx.learning is not None:
        ctx.learning.record_outcome(source, action, success)


def _get_all_specs(ctx: PhaseContext) -> dict[str, dict]:
    """Collect all agent specs from CartridgeFactory."""
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
    """Collect inventories for all active agents."""
    inventories: dict[str, list[dict]] = {}
    for name in ctx.active_agents:
        inv = ctx.pokedex.get_inventory(name)
        if inv:
            inventories[name] = inv
    return inventories


class GatewayHandler(BaseKarmaHandler):
    """Drain nadi/gateway queue, process items, route discussions and DMs.

    Stores all_specs and all_inventories on ctx for downstream handlers.
    """

    @property
    def name(self) -> str:
        return "gateway"

    @property
    def priority(self) -> int:
        return 20

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.registry import SVC_SPAWNER

        # Mark citizens active
        spawner = ctx.registry.get(SVC_SPAWNER)
        if spawner is not None:
            active_count = spawner.mark_citizens_active(ctx.active_agents)
            if active_count:
                operations.append(f"citizens_active:{active_count}")

        # Cognition: compile KG context
        kg_context = ""
        if ctx.knowledge_graph is not None:
            from city.cognition import compile_context
            kg_context = compile_context("process gateway queue operations")

        # Drain from Nadi (priority-sorted) + fallback gateway_queue
        queue_items: list[dict] = []
        if ctx.city_nadi is not None:
            queue_items = ctx.city_nadi.drain()
        while ctx.gateway_queue:
            queue_items.append(ctx.gateway_queue.pop(0))

        # Collect agent specs ONCE for this cycle (shared via ctx)
        all_specs = _get_all_specs(ctx)
        all_inventories = _get_all_inventories(ctx)
        ctx._all_specs = all_specs  # type: ignore[attr-defined]
        ctx._all_inventories = all_inventories  # type: ignore[attr-defined]

        # Reset discussions per-cycle counter
        if ctx.discussions is not None:
            ctx.discussions.reset_cycle()

        for item in queue_items:
            source = item.get("source", "unknown")
            text = item.get("text", "")
            conversation_id = item.get("conversation_id", "")
            from_agent = item.get("from_agent", "")

            # Agent introduction: bypass gateway processing
            if source == "agent_intro":
                _handle_agent_intro(ctx, item, all_specs, operations)
                continue

            try:
                enriched_text = f"{text}\n\n{kg_context}" if kg_context else text
                result = ctx.gateway.process(enriched_text, source)

                discussion_number = item.get("discussion_number")
                if discussion_number and source == "discussion":
                    _handle_discussion_item(
                        ctx, item, result, all_specs, all_inventories, operations,
                    )
                    continue

                # DM messages
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
                            response.conversation_id, response.text,
                        )
                        operations.append(f"dm_replied:{from_agent}:seed={result['seed']}")
                        _learn(ctx, source, "dm_reply", success=True)
                    except Exception as e:
                        operations.append(f"dm_reply_failed:{from_agent}:{e}")
                        _learn(ctx, source, "dm_reply", success=False)
                        logger.warning("KARMA: DM reply failed for %s: %s", from_agent, e)
                else:
                    operations.append(f"processed:{source}:seed={result['seed']}")
                    _learn(ctx, source, "process", success=True)
            except Exception as e:
                operations.append(f"error:{source}:{e}")
                _learn(ctx, source, "process", success=False)
                logger.warning("KARMA: Gateway processing failed for %s: %s", source, e)

        # Log learning confidence
        if ctx.learning is not None and queue_items:
            for item in queue_items:
                src = item.get("source", "unknown")
                confidence = ctx.learning.get_confidence(src, "process")
                if confidence < 0.2:
                    logger.warning("KARMA: Low confidence for %s→process (%.2f)", src, confidence)


# ── Discussion / Intro Routing ───────────────────────────────────────

def _handle_discussion_item(
    ctx: PhaseContext,
    item: dict,
    result: dict,
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]],
    operations: list[str],
) -> None:
    """Route a discussion queue item to an agent and post response."""
    from city.discussions_commands import (
        ConversationTracker,
        execute_command,
        extract_brain_feedback,
        parse_commands,
    )
    from city.discussions_inbox import (
        DiscussionSignal,
        classify_discussion_intent,
        dispatch_discussion,
    )
    from city.karma_handlers.brain_health import brain_budget_ok

    discussion_number = item["discussion_number"]
    direct_agent = item.get("direct_agent", "")
    comment_author = item.get("from_agent", "")
    comment_body = item.get("text", "")
    comment_id = item.get("comment_id", "")

    # Phase 6B: Parse and EXECUTE inbound commands
    commands = parse_commands(
        comment_body,
        author=comment_author,
        discussion_number=discussion_number,
        comment_id=comment_id,
    )
    command_handled = False
    for cmd in commands:
        if cmd.is_valid:
            operations.append(
                f"disc_cmd:/{cmd.command}:#{discussion_number}:@{cmd.author}"
            )
            response_body = execute_command(cmd, ctx)
            if response_body and ctx.discussions is not None and not ctx.offline_mode:
                if ctx.discussions.can_respond(discussion_number):
                    posted = ctx.discussions.comment(discussion_number, response_body)
                    if posted:
                        ctx.discussions.record_response(discussion_number)
                        operations.append(
                            f"cmd_replied:/{cmd.command}:#{discussion_number}"
                        )
                        if ctx.thread_state is not None and comment_id:
                            ctx.thread_state.mark_replied(comment_id)
                        command_handled = True
                        _learn(ctx, "discussion", "command", success=True)
                    else:
                        operations.append(
                            f"cmd_post_failed:/{cmd.command}:#{discussion_number}"
                        )
                        _learn(ctx, "discussion", "command", success=False)
                else:
                    operations.append(f"cmd_rate_limited:#{discussion_number}")

    # If commands were executed and posted, skip normal agent routing
    if command_handled:
        return

    # Phase 6B: Track conversation state (persistent via registry)
    tracker = ctx.conversation_tracker
    if tracker is None:
        tracker = ConversationTracker()
        ctx._conversation_tracker = tracker  # type: ignore[attr-defined]
    thread = tracker.get_or_create(discussion_number)
    for cmd in commands:
        thread.record_command(cmd)

    # Phase 6D: Feed human replies into BrainMemory as external feedback
    if ctx.brain_memory is not None and comment_author:
        feedback = extract_brain_feedback(
            comment_body,
            author=comment_author,
            discussion_number=discussion_number,
            heartbeat=ctx.heartbeat_count,
        )
        if feedback is not None:
            ctx.brain_memory.record_external(feedback)
            thread.brain_feedback_count += 1
            operations.append(
                f"brain_feedback:#{discussion_number}:@{comment_author}"
            )

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
                    direct_agent, discussion_number,
                )
        else:
            logger.debug(
                "KARMA: @%s not in specs for discussion #%d",
                direct_agent, discussion_number,
            )
    else:
        intent = classify_discussion_intent(result)
        agent_name, agent_spec = _route_discussion_to_agent(
            ctx, intent, all_specs, all_inventories, discussion_text=item.get("text", ""),
        )

    if agent_name is None or agent_spec is None:
        operations.append(f"disc_no_agent:#{discussion_number}")
        _learn(ctx, "discussion", "route", success=False)
        return

    # Encode semantic signal
    disc_semantic_signal = None
    try:
        from city.signal_encoder import encode_signal
        from city.jiva import derive_jiva
        agent_jiva = derive_jiva(agent_name)
        disc_semantic_signal = encode_signal(signal.body or signal.title, agent_jiva)
    except Exception:
        pass

    # Brain comprehension (budget-limited)
    brain_thought = None
    brain = ctx.brain
    if brain is not None and brain_budget_ok(ctx):
        from city.brain_context import build_context_snapshot
        from city.semantic import compose_prose
        snapshot = build_context_snapshot(ctx)
        brain_thought = brain.comprehend_discussion(
            discussion_text=item.get("text", ""),
            agent_spec=agent_spec,
            gateway_result=result,
            signal_reading=compose_prose(disc_semantic_signal) if disc_semantic_signal else "",
            snapshot=snapshot,
        )
        if brain_thought is not None:
            ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1
            operations.append(
                f"brain_disc:{agent_name}:#{discussion_number}"
                f":intent={brain_thought.intent.value}"
                f":confidence={brain_thought.confidence:.2f}"
            )
            # Phase 6B+6C-8: Act on brain action_hints (authorization-gated)
            if brain_thought.action_hint:
                _execute_action_hint(
                    ctx, brain_thought, discussion_number, agent_name,
                    operations, comment_author=comment_author,
                    comment_id=comment_id,
                )

    # 7A-4: Run Cartridge process() if available — agent-specific cognition
    cartridge_cognition = None
    try:
        from city.registry import SVC_CARTRIDGE_FACTORY
        factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
        if factory is not None:
            cartridge = factory.get(agent_name)
            if cartridge is not None and hasattr(cartridge, "process"):
                cartridge_cognition = cartridge.process(
                    item.get("text", "") or signal.title
                )
                operations.append(f"cartridge_process:{agent_name}:#{discussion_number}")
    except Exception as e:
        logger.debug("Cartridge process() skipped for %s: %s", agent_name, e)

    # Build response
    city_stats = ctx.pokedex.stats()
    response = dispatch_discussion(
        signal, result, agent_spec, city_stats,
        semantic_signal=disc_semantic_signal,
        brain_thought=brain_thought,
        cartridge_cognition=cartridge_cognition,
    )

    # Broadcast signal to agent nadi
    if disc_semantic_signal is not None and ctx.agent_nadi is not None:
        ctx.agent_nadi.broadcast(agent_name, response.body[:200])

    # Rate limit + post
    if ctx.discussions is not None and ctx.discussions.can_respond(discussion_number):
        if not ctx.offline_mode:
            posted = ctx.discussions.comment(discussion_number, response.body)
        else:
            posted = False
            logger.info("KARMA: Discussion #%d response (offline, not posted)", discussion_number)

        if posted:
            ctx.discussions.record_response(discussion_number)
            thread.record_response(ctx.heartbeat_count)
            # P8: Record agent response in ThreadState lifecycle engine
            if ctx.thread_state is not None:
                ctx.thread_state.record_agent_response(discussion_number)
                # Close the loop: mark originating comment as replied
                origin_comment_id = item.get("comment_id", "")
                if origin_comment_id:
                    ctx.thread_state.mark_replied(origin_comment_id)
            emit_event(
                "ACTION", agent_name, f"Discussion #{discussion_number} response",
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
    """Post an agent self-introduction to the Discussions registry thread."""
    agent_name = item.get("agent_name", "")
    if not agent_name:
        return

    if ctx.pokedex.has_asset(agent_name, "word_token", "introduced"):
        return

    spec = all_specs.get(agent_name)
    if spec is None:
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
                agent_name, "word_token", "introduced", source="discussion_intro",
            )
            operations.append(f"agent_intro:{agent_name}")
            emit_event(
                "ACTION", agent_name, "Introduced in Discussions",
                {"action": "discussion_intro", "agent": agent_name},
            )
            _learn(ctx, "agent_intro", "post", success=True)
        else:
            operations.append(f"intro_rate_limited:{agent_name}")


# 6C-8: Action hints that mutate state require citizen/operator access.
# Read-only hints are allowed from anyone.
_READ_ONLY_HINTS = frozenset({"run_status"})
_READ_ONLY_PREFIXES = ("check_health:",)


def _authorize_action_hint(
    ctx: PhaseContext, hint: str, author: str,
) -> bool:
    """Check if comment author is authorized to trigger this action_hint.

    Read-only hints (run_status, check_health) → always allowed.
    State-mutating hints (create_mission, assign_agent, escalate, etc.) →
    requires the author to be a registered citizen OR operator.
    """
    # Read-only hints pass unconditionally
    if hint in _READ_ONLY_HINTS:
        return True
    for prefix in _READ_ONLY_PREFIXES:
        if hint.startswith(prefix):
            return True

    # State-mutating: author must be a citizen or registered operator
    if not author:
        return False
    # Check citizen status
    agent_data = ctx.pokedex.get(author)
    if agent_data and agent_data.get("status") in ("citizen", "active"):
        return True
    # Check operator table
    operator = ctx.pokedex.get_operator(author)
    if operator is not None:
        return True
    return False


# 6C-9: Track executed action_hints per comment_id to prevent duplicate fires on edits.
_executed_hints: dict[str, str] = {}  # comment_id → last executed hint
_EXECUTED_HINTS_MAX = 500


def _execute_action_hint(
    ctx: PhaseContext,
    thought: object,
    discussion_number: int,
    agent_name: str,
    operations: list[str],
    *,
    comment_author: str = "",
    comment_id: str = "",
) -> None:
    """Act on a Brain action_hint from discussion comprehension.

    6C-8: Authorization-gated — state-mutating hints require citizen/operator.
    6C-9: Edit-dedup — same hint for same comment_id is skipped.
    """
    hint = thought.action_hint
    if not hint:
        return

    # 6C-8: Authorization gate
    if not _authorize_action_hint(ctx, hint, comment_author):
        operations.append(
            f"brain_hint_denied:{hint[:30]}:@{comment_author}:#{discussion_number}"
        )
        logger.info(
            "KARMA: action_hint '%s' denied for @%s (not citizen/operator)",
            hint[:40], comment_author,
        )
        return

    # 6C-9: Edit dedup — skip if same hint already executed for this comment
    if comment_id:
        prev_hint = _executed_hints.get(comment_id)
        if prev_hint == hint:
            operations.append(
                f"brain_hint_dedup:{hint[:30]}:{comment_id[:12]}:#{discussion_number}"
            )
            return
        # Track this execution (bounded dict)
        if len(_executed_hints) >= _EXECUTED_HINTS_MAX:
            # Evict oldest entries (first 100)
            for old_key in list(_executed_hints)[:100]:
                del _executed_hints[old_key]
        _executed_hints[comment_id] = hint

    if hint.startswith("create_mission:"):
        desc = hint[len("create_mission:"):].strip()
        if desc and ctx.sankalpa is not None:
            from city.missions import create_discussion_mission
            mission_id = create_discussion_mission(
                ctx, discussion_number, desc, thought.intent.value,
            )
            if mission_id:
                operations.append(f"brain_hint_mission:{mission_id}:#{discussion_number}")
            return

    if hint.startswith("investigate:"):
        topic = hint[len("investigate:"):].strip()
        if topic and ctx.sankalpa is not None:
            from city.missions import create_discussion_mission
            mission_id = create_discussion_mission(
                ctx, discussion_number, f"Investigate: {topic}", "inquiry",
            )
            if mission_id:
                operations.append(f"brain_hint_investigate:{mission_id}:#{discussion_number}")
            return

    if hint.startswith("flag_bottleneck:"):
        domain = hint[len("flag_bottleneck:"):].strip()
        if hasattr(ctx, "reactor") and ctx.reactor is not None:
            try:
                ctx.reactor.emit_pain(
                    source="brain_discussion",
                    severity=0.5,
                    detail=f"Bottleneck flagged in {domain} from #{discussion_number}",
                )
                operations.append(f"brain_hint_bottleneck:{domain}:#{discussion_number}")
            except Exception as e:
                logger.warning("Brain hint flag_bottleneck failed: %s", e)
            return

    if hint == "run_status":
        operations.append(f"brain_hint_run_status:#{discussion_number}")
        return

    if hint.startswith("check_health:"):
        domain = hint[len("check_health:"):].strip()
        if hasattr(ctx, "reactor") and ctx.reactor is not None:
            try:
                ctx.reactor.emit_pain(
                    source="brain_discussion",
                    severity=0.3,
                    detail=f"Health check requested for {domain} from #{discussion_number}",
                )
            except Exception as e:
                logger.warning("Brain hint check_health failed: %s", e)
        operations.append(f"brain_hint_check_health:{domain}:#{discussion_number}")
        return

    if hint.startswith("assign_agent:"):
        parts = hint[len("assign_agent:"):].split(":", 1)
        target_agent = parts[0].strip() if parts else ""
        task_desc = parts[1].strip() if len(parts) > 1 else ""
        if target_agent and task_desc:
            from city.missions import create_community_mission
            mission_id = create_community_mission(
                ctx, discussion_number, f"Assigned: {task_desc[:60]}", "propose",
            )
            if mission_id:
                operations.append(
                    f"brain_hint_assign:{target_agent}:{mission_id}:#{discussion_number}"
                )
        return

    if hint.startswith("escalate:"):
        reason = hint[len("escalate:"):].strip()
        if hasattr(ctx, "reactor") and ctx.reactor is not None:
            try:
                ctx.reactor.emit_pain(
                    source="brain_discussion",
                    severity=0.7,
                    detail=f"Escalation from #{discussion_number}: {reason[:100]}",
                )
            except Exception as e:
                logger.warning("Brain hint escalate failed: %s", e)
        operations.append(f"brain_hint_escalate:{reason[:40]}:#{discussion_number}")
        return

    # Unknown hint — log but don't fail
    operations.append(f"brain_hint_unknown:{hint[:40]}:#{discussion_number}")


def _route_discussion_to_agent(
    ctx: PhaseContext,
    intent: str,
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]],
    discussion_text: str = "",
) -> tuple[str | None, dict | None]:
    """Find the best agent for a discussion intent via neuro-symbolic scoring."""
    from city.diagnostics import score_agent_for_discussion
    from city.discussions_inbox import INTENT_REQUIREMENTS
    from city.mission_router import check_capability_gate

    reqs = INTENT_REQUIREMENTS.get(intent, INTENT_REQUIREMENTS["observe"])
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
        score = score_agent_for_discussion(spec, intent, discussion_text)
        if score > best_score:
            best_score = score
            best_name = name
            best_spec = spec

    if best_name is not None:
        logger.info(
            "KARMA: Discussion routed to %s (score=%.2f, intent=%s)",
            best_name, best_score, intent,
        )
    return best_name, best_spec
