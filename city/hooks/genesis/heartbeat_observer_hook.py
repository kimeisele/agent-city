"""
GENESIS Hook: Heartbeat Observer — Self-Observation.

The system reads its own recent workflow runs and Discussion activity
before doing anything else. The diagnosis is stored on ctx for downstream
hooks (SystemHealthHook, Brain context, etc.) to consume.

Priority 1 — runs before census (0) is wrong, run AFTER census.
Priority 5 — after census, before everything else.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.OBSERVER")


class HeartbeatObserverHook(BasePhaseHook):
    """GENESIS: Self-observation before any action.

    Reads workflow runs + discussion activity via gh CLI.
    Stores HeartbeatDiagnosis on ctx._heartbeat_diagnosis for downstream use.
    """

    @property
    def name(self) -> str:
        return "heartbeat_observer"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 5  # after census (0), before all other hooks

    def should_run(self, ctx: PhaseContext) -> bool:
        # Only observe when online (gh CLI available) and not in test mode
        return not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from config import get_config
        from city.heartbeat_observer import HeartbeatObserver

        cfg = get_config()
        disc_cfg = cfg.get("discussions", {})
        owner = disc_cfg.get("owner", "")
        repo = disc_cfg.get("repo", "")
        if not owner or not repo:
            logger.debug("HeartbeatObserver: no discussions.owner/repo configured, skipping")
            return

        observer = HeartbeatObserver(
            _owner=owner,
            _repo=repo,
        )

        diag = observer.observe()

        # Schritt 9: Brain-alive check — detect NoOp provider EARLY
        brain = ctx.brain
        if brain is not None and not getattr(brain, "is_available", True):
            diag.anomalies.append(
                "brain_offline: NoOp provider — no LLM API key detected. "
                "All agent cognition is suppressed."
            )
            logger.critical(
                "OBSERVER CRITICAL: Brain is brain-dead (NoOp provider). "
                "Set OPENROUTER_API_KEY or OPENAI_API_KEY in GitHub Secrets."
            )

        # Store on ctx for downstream hooks
        ctx._heartbeat_diagnosis = diag  # type: ignore[attr-defined]

        # Log anomalies
        if diag.anomalies:
            for anomaly in diag.anomalies:
                operations.append(f"observer:{anomaly}")
                logger.warning("OBSERVER ANOMALY: %s", anomaly)

            # Emit CityIntent for self-repair if intent_executor available
            from city.registry import SVC_INTENT_EXECUTOR
            executor = ctx.registry.get(SVC_INTENT_EXECUTOR) if ctx.registry else None
            if executor is not None:
                _emit_anomaly_intents(ctx, executor, diag)
        else:
            operations.append(f"observer:healthy ({diag.summary()})")
            logger.info("OBSERVER: system healthy — %s", diag.summary())


def _emit_anomaly_intents(ctx, executor, diag):
    """Convert anomalies into CityIntents for the dispatch system."""
    try:
        from city.intent_executor import CityIntent

        for anomaly in diag.anomalies:
            intent = CityIntent(
                signal="observer:anomaly",
                context={
                    "anomaly": anomaly,
                    "success_rate": diag.success_rate,
                    "last_success_age_s": diag.last_success_age_s,
                    "total_comments": diag.total_comments,
                },
            )
            # Route through attention if available
            from city.registry import SVC_ATTENTION
            attention = ctx.registry.get(SVC_ATTENTION) if ctx.registry else None
            if attention is not None:
                handler_name = attention.route(intent)
                if handler_name:
                    executor.execute(ctx, intent, handler_name)
    except Exception as e:
        logger.debug("Anomaly intent emission skipped: %s", e)
