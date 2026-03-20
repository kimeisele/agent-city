"""Gateway Handler — Drain nadi/queue, process via gateway, route discussions/DMs."""

from __future__ import annotations

import logging
from collections import OrderedDict as _OrderedDict
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
        ctx.all_specs = all_specs
        ctx.all_inventories = all_inventories

        # Reset discussions per-cycle counter
        if ctx.discussions is not None:
            ctx.discussions.reset_cycle()

        # 9D: Per-cycle thread dedup — prevent responding to same thread twice
        responded_threads: set[int] = set()
        ctx.responded_threads = responded_threads
        # 9D: Per-cycle agent diversity — track which agents responded
        ctx.responded_threads_agents = set()

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
                result = ctx.gateway.process(
                    enriched_text,
                    source,
                    membrane=item.get("membrane"),
                )

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
    membrane = item.get("membrane")

    # 9D: Per-cycle dedup — skip threads already responded to this cycle
    responded = ctx.responded_threads
    if discussion_number in responded:
        operations.append(f"disc_dedup:#{discussion_number}")
        return

    # 9B: Last Speaker Gate — skip threads where bot was last to speak
    # Prevents re-processing on cache miss / stale re-scan
    if ctx.thread_state is not None:
        ts = ctx.thread_state.get(discussion_number)
        if ts is not None and not ts.unresolved:
            logger.debug(
                "KARMA: Skipping #%d — last speaker was bot (status=%s)",
                discussion_number, ts.status,
            )
            operations.append(f"disc_last_speaker_gate:#{discussion_number}")
            return

    # Phase 6B: Parse and EXECUTE inbound commands
    commands = parse_commands(
        comment_body,
        author=comment_author,
        discussion_number=discussion_number,
        comment_id=comment_id,
    )
    command_handled = False
    command_denied = False
    for cmd in commands:
        if cmd.is_valid:
            operations.append(
                f"disc_cmd:/{cmd.command}:#{discussion_number}:@{cmd.author}"
            )
            allowed, denial_reason = _authorize_discussion_command(
                ctx,
                cmd.command,
                cmd.author,
                membrane=membrane,
            )
            if not allowed:
                operations.append(
                    f"disc_cmd_denied:/{cmd.command}:#{discussion_number}:@{cmd.author}:{denial_reason}"
                )
                rejected = getattr(ctx, "_rejected_actions", [])
                rejected.append({
                    "verb": f"/{cmd.command}",
                    "target": cmd.args[:40],
                    "reason": (
                        f"{denial_reason} for @{cmd.author} on #{discussion_number}"
                    ),
                    "source": "discussion",
                })
                ctx._rejected_actions = rejected  # type: ignore[attr-defined]
                command_denied = True
                _learn(ctx, "discussion", "command_denied", success=False)
                continue
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
    if command_handled or command_denied:
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
                    "KARMA: @%s blocked by capability gate for #%d, falling back to general routing",
                    direct_agent, discussion_number,
                )
        else:
            logger.debug(
                "KARMA: @%s not in specs for discussion #%d, falling back",
                direct_agent, discussion_number,
            )

    # General routing: no direct agent, or direct agent was blocked
    if agent_name is None:
        intent = classify_discussion_intent(result)
        agent_name, agent_spec, routing_score = _route_discussion_to_agent(
            ctx, intent, all_specs, all_inventories, discussion_text=item.get("text", ""),
        )
        if routing_score > 0:
            result["routing_score"] = round(routing_score, 2)
            result["routing_intent"] = intent

    if agent_name is None or agent_spec is None:
        operations.append(f"disc_no_agent:#{discussion_number}")
        _learn(ctx, "discussion", "route", success=False)
        return

    # 8D+8G: Claim protocol — lock thread before acting, charge prana tax
    _claim_ticket = None
    try:
        from city.city_registry import get_city_registry
        from city.seed_constants import TRINITY as _CLAIM_COST

        _city_reg = get_city_registry()

        # 8G: Prana gate — broke agents can't claim threads
        if ctx.pokedex is not None:
            agent_prana = ctx.pokedex.get_prana(agent_name)
            if agent_prana < _CLAIM_COST:
                operations.append(
                    f"disc_claim_broke:{agent_name}:#{discussion_number}:prana={agent_prana}"
                )
                _learn(ctx, "discussion", "claim_broke", success=False)
                return

        _claim_ticket = _city_reg.request_claim(
            thread_id=str(discussion_number),
            agent_id=agent_name,
        )
        if _claim_ticket is None:
            holder = _city_reg.get_claim_holder(str(discussion_number))
            operations.append(
                f"disc_claim_denied:{agent_name}:#{discussion_number}:held_by={holder}"
            )
            _learn(ctx, "discussion", "claim", success=False)
            return

        # 8G: Debit claim tax on grant
        if ctx.pokedex is not None:
            ctx.pokedex.debit_prana(agent_name, _CLAIM_COST, reason="claim_tax")
    except Exception as exc:
        logger.debug("Claim protocol skipped: %s", exc)

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
            # 8G: Bill the agent for brain compute
            if ctx.pokedex is not None:
                from city.brain_cell import BRAIN_CALL_COST
                ctx.pokedex.debit_prana(
                    agent_name, BRAIN_CALL_COST, reason="brain_comprehension",
                )
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
                    membrane=membrane,
                )

    # 7A-4: Agent Runtime — the 6-step cognitive loop
    # Replaces static cartridge.process() with confidence-gated cognition
    cartridge_cognition = None
    try:
        from city.registry import SVC_CARTRIDGE_FACTORY, SVC_LEARNING
        from city.agent_runtime import AgentRuntime

        factory = ctx.registry.get(SVC_CARTRIDGE_FACTORY)
        learning = ctx.registry.get(SVC_LEARNING)

        if factory is not None:
            cartridge = factory.get(agent_name)
            if cartridge is not None:
                # Build runtime with MicroBrain if LLM is available
                micro_brain = None
                try:
                    from city.micro_brain import MicroBrain
                    micro_brain = MicroBrain()
                except Exception:
                    pass

                runtime = AgentRuntime(
                    name=agent_name,
                    cartridge=cartridge,
                    learning=learning,
                    micro_brain=micro_brain,
                )
                task_text = item.get("text", "") or signal.title
                cartridge_cognition = runtime.process(task_text, intent="discussion")

                mode = cartridge_cognition.get("decision_mode", "?")
                conf = cartridge_cognition.get("confidence", 0)
                operations.append(f"runtime:{agent_name}:{mode}:{conf:.2f}:#{discussion_number}")

                # Execute non-respond actions through IntentExecutor
                brain_action = cartridge_cognition.get("brain_action")
                if brain_action is not None:
                    from city.registry import SVC_EXECUTOR
                    executor = ctx.registry.get(SVC_EXECUTOR)
                    if executor is not None:
                        exec_result = executor.execute_brain_action(
                            ctx, brain_action, ctx.attention,
                            agent=agent_name, discussion=discussion_number,
                        )
                        operations.append(f"runtime_action:{agent_name}:{brain_action.verb}:{exec_result}")
                        logger.info(
                            "RUNTIME ACTION: %s → %s (target=%s) → %s",
                            agent_name, brain_action.verb, brain_action.target, exec_result,
                        )
    except Exception as e:
        logger.debug("AgentRuntime skipped for %s: %s", agent_name, e)

    # Build response
    city_stats = ctx.pokedex.stats()
    response = dispatch_discussion(
        signal, result, agent_spec, city_stats,
        semantic_signal=disc_semantic_signal,
        brain_thought=brain_thought,
        cartridge_cognition=cartridge_cognition,
    )

    # 9A: Fail Closed — if Brain is offline, dispatch returns None. Stay silent.
    if response is None:
        operations.append(f"disc_brain_offline:{agent_name}:#{discussion_number}")
        _learn(ctx, "discussion", "brain_offline", success=False)
        # 12D: Record suppressed post so Brain detects its own gaps on recovery
        if ctx.brain_memory is not None:
            ctx.brain_memory.record_suppressed(
                agent_name, discussion_number, ctx.heartbeat_count,
            )
        if _claim_ticket is not None:
            try:
                _city_reg.release_claim(str(discussion_number), agent_name)
            except Exception:
                pass
        return

    # Broadcast signal to agent nadi
    if disc_semantic_signal is not None and ctx.agent_nadi is not None:
        ctx.agent_nadi.broadcast(agent_name, response.body[:200])

    # 8D: Re-validate claim AFTER brain (may have expired during LLM inference)
    if _claim_ticket is not None:
        try:
            if not _city_reg.check_claim(str(discussion_number), agent_name):
                holder = _city_reg.get_claim_holder(str(discussion_number))
                logger.warning(
                    "CLAIM: Post aborted — '%s' lost claim on #%d (holder=%s)",
                    agent_name, discussion_number, holder or "expired",
                )
                operations.append(
                    "disc_claim_lost:"
                    f"{agent_name}:#{discussion_number}:holder={holder or 'expired'}"
                )
                _learn(ctx, "discussion", "claim_lost", success=False)
                return
        except Exception as exc:
            logger.debug("Claim re-validation skipped: %s", exc)

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
            # Runtime learning: record per-agent per-intent outcome
            _learn(ctx, f"{agent_name}:discussion", "handle", success=True)
            # 12B: Prana income — rebate for successful Brain-gated post
            if ctx.pokedex is not None:
                from city.seed_constants import DISCUSSION_RESPONSE_REBATE
                ctx.pokedex.award_prana(
                    agent_name, DISCUSSION_RESPONSE_REBATE,
                    source=f"disc_response:#{discussion_number}",
                )
            # 9D: Mark thread + agent as responded for per-cycle dedup/diversity
            ctx.responded_threads.add(discussion_number)
            ctx.responded_threads_agents.add(agent_name)

            # 8D: Release claim after successful post
            if _claim_ticket is not None:
                try:
                    _city_reg.release_claim(str(discussion_number), agent_name)
                except Exception:
                    pass

            # 7B-3: Cross-post DISABLED — activity logs are spam, not content.
            # Every Discussion response was being posted as "[Agent] X: responded
            # to discussion #Y" which has zero value for Moltbook readers and got
            # flagged as spam. Real Moltbook content comes from MoltbookOutboundHook
            # (BrainVoice insights, spotlights) — not from activity cross-posts.
        else:
            operations.append(f"disc_post_failed:#{discussion_number}")
            _learn(ctx, "discussion", "reply", success=False)
            # 8D: Release claim on post failure (don't orphan the lock)
            if _claim_ticket is not None:
                try:
                    _city_reg.release_claim(str(discussion_number), agent_name)
                except Exception:
                    pass
    else:
        operations.append(f"disc_rate_limited:#{discussion_number}")
        # 8D: Release claim on rate limit (don't orphan the lock)
        if _claim_ticket is not None:
            try:
                _city_reg.release_claim(str(discussion_number), agent_name)
            except Exception:
                pass


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


# 6C-9: Track executed action_hints per comment_id to prevent duplicate fires on edits.
# OrderedDict for FIFO eviction (oldest entries removed first, not arbitrary).
_executed_hints: _OrderedDict[str, str] = _OrderedDict()  # comment_id → last executed hint
_EXECUTED_HINTS_MAX = 500


def _authorize_discussion_command(
    ctx: PhaseContext,
    command: str,
    author: str,
    *,
    membrane: dict | None = None,
) -> tuple[bool, str]:
    from city.membrane import AuthorityRequirement, authorize_ingress

    requirement = AuthorityRequirement()
    if command in {"mission", "heal"}:
        from city.claims import ClaimLevel

        requirement = AuthorityRequirement(claim_level=ClaimLevel.SELF_CLAIMED)
    return authorize_ingress(
        ctx,
        membrane=membrane,
        author=author,
        requirement=requirement,
    )


def _authorize_action_hint(
    ctx: PhaseContext,
    hint: str,
    author: str,
    *,
    membrane: dict | None = None,
) -> tuple[bool, str]:
    """Check if comment author is authorized to trigger this action_hint.

    C2.2: Resolve effective authority from membrane floor + local identity.
    """
    from city.brain_action import parse_action_hint
    from city.membrane import authorize_ingress, requirement_for_auth_tier

    action = parse_action_hint(hint)
    if action is None:
        return False, "unknown_hint"

    return authorize_ingress(
        ctx,
        membrane=membrane,
        author=author,
        requirement=requirement_for_auth_tier(action.auth_tier),
    )


def _execute_action_hint(
    ctx: PhaseContext,
    thought: object,
    discussion_number: int,
    agent_name: str,
    operations: list[str],
    *,
    comment_author: str = "",
    comment_id: str = "",
    membrane: dict | None = None,
) -> None:
    """Act on a Brain action_hint from discussion comprehension.

    6C-8: Authorization-gated — state-mutating hints require citizen/operator.
    6C-9: Edit-dedup — same hint for same comment_id is skipped.
    Schritt 2: Uses typed ActionParser instead of startswith() chains.
    """
    from city.brain_action import parse_action_hint

    hint = thought.action_hint
    if not hint:
        return

    # 6C-8: Authorization gate
    allowed, denial_reason = _authorize_action_hint(
        ctx,
        hint,
        comment_author,
        membrane=membrane,
    )
    if not allowed:
        operations.append(
            f"brain_hint_denied:{hint[:30]}:@{comment_author}:#{discussion_number}:{denial_reason}"
        )
        logger.info(
            "KARMA: action_hint '%s' denied for @%s (%s)",
            hint[:40], comment_author, denial_reason,
        )
        # Track rejection for Brain feedback loop
        rejected = getattr(ctx, "_rejected_actions", [])
        rejected.append({
            "verb": hint.split(":")[0] if ":" in hint else hint,
            "target": hint.split(":", 1)[1][:40] if ":" in hint else "",
            "reason": f"{denial_reason} for @{comment_author} on #{discussion_number}",
            "source": "discussion",
        })
        ctx._rejected_actions = rejected  # type: ignore[attr-defined]
        return

    # Parse into typed action
    try:
        confidence = float(getattr(thought, "confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    action = parse_action_hint(hint, confidence=confidence)

    if action is None:
        operations.append(f"brain_hint_unknown:{hint[:40]}:#{discussion_number}")
        return

    # 6C-9: Edit dedup — skip if same hint already executed for this comment
    if comment_id:
        prev_hint = _executed_hints.get(comment_id)
        if prev_hint == hint:
            operations.append(
                f"brain_hint_dedup:{hint[:30]}:{comment_id[:12]}:#{discussion_number}"
            )
            return
        # Track this execution (bounded OrderedDict — FIFO eviction)
        while len(_executed_hints) >= _EXECUTED_HINTS_MAX:
            _executed_hints.popitem(last=False)  # evict oldest
        _executed_hints[comment_id] = hint

    # Schritt 6B: Unified dispatch via CityIntentExecutor
    from city.registry import SVC_ATTENTION, SVC_INTENT_EXECUTOR

    executor = ctx.registry.get(SVC_INTENT_EXECUTOR) if ctx.registry else None
    attention = ctx.registry.get(SVC_ATTENTION) if ctx.registry else None

    if executor is not None:
        # Enrich intent with discussion context
        intent = action.to_city_intent(
            source="discussion",
            discussion_number=discussion_number,
            intent_type=getattr(thought, "intent", None) and thought.intent.value or "observe",
            author=comment_author,
            membrane=membrane or {},
        )
        handler_name = attention.route(intent.signal) if attention else None
        result = executor.execute(ctx, intent, handler_name)
        operations.append(f"brain_action:{action.verb.value}:{result}:#{discussion_number}")
    else:
        operations.append(f"brain_hint_unhandled:{action.verb.value}:#{discussion_number}")


def _route_discussion_to_agent(
    ctx: PhaseContext,
    intent: str,
    all_specs: dict[str, dict],
    all_inventories: dict[str, list[dict]],
    discussion_text: str = "",
) -> tuple[str | None, dict | None]:
    """Find the best agent for a discussion intent via resonance chamber.

    8B: Uses CityResonator (steward-protocol SankirtanChamber) instead of
    flat scoring. Capability gating stays as pre-filter. Falls back to
    diagnostics scoring if resonator unavailable.
    """
    from city.discussions_inbox import INTENT_REQUIREMENTS

    reqs = INTENT_REQUIREMENTS.get(intent, INTENT_REQUIREMENTS["observe"])
    required_caps = reqs.get("required_caps", [])

    # Schritt 4: O(1) pre-filter via CityRouter (Lotus lookup + set intersection)
    from city.registry import SVC_ROUTER
    router = ctx.registry.get(SVC_ROUTER) if ctx.registry else None

    if router is not None:
        # O(1) capability + tier lookup → frozenset of agent names
        eligible_names = router.agents_for_requirement(
            required_caps=required_caps, min_tier="contributor",
        )
        # Intersect with active agents (O(|active|))
        eligible_names = eligible_names & ctx.active_agents
        eligible_specs = {n: all_specs[n] for n in eligible_names if n in all_specs}
    else:
        # Fallback: O(n) linear scan (pre-Schritt-4 path)
        from city.mission_router import check_capability_gate
        gate_req = {
            "required": required_caps,
            "preferred": [],
            "min_tier": "contributor",
        }
        eligible_specs = {}
        for name, spec in all_specs.items():
            if name not in ctx.active_agents:
                continue
            inventory = all_inventories.get(name)
            if not check_capability_gate(spec, gate_req, inventory):
                continue
            eligible_specs[name] = spec

    if not eligible_specs:
        return None, None, -1.0

    # 9D: Routing diversity — deprioritize agents who already responded this cycle
    responded_this_cycle = ctx.responded_threads_agents
    diverse_specs: dict[str, dict] = {}
    fallback_specs: dict[str, dict] = {}
    for name, spec in eligible_specs.items():
        if name in responded_this_cycle:
            fallback_specs[name] = spec
        else:
            diverse_specs[name] = spec
    # Prefer diverse agents; fall back to all eligible if none left
    routing_specs = diverse_specs if diverse_specs else eligible_specs

    # 8B: Resonance-based routing via CityResonator
    best_name: str | None = None
    best_spec: dict | None = None
    best_score = -1.0

    try:
        from city.resonator import get_resonator

        resonator = get_resonator()
        result = resonator.resonate(discussion_text, routing_specs, max_agents=1)
        if result.scores:
            top = result.scores[0]
            best_name = top.agent_name
            best_spec = eligible_specs[best_name]
            # Normalize prana_delta to 0.0-1.0 range for compatibility
            best_score = max(0.0, min(1.0, top.prana_delta / 1000.0))
            logger.info(
                "KARMA: Resonator routed to %s (prana_delta=%d, mode=%s, intent=%s)",
                best_name, top.prana_delta, result.chamber_mode, intent,
            )
    except Exception as exc:
        logger.warning("KARMA: Resonator unavailable: %s", exc)

    # Fallback: deterministic pick (first from diversity pool) — no fake scoring
    if best_name is None and routing_specs:
        best_name = next(iter(routing_specs))
        best_spec = routing_specs[best_name]
        best_score = 0.0
        logger.info(
            "KARMA: Deterministic fallback routed to %s (intent=%s)",
            best_name, intent,
        )

    return best_name, best_spec, best_score
