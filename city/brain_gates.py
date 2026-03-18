"""
BRAIN GATES — Deterministic Python Harness Around Brain Outputs.

Compound Architecture: 24/25 elements are hard deterministic Python.
The Brain (LLM) is 1/25. These gates are the other 24.

Three gates:
1. RepetitionGate: Suppress duplicate action_hints, auto-escalate verbs.
2. pending_brain_missions: Count active brain-created missions.
3. terminal_brain_missions: Collect completed/failed brain missions for feedback.

NO prompts. NO LLM calls. Pure Python reflexes.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.brain_memory import BrainMemory

logger = logging.getLogger("AGENT_CITY.BRAIN_GATES")

# ── Gate 1: Repetition Gate ─────────────────────────────────────────
# If the same action_hint verb+target appeared N times in recent memory,
# suppress the post and/or auto-escalate the verb.

_REPETITION_THRESHOLD = 3  # same hint verb 3x → suppress or escalate
_RECENT_WINDOW = 6         # look at last 6 thoughts


@dataclass(frozen=True)
class RepetitionVerdict:
    """Deterministic verdict from the Repetition Gate.

    should_post: False = suppress the discussion post (dedup).
    escalated_hint: If non-empty, the original hint was auto-escalated.
    repeat_count: How many times this verb appeared in recent memory.
    """

    should_post: bool
    escalated_hint: str
    repeat_count: int
    reason: str = ""


def _extract_hint_verb(action_hint: str) -> str:
    """Extract the verb part from an action_hint string.

    'flag_bottleneck:engineering' → 'flag_bottleneck'
    'investigate:api_latency' → 'investigate'
    'escalate' → 'escalate'
    """
    if not action_hint:
        return ""
    return action_hint.split(":")[0].strip()


# Deterministic escalation map: if verb repeated too often, upgrade it.
# Only validate-tier verbs escalate. Infer/route/enforce stay as-is.
_ESCALATION_MAP: dict[str, str] = {
    "flag_bottleneck": "escalate",
    "check_health": "escalate",
    "investigate": "escalate",
}


def check_repetition(
    action_hint: str,
    memory: BrainMemory | None,
    *,
    threshold: int = _REPETITION_THRESHOLD,
    window: int = _RECENT_WINDOW,
) -> RepetitionVerdict:
    """Deterministic repetition check against BrainMemory.

    Returns a RepetitionVerdict:
    - If hint verb appeared < threshold times → post normally.
    - If hint verb appeared >= threshold times AND is escalatable →
      auto-escalate verb, still post (with new verb).
    - If hint verb appeared >= threshold times AND is NOT escalatable →
      suppress the post entirely.

    Pure Python. No LLM. No prompt changes.
    """
    if not action_hint or memory is None:
        return RepetitionVerdict(
            should_post=True, escalated_hint="", repeat_count=0,
        )

    verb = _extract_hint_verb(action_hint)
    if not verb:
        return RepetitionVerdict(
            should_post=True, escalated_hint="", repeat_count=0,
        )

    # Count same verb in recent memory
    recent = memory.recent(window)
    count = sum(
        1 for entry in recent
        if _extract_hint_verb(
            entry.get("thought", {}).get("action_hint", "")
        ) == verb
    )

    if count < threshold:
        return RepetitionVerdict(
            should_post=True, escalated_hint="", repeat_count=count,
        )

    # Threshold reached — check if we can escalate
    escalated_verb = _ESCALATION_MAP.get(verb)
    if escalated_verb:
        # Auto-escalate: swap the verb, keep the target
        target = action_hint.split(":", 1)[1].strip() if ":" in action_hint else ""
        new_hint = f"{escalated_verb}:{target}" if target else escalated_verb
        logger.info(
            "REPETITION GATE: '%s' appeared %d times in last %d thoughts — "
            "auto-escalating to '%s'",
            verb, count, window, new_hint,
        )
        return RepetitionVerdict(
            should_post=True,
            escalated_hint=new_hint,
            repeat_count=count,
            reason=f"auto-escalated from {verb} (repeated {count}x)",
        )

    # Not escalatable — suppress the post
    logger.info(
        "REPETITION GATE: '%s' appeared %d times in last %d thoughts — "
        "suppressing duplicate post",
        verb, count, window,
    )
    return RepetitionVerdict(
        should_post=False,
        escalated_hint="",
        repeat_count=count,
        reason=f"suppressed {verb} (repeated {count}x, no escalation path)",
    )


# ── Gate 2: Pending Brain Missions ──────────────────────────────────
# Count active missions that originated from Brain action_hints.


def pending_brain_missions(ctx: object) -> list[dict]:
    """Return active missions that were created by the Brain.

    Deterministic filter on Sankalpa registry.
    Missions created by Brain have source='brain' or id starts with 'brain_'.
    """
    try:
        sankalpa = ctx.sankalpa  # type: ignore[union-attr]
        if sankalpa is None or not hasattr(sankalpa, "registry"):
            return []

        missions = sankalpa.registry.get_active_missions()
        brain_missions = []
        for m in missions:
            mid = getattr(m, "id", "")
            source = getattr(m, "source", "")
            if mid.startswith("brain_") or source == "brain":
                brain_missions.append({
                    "id": mid,
                    "name": getattr(m, "name", ""),
                    "status": (
                        m.status.value
                        if hasattr(m.status, "value")
                        else str(getattr(m, "status", ""))
                    ),
                    "owner": getattr(m, "owner", "unknown"),
                })
        return brain_missions
    except Exception:
        return []


# ── Gate 3: Terminal Brain Missions (Outcome Feedback) ──────────────
# Collect completed/failed brain missions that the Brain hasn't seen yet.


def terminal_brain_missions(ctx: object) -> list[dict]:
    """Return recently-completed brain missions for outcome feedback.

    Looks for terminal missions (completed/failed/timeout) with brain origin.
    Returns dicts suitable for digest cell construction.
    """
    try:
        sankalpa = ctx.sankalpa  # type: ignore[union-attr]
        if sankalpa is None or not hasattr(sankalpa, "registry"):
            return []

        # Get terminal missions (completed, failed, timeout)
        terminal: list[dict] = []
        all_missions = []
        if hasattr(sankalpa.registry, "get_terminal_missions"):
            all_missions = sankalpa.registry.get_terminal_missions()
        elif hasattr(sankalpa.registry, "get_all_missions"):
            all_missions = [
                m for m in sankalpa.registry.get_all_missions()
                if str(getattr(m, "status", "")).lower()
                in ("completed", "failed", "timeout")
            ]

        for m in all_missions:
            mid = getattr(m, "id", "")
            source = getattr(m, "source", "")
            if mid.startswith("brain_") or source == "brain":
                terminal.append({
                    "id": mid,
                    "name": getattr(m, "name", ""),
                    "status": (
                        m.status.value
                        if hasattr(m.status, "value")
                        else str(getattr(m, "status", ""))
                    ),
                    "owner": getattr(m, "owner", "unknown"),
                    "result": getattr(m, "result", None),
                })
        return terminal
    except Exception:
        return []
