"""Brain Health Handler — System-level brain cognition during KARMA."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from config import get_config
from city.karma_handlers import BaseKarmaHandler
from city.seed_constants import NAVA, TRINITY

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.BRAIN_HEALTH")

_MAX_BRAIN_CALLS_PER_CYCLE = 3
# Max prana the brain can spend per KARMA cycle: 3 calls × 9 prana = 27
_MAX_BRAIN_PRANA_PER_CYCLE = NAVA * TRINITY  # 27 prana


def _target_repo_name() -> str:
    cfg = get_config().get("discussions", {})
    owner = cfg.get("owner", "kimeisele")
    repo = cfg.get("repo", "agent-city")
    return f"{owner}/{repo}"


def _contract_name_for_target(target: str) -> str:
    lowered = target.lower()
    if "ruff" in lowered:
        return "ruff_clean"
    if "tests_pass" in lowered or "test_pass" in lowered or "tests" in lowered:
        return "tests_pass"
    if "integrity" in lowered:
        return "integrity"
    if "code_health" in lowered:
        return "code_health"
    if "engagement" in lowered:
        return "engagement"
    token = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return token[:40] or "unknown"


def _issue_key_for_target(target: str) -> str:
    contract_name = _contract_name_for_target(target)
    token = re.sub(r"[^a-z0-9]+", "_", target.lower()).strip("_")
    token = token[:48] or "unknown"
    return f"{_target_repo_name()}:{contract_name}:{token}"


def brain_budget_ok(ctx: PhaseContext) -> bool:
    """Check if brain call budget is not exhausted for this KARMA cycle.

    Two gates (defense in depth):
    1. Call count: max 3 LLM invocations per cycle
    2. Prana budget: max 27 prana spent per cycle (tracked by BrainMemory)
    """
    if getattr(ctx, "_brain_calls", 0) >= _MAX_BRAIN_CALLS_PER_CYCLE:
        return False
    if ctx.brain_memory is not None:
        spent = getattr(ctx.brain_memory, "total_prana_spent", 0)
        if isinstance(spent, int) and spent >= _MAX_BRAIN_PRANA_PER_CYCLE:
            return False
    return True


class BrainHealthHandler(BaseKarmaHandler):
    """Evaluate system health via CityBrain. Persists before_snapshot for MOKSHA."""

    @property
    def name(self) -> str:
        return "brain_health"

    @property
    def priority(self) -> int:
        return 10

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.offline_mode:
            return False
        return ctx.brain is not None and hasattr(ctx.brain, "evaluate_health")

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.brain_context import (
            build_context_snapshot,
            build_field_digest,
            save_before_snapshot,
        )

        snapshot = build_context_snapshot(ctx)
        save_before_snapshot(snapshot, ctx.state_path.parent)

        # Observability: log explicitly when Brain is offline
        if not ctx.brain.is_available:
            operations.append("brain_health:OFFLINE")
            logger.info("Brain: cognition offline — no LLM provider available")
            return

        health_thought = ctx.brain.evaluate_health(snapshot, memory=ctx.brain_memory)
        if health_thought is None:
            operations.append("brain_health:NOOP")
            logger.info("Brain: evaluate_health returned None — LLM call failed or timed out")
            return

        operations.append(
            f"brain_health:intent={health_thought.intent.value}"
            f":confidence={health_thought.confidence:.2f}"
            f":hint={health_thought.action_hint or 'none'}"
        )
        # Record in memory (returns prana cost of the cell)
        if ctx.brain_memory is not None:
            prana_cost = ctx.brain_memory.record(
                health_thought, ctx.heartbeat_count,
            )
            if prana_cost:
                logger.debug(
                    "Brain health cost: %d prana (total spent: %d/%d)",
                    prana_cost,
                    ctx.brain_memory.total_prana_spent,
                    _MAX_BRAIN_PRANA_PER_CYCLE,
                )
        # Execute health action_hints via IntentExecutor (same as critique path)
        if health_thought.action_hint:
            _execute_health_hint(ctx, health_thought, operations)

        # Post high-confidence health thoughts to discussions
        # GATE: Repetition check — deterministic Python, not prompt engineering
        if (
            health_thought.confidence >= 0.7
            and ctx.discussions is not None
            and not ctx.offline_mode
        ):
            from city.brain_gates import check_repetition

            verdict = check_repetition(
                health_thought.action_hint, ctx.brain_memory,
            )
            if verdict.should_post:
                ctx.discussions.post_brain_thought(
                    health_thought, ctx.heartbeat_count,
                )
            else:
                operations.append(
                    f"brain_health:SUPPRESSED:{verdict.reason}"
                )
        # Budget: health check counts as 1 brain call
        ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1

        # 12C: Track brain operations for GAD-000 transparency
        brain_ops = getattr(ctx, "_brain_operations", [])
        brain_ops.append(
            f"health:intent={health_thought.intent.value}"
            f":confidence={health_thought.confidence:.2f}"
        )
        ctx._brain_operations = brain_ops  # type: ignore[attr-defined]

        # 10B: Field Critique — Brain as Kshetrajna evaluates system output
        if brain_budget_ok(ctx) and hasattr(ctx.brain, "critique_field"):
            field_summary = build_field_digest(ctx)
            critique = ctx.brain.critique_field(
                field_summary, snapshot=snapshot, memory=ctx.brain_memory,
            )
            if critique is not None:
                operations.append(
                    f"brain_critique:intent={critique.intent.value}"
                    f":confidence={critique.confidence:.2f}"
                    f":hint={critique.action_hint or 'none'}"
                )
                if ctx.brain_memory is not None:
                    ctx.brain_memory.record(critique, ctx.heartbeat_count)
                ctx._brain_calls = getattr(ctx, "_brain_calls", 0) + 1

                # 12C: Track critique for GAD-000 transparency
                brain_ops = getattr(ctx, "_brain_operations", [])
                brain_ops.append(
                    f"critique:intent={critique.intent.value}"
                    f":confidence={critique.confidence:.2f}"
                    f":hint={critique.action_hint or 'none'}"
                )
                ctx._brain_operations = brain_ops  # type: ignore[attr-defined]

                # 10C: Self-healing loop — execute critique action hints
                if critique.action_hint:
                    _execute_critique_hint(ctx, critique, operations)

                # Post high-confidence critiques to brainstream
                # GATE: Repetition check — deterministic Python, not prompt engineering
                if (
                    critique.confidence >= 0.6
                    and ctx.discussions is not None
                    and not ctx.offline_mode
                ):
                    from city.brain_gates import check_repetition

                    critique_verdict = check_repetition(
                        critique.action_hint, ctx.brain_memory,
                    )
                    if critique_verdict.should_post:
                        ctx.discussions.post_brain_thought(
                            critique, ctx.heartbeat_count,
                        )
                    else:
                        operations.append(
                            f"brain_critique:SUPPRESSED:{critique_verdict.reason}"
                        )


def _execute_health_hint(
    ctx: PhaseContext,
    health_thought: object,
    operations: list[str],
) -> None:
    """Execute Brain health action_hints — Brain sees problem, Brain acts.

    Mirrors _execute_critique_hint but for health_check thoughts.
    The Brain is authorized to act on anomalies it detects in system health.
    """
    from city.brain_action import parse_action_hint

    hint = getattr(health_thought, "action_hint", "")
    if not hint:
        return

    try:
        confidence = float(getattr(health_thought, "confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    action = parse_action_hint(hint, confidence=confidence)

    if action is None:
        operations.append(f"health_hint_unknown:{hint[:40]}")
        return

    # Enforcement verbs require minimum confidence
    if action.is_enforcement and not action.confidence_sufficient:
        operations.append(
            f"health_hint_low_confidence:{action.verb.value}"
            f":conf={confidence:.2f}"
        )
        logger.info(
            "BRAIN HEALTH: %s rejected — confidence %.2f below threshold",
            action.verb.value, confidence,
        )
        return

    # ── Scope gate: reject missions that require code changes ──────
    # Agents can respond/investigate/check_health but CANNOT write code,
    # run ruff, fix tests, or create PRs.  Those need the Steward (NADI).
    # Downgrade to flag_bottleneck so the problem is logged, not lost.
    from city.brain_action import ActionVerb

    _CODE_FIX_KEYWORDS = (
        "ruff", "tests_pass", "test_pass", "lint", "contract",
        "code_health", "fix code", "repair code", "refactor",
    )
    if action.verb == ActionVerb.CREATE_MISSION:
        target = action.target or ""
        if any(kw in target.lower() for kw in _CODE_FIX_KEYWORDS):
            operations.append(
                f"health_action:SCOPE_REJECT:create_mission→flag_bottleneck"
                f":{target[:60]}"
            )
            logger.info(
                "BRAIN HEALTH: downgraded create_mission to flag_bottleneck "
                "— target requires code changes agents cannot perform: %s",
                target[:80],
            )
            # ── Wire to Steward via NADI ────────────────────────────
            _escalate_bottleneck_to_steward(ctx, target, "brain_health")
            # ── Create Bounty on Marketplace ──────────────────────
            try:
                from city.bounty import create_bounty
                bounty_id = create_bounty(ctx, target, severity="high", source="brain_health")
                if bounty_id:
                    operations.append(f"bounty_created:{bounty_id}")
            except Exception as exc:
                logger.debug("Bounty creation failed (non-fatal): %s", exc)
            return

    # Awareness gate: skip if an active brain-health mission already exists.
    # Brain health always creates disc_0_* missions (no discussion context).
    # Deterministic check (element 24) — do NOT rely on LLM to avoid duplicates.
    if action.verb == ActionVerb.CREATE_MISSION and ctx.sankalpa is not None:
        if hasattr(ctx.sankalpa, "registry"):
            try:
                active = ctx.sankalpa.registry.get_active_missions()
                # Brain-health missions always use disc_0_ prefix
                # (discussion_number=0 because there's no discussion context).
                # Also check brain_bottleneck_ prefix from flag_bottleneck hints.
                for m in active:
                    mid = getattr(m, "id", "")
                    if mid.startswith("disc_0_") or mid.startswith("brain_bottleneck_"):
                        operations.append(
                            f"health_action:SKIP_DUPLICATE:{action.verb.value}"
                            f":{mid}"
                        )
                        logger.info(
                            "BRAIN HEALTH: skipped duplicate — active mission "
                            "'%s' already exists",
                            mid,
                        )
                        return
            except Exception as e:
                logger.debug("Awareness gate check failed: %s", e)

    # Dispatch via CityIntentExecutor (unified path)
    from city.registry import SVC_ATTENTION, SVC_INTENT_EXECUTOR

    executor = ctx.registry.get(SVC_INTENT_EXECUTOR) if ctx.registry else None
    attention = ctx.registry.get(SVC_ATTENTION) if ctx.registry else None

    if executor is not None:
        from city.membrane import internal_membrane_snapshot

        evidence = getattr(health_thought, "evidence", "") or ""
        if isinstance(evidence, (list, tuple)):
            evidence = "; ".join(str(e) for e in evidence[:3])
        intent = action.to_city_intent(
            source="health_check",
            detail=str(evidence)[:60],
            membrane=internal_membrane_snapshot(),
        )
        handler_name = attention.route(intent.signal) if attention else None
        result = executor.execute(ctx, intent, handler_name)
        operations.append(f"health_action:{action.verb.value}:{result}")
        logger.info(
            "BRAIN HEALTH ACTION: %s → %s (confidence=%.2f)",
            action.verb.value, result, confidence,
        )
    else:
        operations.append(f"health_hint_unhandled:{action.verb.value}")


def _execute_critique_hint(
    ctx: PhaseContext,
    critique: object,
    operations: list[str],
) -> None:
    """10C: Execute Brain critique action_hints — self-healing loop.

    Unlike discussion hints, these are system-level (no discussion context).
    The Brain is authorized to act on its own field critique.

    Schritt 2: Uses typed ActionParser instead of startswith() chains.
    """
    from city.brain_action import parse_action_hint

    hint = getattr(critique, "action_hint", "")
    if not hint:
        return

    try:
        confidence = float(getattr(critique, "confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    action = parse_action_hint(hint, confidence=confidence)

    if action is None:
        operations.append(f"critique_hint_unknown:{hint[:40]}")
        return

    # Enforcement verbs require minimum confidence
    if action.is_enforcement and not action.confidence_sufficient:
        operations.append(
            f"critique_hint_low_confidence:{action.verb.value}"
            f":conf={confidence:.2f}"
        )
        logger.info(
            "BRAIN: %s rejected — confidence %.2f below threshold",
            action.verb.value, confidence,
        )
        # Track rejection for Brain feedback loop
        rejected = getattr(ctx, "_rejected_actions", [])
        rejected.append({
            "verb": action.verb.value,
            "target": action.target,
            "reason": f"confidence {confidence:.2f} below enforcement threshold",
            "source": "critique",
        })
        ctx._rejected_actions = rejected  # type: ignore[attr-defined]
        return

    # Scope gate: reject missions that require code changes (same as health hints)
    from city.brain_action import ActionVerb

    _CODE_FIX_KEYWORDS = (
        "ruff", "tests_pass", "test_pass", "lint", "contract",
        "code_health", "fix code", "repair code", "refactor",
    )
    if action.verb == ActionVerb.CREATE_MISSION:
        target = action.target or ""
        if any(kw in target.lower() for kw in _CODE_FIX_KEYWORDS):
            operations.append(
                f"critique_action:SCOPE_REJECT:create_mission→flag_bottleneck"
                f":{target[:60]}"
            )
            logger.info(
                "BRAIN: downgraded create_mission to flag_bottleneck "
                "— target requires code changes: %s",
                target[:80],
            )
            # ── Wire to Steward via NADI ────────────────────────────
            _escalate_bottleneck_to_steward(ctx, target, "brain_critique")
            # ── Create Bounty on Marketplace ──────────────────────
            try:
                from city.bounty import create_bounty
                bounty_id = create_bounty(ctx, target, severity="high", source="brain_critique")
                if bounty_id:
                    operations.append(f"bounty_created:{bounty_id}")
            except Exception as exc:
                logger.debug("Bounty creation failed (non-fatal): %s", exc)
            return

    # Schritt 6B: Unified dispatch via CityIntentExecutor
    from city.registry import SVC_ATTENTION, SVC_INTENT_EXECUTOR

    executor = ctx.registry.get(SVC_INTENT_EXECUTOR) if ctx.registry else None
    attention = ctx.registry.get(SVC_ATTENTION) if ctx.registry else None

    if executor is not None:
        from city.membrane import internal_membrane_snapshot

        evidence = getattr(critique, "evidence", "") or ""
        intent = action.to_city_intent(
            source="critique",
            detail=evidence[:60],
            membrane=internal_membrane_snapshot(),
        )
        handler_name = attention.route(intent.signal) if attention else None
        result = executor.execute(ctx, intent, handler_name)
        operations.append(f"critique_action:{action.verb.value}:{result}")
    else:
        operations.append(f"critique_hint_unhandled:{action.verb.value}")


# ── Steward escalation via Federation NADI ──────────────────────────


def _escalate_bottleneck_to_steward(
    ctx: PhaseContext, target: str, source: str,
) -> None:
    """Emit a bottleneck_escalation message to the Steward via NADI.

    Called when the Scope Gate rejects a code-fix mission that agents
    cannot perform.  The Steward (federation super-agent) has the
    AutonomyEngine to actually fix code, run ruff, and create PRs.
    """
    nadi = ctx.federation_nadi
    if nadi is None or not hasattr(nadi, "emit"):
        logger.warning(
            "BRAIN HEALTH: cannot escalate bottleneck — federation_nadi unavailable"
        )
        return

    nadi.emit(
        source=source,
        operation="bottleneck_escalation",
        payload={
            "target": target[:120],
            "contract_name": _contract_name_for_target(target),
            "issue_key": _issue_key_for_target(target),
            "target_repo": _target_repo_name(),
            "target_role": "city_runtime",
            "source": source,
            "evidence": "failing contracts — scope gate rejected code-fix mission",
            "requested_action": "fix",
            "heartbeat": getattr(ctx, "heartbeat_count", 0),
        },
        priority=2,  # SATTVA — important, not critical
    )
    logger.info(
        "BRAIN HEALTH: escalated bottleneck to Steward via NADI — %s",
        target[:80],
    )
