"""
BRAIN GATES — Deterministic Python Harness Around Brain Outputs.

Compound Architecture: 24/25 elements are hard deterministic Python.
The Brain (LLM) is 1/25. These gates are the other 24.

Four gates:
1. RepetitionGate: Suppress duplicate action_hints, auto-escalate verbs.
2. pending_brain_missions: Count active brain-created missions.
3. terminal_brain_missions: Collect completed/failed brain missions for feedback.
4. GroundingGate: Verify every event claim in Brain/BrainVoice output traces
   to a concrete metric available at claim-generation time (digest cells,
   context snapshot, city stats). Outputs with untraceable claims are
   suppressed — never posted unverified.

NO prompts. NO LLM calls. Pure Python reflexes.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
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


# ── Gate 4: Grounding Gate ──────────────────────────────────────────
# Verify that every event claim in Brain/BrainVoice output traces to a
# concrete metric available at claim-generation time (digest cells, context
# snapshot, city stats). The LLM writes free prose; this gate deterministically
# extracts the verifiable claim tokens (digest anomaly vocabulary,
# metric=value pairs, canonical metric phrases) and checks each against the
# evidence the LLM was actually given. Outputs with at least one untraceable
# claim MUST NOT be posted unverified — the caller suppresses or flags them.


@dataclass(frozen=True)
class GroundingVerdict:
    """Deterministic verdict from the Grounding Gate.

    grounded: False = output contains at least one event claim that does not
        trace to the generation-time evidence (caller must suppress/flag).
    untraceable_claims: the specific claim tokens that could not be traced.
    reason: human-readable summary for operations/observability.
    """

    grounded: bool
    untraceable_claims: tuple[str, ...] = ()
    reason: str = ""


# Canonical deterministic digest/anomaly vocabulary (mirrors city/brain_digest.py
# and the BrainVoice build_events vocabulary). These are the only crisis/anomaly
# claims the gate recognizes — anything else is unverifiable prose by design.
_ANOMALY_TERMS = (
    "unresponsive_thread",
    "dying_thread_with_unresolved",
    "agent_spam",
    "high_dormancy",
    "prana_inequality",
    "economy_collapsed",
    "chain_integrity_broken",
    "mechanical_pattern_detected",
    "empty_content",
    "too_short",
    "too_long",
    "repeated_sentence",
    "mission_failed",
    "mission_timeout",
    "campaign_gap",
)

# Natural-language phrase variants of the vocabulary → canonical term.
# Exact substring matching only (deterministic; no fuzzy matching).
_ANOMALY_PHRASES = (
    ("unresponsive thread", "unresponsive_thread"),
    ("economy collapsed", "economy_collapsed"),
    ("chain integrity broken", "chain_integrity_broken"),
    ("chain is broken", "chain_integrity_broken"),
    ("agent spam", "agent_spam"),
    ("prana inequality", "prana_inequality"),
    ("high dormancy", "high_dormancy"),
    ("mission failed", "mission_failed"),
    ("mission timeout", "mission_timeout"),
)

# Metric names that appear WITHOUT underscores in prose/digest renderings.
_KNOWN_BARE_METRICS = frozenset({
    "energy", "prana", "alive", "total", "population", "heartbeat",
    "unresolved", "chain_valid", "dormant", "agents",
})

# Claim tokens that are thought plumbing, not event facts — never verified.
_NON_CLAIM_METRICS = frozenset({"confidence", "model", "temperature"})

# Evidence aliases: canonical metric → prose renderings used in prompts.
_METRIC_ALIASES = {
    "agent_count": ("population", "total"),
    "alive_count": ("alive",),
}

# Reverse map: prose rendering → canonical metric (city_stats keys like
# "total"/"active" are the same facts the snapshot calls agent_count/alive_count).
_ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in _METRIC_ALIASES.items()
    for alias in aliases
}


@dataclass(frozen=True)
class _PhraseClaim:
    """A deterministic natural-language phrase → canonical claim token."""

    pattern: re.Pattern
    token: str | None = None


def _canonical_number(value: object) -> str:
    """Canonicalize a numeric value for token comparison (int/float unified)."""
    f = float(value)  # type: ignore[arg-type]
    s = f"{f:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _canonical_value(value: object) -> str:
    """Canonicalize a scalar metric value for token comparison."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    lowered = str(value).strip().lower()
    if lowered == "true":
        return "True"
    if lowered == "false":
        return "False"
    try:
        float(lowered)
    except ValueError:
        return str(value).strip()
    return _canonical_number(lowered)


_CLAIM_METRIC_PAIR_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(-?\d+(?:\.\d+)?|true|false)\b",
    re.IGNORECASE,
)


def _token_human_comments(m: re.Match) -> str:
    return f"human_comments={_canonical_value(m.group(1))}"


def _token_agent_responses(m: re.Match) -> str:
    return f"agent_responses={_canonical_value(m.group(1))}"


def _token_unresolved(m: re.Match) -> str:
    return "unresolved=True"


def _token_alive(m: re.Match) -> str:
    return f"alive_count={_canonical_value(m.group(1))}"


def _token_heartbeat(m: re.Match) -> str:
    return f"heartbeat={_canonical_value(m.group(1))}"


def _token_avg_prana(m: re.Match) -> str:
    return f"avg_prana={_canonical_value(m.group(1))}"


def _token_population_delta(m: re.Match) -> str:
    return f"population_delta={_canonical_value(m.group(1))}"


def _token_mayor(m: re.Match) -> str:
    return f"mayor={m.group(1)}"


def _token_new_citizens(m: re.Match) -> str:
    return f"new_citizens={_canonical_value(m.group(1))}"


def _token_federation_peers(m: re.Match) -> str:
    return f"federation_peers_online={_canonical_value(m.group(1))}"


def _token_pending_applications(m: re.Match) -> str:
    return f"pending_applications={_canonical_value(m.group(1))}"


def _token_relay_messages(m: re.Match) -> str:
    return f"relay_messages_delivered={_canonical_value(m.group(1))}"


def _token_delta(m: re.Match) -> str:
    return f"{m.group(1).lower()}_delta={_canonical_value(m.group(2))}"


# Natural-language metric phrases → canonical claim tokens.
_PHRASE_CLAIMS = (
    (re.compile(r"(\d+)\s+human comments?", re.IGNORECASE), _token_human_comments),
    (re.compile(r"(\d+)\s+agent responses?", re.IGNORECASE), _token_agent_responses),
    (re.compile(r"(\d+)\s+unresolved", re.IGNORECASE), _token_unresolved),
    (re.compile(r"(\d+)\s+agents?\s+alive", re.IGNORECASE), _token_alive),
    (re.compile(r"(\d+)\s+active nodes?", re.IGNORECASE), _token_alive),
    (re.compile(r"heartbeat\s*#?\s*(\d+)", re.IGNORECASE), _token_heartbeat),
    (
        re.compile(r"average prana (?:at|of|is)\s+(\d+(?:\.\d+)?)", re.IGNORECASE),
        _token_avg_prana,
    ),
    (
        re.compile(r"population (?:delta|Δ)[:=]?\s*([+-]?\d+)", re.IGNORECASE),
        _token_population_delta,
    ),
    (re.compile(r"mayor[:=]\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE), _token_mayor),
    (re.compile(r"(\d+)\s+new citizens?", re.IGNORECASE), _token_new_citizens),
    (re.compile(r"(\d+)\s+federation peers?", re.IGNORECASE), _token_federation_peers),
    (
        re.compile(r"(\d+)\s+immigration applications?", re.IGNORECASE),
        _token_pending_applications,
    ),
    (re.compile(r"(\d+)\s+cross-repo messages?", re.IGNORECASE), _token_relay_messages),
    (
        re.compile(r"(synapse|weight) delta[:=]?\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE),
        _token_delta,
    ),
)


_DIGEST_PLUMBING_METRICS = ("seed", "position", "word_count", "line_count", "compression_ratio")


def _extract_claim_tokens(text: str) -> set[str]:
    """Deterministically extract verifiable claim tokens from output prose.

    Only claims the gate can verify are extracted: canonical digest anomaly
    vocabulary, natural-language phrase variants of that vocabulary, and
    metric=value / metric-phrase pairs. Everything else is unverifiable prose
    and is deliberately ignored (no concrete fact is asserted).
    """
    lowered = text.lower()
    claims: set[str] = set()

    for term in _ANOMALY_TERMS:
        if term in lowered:
            claims.add(term)
    for phrase, term in _ANOMALY_PHRASES:
        if phrase in lowered:
            claims.add(term)
    for m in _CLAIM_METRIC_PAIR_RE.finditer(text):
        name = m.group(1).lower()
        if name in _NON_CLAIM_METRICS:
            continue
        if "_" in name or name in _KNOWN_BARE_METRICS:
            claims.add(f"{name}={_canonical_value(m.group(2))}")
    for pattern, token_fn in _PHRASE_CLAIMS:
        for m in pattern.finditer(text):
            claims.add(token_fn(m))
    return claims


def _dict_to_tokens(data: dict, tokens: set[str]) -> None:
    """Flatten a metrics dict into canonical fact tokens (one level deep)."""
    for key, value in data.items():
        k = str(key).lower()
        if isinstance(value, bool) or isinstance(value, (int, float)):
            tokens.add(f"{k}={_canonical_value(value)}")
            canonical = _ALIAS_TO_CANONICAL.get(k)
            if canonical is not None:
                tokens.add(f"{canonical}={_canonical_value(value)}")
            for alias in _METRIC_ALIASES.get(k, ()):
                tokens.add(f"{alias}={_canonical_value(value)}")
        elif isinstance(value, str):
            tokens.add(f"{k}={_canonical_value(value)}")
            if value.strip():
                tokens.add(value.strip())
        elif isinstance(value, (list, tuple)):
            tokens.add(f"{k}={len(value)}")
            for item in value:
                if isinstance(item, str) and item.strip():
                    tokens.add(item.strip())
        elif isinstance(value, dict):
            for ik, iv in value.items():
                if isinstance(iv, (bool, int, float, str)):
                    flat = f"{str(ik).lower()}={_canonical_value(iv)}"
                    tokens.add(flat)
                    tokens.add(f"{k}.{str(ik).lower()}={_canonical_value(iv)}")


_SCALAR_SNAPSHOT_FIELDS = (
    "agent_count", "alive_count", "dead_count", "chain_valid",
    "recent_events_count", "audit_findings_count", "venu_tick",
)

_SNAPSHOT_DICT_FIELDS = (
    "economy_stats", "discussion_activity", "immune_stats",
    "learning_stats", "council_summary", "thread_stats", "heartbeat_health",
)


def _snapshot_to_tokens(snapshot: object, tokens: set[str]) -> None:
    """Flatten a ContextSnapshot into canonical fact tokens."""
    for field in _SCALAR_SNAPSHOT_FIELDS:
        value = getattr(snapshot, field, None)
        if value is not None:
            tokens.add(f"{field}={_canonical_value(value)}")
            for alias in _METRIC_ALIASES.get(field, ()):
                tokens.add(f"{alias}={_canonical_value(value)}")
    for field in _SNAPSHOT_DICT_FIELDS:
        data = getattr(snapshot, field, None) or {}
        if isinstance(data, dict):
            _dict_to_tokens(data, tokens)
    for name in getattr(snapshot, "failing_contracts", ()) or ():
        tokens.add(f"failing_contract={name}")
    for finding in getattr(snapshot, "critical_findings", ()) or ():
        tokens.add(f"critical_finding={finding}")
    for mission in getattr(snapshot, "active_missions", ()) or ():
        if isinstance(mission, dict):
            status = mission.get("status")
            name = mission.get("name")
        else:
            status = getattr(mission, "status", "")
            name = getattr(mission, "name", "")
        if status:
            tokens.add(f"mission_status={_canonical_value(status)}")
        if name:
            tokens.add(f"mission_name={name}")
    for campaign in getattr(snapshot, "active_campaigns", ()) or ():
        if isinstance(campaign, dict):
            status = campaign.get("status")
        else:
            status = getattr(campaign, "status", "")
        if status:
            tokens.add(f"campaign_status={_canonical_value(status)}")


def build_grounding_evidence(
    *,
    snapshot: object | None = None,
    field_summary: str = "",
    city_stats: dict | None = None,
    cells: Iterable[object] | None = None,
    heartbeat: int | None = None,
    extra: dict | None = None,
) -> set[str]:
    """Assemble the canonical fact tokens available at claim-generation time.

    Every source is deterministic and comes from the same context the LLM was
    given: digest cells (anomaly vocabulary + key_metrics), the rendered field
    digest, the context snapshot, city stats, and any extra deterministic
    context (outcome_diff, event strings, telemetry).
    """
    tokens: set[str] = set()

    for cell in cells or ():
        for anomaly in getattr(cell, "anomalies", ()) or ():
            tokens.add(str(anomaly))
            for term in _ANOMALY_TERMS:
                if term in str(anomaly):
                    tokens.add(term)
        metrics = getattr(cell, "key_metrics", None) or {}
        if isinstance(metrics, dict):
            _dict_to_tokens(metrics, tokens)
        for field in _DIGEST_PLUMBING_METRICS:
            value = getattr(cell, field, None)
            if value is not None:
                tokens.add(f"{field}={_canonical_value(value)}")
        severity = getattr(cell, "severity", None)
        if severity is not None:
            name = getattr(severity, "name", None) or severity
            tokens.add(f"severity={name}")

    if field_summary:
        tokens |= _extract_claim_tokens(field_summary)
    if snapshot is not None:
        _snapshot_to_tokens(snapshot, tokens)
    if city_stats:
        _dict_to_tokens(city_stats, tokens)
    if extra:
        _dict_to_tokens(extra, tokens)
    if heartbeat is not None:
        tokens.add(f"heartbeat={_canonical_value(heartbeat)}")

    return tokens


def check_grounding(
    text: str,
    *,
    snapshot: object | None = None,
    field_summary: str = "",
    city_stats: dict | None = None,
    cells: Iterable[object] | None = None,
    heartbeat: int | None = None,
    extra: dict | None = None,
) -> GroundingVerdict:
    """Grounding Gate: verify posted-claim traceability before posting.

    Extracts verifiable claim tokens from the output text and checks every one
    against the evidence available at claim-generation time. Outputs with at
    least one untraceable claim are ungrounded and MUST NOT be posted
    unverified (the caller suppresses or flags). Outputs with no verifiable
    claims pass — nothing concrete is asserted.
    """
    evidence = build_grounding_evidence(
        snapshot=snapshot,
        field_summary=field_summary,
        city_stats=city_stats,
        cells=cells,
        heartbeat=heartbeat,
        extra=extra,
    )
    claims = _extract_claim_tokens(text)
    untraceable = tuple(sorted(c for c in claims if c not in evidence))
    if untraceable:
        return GroundingVerdict(
            grounded=False,
            untraceable_claims=untraceable,
            reason=f"untraceable claims: {', '.join(untraceable)}",
        )
    return GroundingVerdict(grounded=True)
