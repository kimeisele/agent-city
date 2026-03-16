"""
MOKSHA Hook: System Health Diagnostic — Operator Inversion.

12E: The system tells the operator what's wrong, not vice versa.
Aggregates all health signals into a structured diagnostic that gets
posted to discussions proactively when issues are detected.

Deterministic — no LLM required. Pure signal aggregation.
This is the system recognizing its own problems.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.HEALTH")

# Severity thresholds — deterministic, no LLM needed
_ECONOMY_CRITICAL_AVG_PRANA = 500  # avg prana below this = economy dying
_ECONOMY_WARNING_AVG_PRANA = 2000
_DORMANT_SPIKE_THRESHOLD = 5  # >= 5 dormant agents = red flag
_SUPPRESSED_POSTS_WARNING = 3  # >= 3 suppressed = Brain had outage


class SystemHealthHook(BasePhaseHook):
    """12E: Proactive system health diagnostic — operator inversion.

    Runs during MOKSHA, aggregates health signals from:
    - Prana economy (deflation, starvation, dormant spike)
    - Brain status (offline, suppressed posts, critique actions)
    - Reactor pain signals (metabolize_slow, death_spike, zone_empty)
    - Thread lifecycle (stale threads, unanswered)

    Posts a structured diagnostic to discussions ONLY when issues found.
    Healthy system = silent. Problems = proactive alert.
    """

    @property
    def name(self) -> str:
        return "system_health"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 68  # just before outbound (70)

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.pokedex is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        issues: list[dict] = []

        # 1. Economy health
        issues.extend(_check_economy(ctx, reflection))

        # 2. Brain health
        issues.extend(_check_brain(ctx))

        # 3. Reactor pain signals
        issues.extend(_check_reactor(ctx))

        # 4. Thread health
        issues.extend(_check_threads(ctx))

        # 5. Heartbeat observer anomalies (Schritt 8)
        issues.extend(_check_heartbeat_observer(ctx))

        if not issues:
            operations.append("system_health:ok")
            return

        # Store on reflection for city report
        reflection["health_issues"] = issues

        # Build diagnostic
        diagnostic = _build_diagnostic(issues, ctx.heartbeat_count)
        operations.append(f"system_health:issues={len(issues)}")

        # Post to brainstream — gated by governance rules
        actions = getattr(ctx, "_governance_actions", None)
        should_post = (
            actions is not None
            and getattr(actions, "should_post_health_diagnostic", False)
        )
        if should_post and ctx.discussions is not None and not ctx.offline_mode:
            brainstream = ctx.discussions._seed_threads.get("brainstream")
            if brainstream is not None:
                ctx.discussions.comment(brainstream, diagnostic)
                operations.append("system_health:posted")
                logger.info(
                    "SYSTEM HEALTH: %d issues detected, posted to brainstream",
                    len(issues),
                )


def _check_economy(ctx: PhaseContext, reflection: dict) -> list[dict]:
    """Deterministic economy health checks."""
    issues: list[dict] = []

    economy = reflection.get("economy_stats")
    if economy is None:
        try:
            economy = ctx.pokedex.economy_snapshot()
        except Exception:
            return issues

    if not economy:
        return issues

    avg_prana = economy.get("avg_prana", 0)
    dormant = economy.get("dormant_count", 0)
    living = economy.get("living_agents", 0)

    if avg_prana < _ECONOMY_CRITICAL_AVG_PRANA and living > 0:
        issues.append({
            "severity": "critical",
            "system": "economy",
            "signal": f"Average prana critically low: {avg_prana:.0f}",
            "detail": f"Living: {living}, Dormant: {dormant}",
        })
    elif avg_prana < _ECONOMY_WARNING_AVG_PRANA and living > 0:
        issues.append({
            "severity": "warning",
            "system": "economy",
            "signal": f"Average prana declining: {avg_prana:.0f}",
            "detail": f"Living: {living}, Dormant: {dormant}",
        })

    if dormant >= _DORMANT_SPIKE_THRESHOLD:
        issues.append({
            "severity": "warning",
            "system": "economy",
            "signal": f"Dormant agent spike: {dormant} frozen",
            "detail": "Possible prana starvation or mass freezing event",
        })

    return issues


def _check_brain(ctx: PhaseContext) -> list[dict]:
    """Check Brain health — offline gaps, suppressed posts."""
    issues: list[dict] = []

    # Brain offline right now — check actual provider availability, not just object existence
    brain = ctx.brain
    brain_offline = brain is None or not getattr(brain, "is_available", True)
    if brain_offline:
        issues.append({
            "severity": "critical",
            "system": "brain",
            "signal": "Brain is OFFLINE — NoOp provider, no LLM API key detected",
            "detail": (
                "All agent cognition suppressed."
                " Check OPENROUTER_API_KEY / OPENAI_API_KEY secrets."
            ),
        })

    # Suppressed posts from recent outage
    if ctx.brain_memory is not None:
        suppressed = ctx.brain_memory.get_suppressed()
        if len(suppressed) >= _SUPPRESSED_POSTS_WARNING:
            threads = {s["discussion"] for s in suppressed}
            issues.append({
                "severity": "warning",
                "system": "brain",
                "signal": f"{len(suppressed)} posts suppressed across {len(threads)} threads",
                "detail": "Brain was offline. Posts were fail-closed (correct behavior).",
            })

    return issues


def _check_reactor(ctx: PhaseContext) -> list[dict]:
    """Check reactor pain signals."""
    issues: list[dict] = []

    reactor = getattr(ctx, "reactor", None)
    if reactor is None:
        return issues

    try:
        pain = reactor.detect_pain()
        for intent in pain:
            severity = "warning"
            detail = str(intent)
            if hasattr(intent, "severity"):
                severity = "critical" if intent.severity >= 0.7 else "warning"
            if hasattr(intent, "detail"):
                detail = intent.detail
            issues.append({
                "severity": severity,
                "system": "reactor",
                "signal": getattr(intent, "name", str(intent)),
                "detail": detail,
            })
    except Exception:
        pass

    return issues


def _check_threads(ctx: PhaseContext) -> list[dict]:
    """Check thread lifecycle health."""
    issues: list[dict] = []

    if ctx.thread_state is None:
        return issues

    try:
        # Use stats() if available — check for unanswered threads
        if hasattr(ctx.thread_state, "stats"):
            ts_stats = ctx.thread_state.stats()
            unanswered = ts_stats.get("unanswered", 0)
            if unanswered >= 5:
                issues.append({
                    "severity": "warning",
                    "system": "threads",
                    "signal": f"{unanswered} unanswered threads",
                    "detail": "Threads with human comments but no agent response",
                })
    except Exception:
        pass

    return issues


def _check_heartbeat_observer(ctx: PhaseContext) -> list[dict]:
    """Surface anomalies from HeartbeatObserver (Schritt 8)."""
    issues: list[dict] = []

    diag = getattr(ctx, "_heartbeat_diagnosis", None)
    if diag is None:
        return issues

    for anomaly in diag.anomalies:
        severity = "critical" if "crash_loop" in anomaly or "failing" in anomaly else "warning"
        issues.append({
            "severity": severity,
            "system": "observer",
            "signal": anomaly,
            "detail": f"Success rate: {diag.success_rate:.0%}, "
                       f"runs observed: {len(diag.recent_runs)}, "
                       f"discussions: {diag.total_comments} total comments",
        })

    return issues


def _build_diagnostic(issues: list[dict], heartbeat: int) -> str:
    """Build a structured diagnostic post for discussions."""
    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    lines = [f"### System Health Diagnostic — Heartbeat #{heartbeat}"]

    if critical:
        lines.append(f"\n**🔴 CRITICAL ({len(critical)})**")
        for issue in critical:
            lines.append(f"- **[{issue['system']}]** {issue['signal']}")
            if issue.get("detail"):
                lines.append(f"  - {issue['detail']}")

    if warnings:
        lines.append(f"\n**🟡 WARNING ({len(warnings)})**")
        for issue in warnings:
            lines.append(f"- **[{issue['system']}]** {issue['signal']}")
            if issue.get("detail"):
                lines.append(f"  - {issue['detail']}")

    lines.append(
        "\n*This diagnostic was generated deterministically by the system health monitor. "
        "No LLM was involved.*"
    )

    return "\n".join(lines)
