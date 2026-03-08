"""
BRAIN DIGEST — Adapted MahaCompression for Brain-Readable Field Summaries.

The Brain is the Kshetrajna (Knower of the Field). The Field is the entire
system: agent outputs, mission results, thread states, economy, workflows.

MahaCompression gives us: seed (deterministic address), position, ratio.
BrainDigest ADAPTS this by adding: content-aware extraction, anomaly flags,
structural markers — all deterministic, no AI needed for the compression.

The result: DigestCell — a compact, Brain-readable summary of any system
artifact. The Brain prompt consumes DigestCells, not raw data dumps.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from vibe_core.mahamantra.adapters.compression import MahaCompression

logger = logging.getLogger("AGENT_CITY.BRAIN_DIGEST")

# Singleton compression — reuse across all digest calls
_compression: MahaCompression | None = None


def _get_compression() -> MahaCompression:
    global _compression
    if _compression is None:
        _compression = MahaCompression()
    return _compression


# ── Anomaly Severity ─────────────────────────────────────────────────


class Severity(IntEnum):
    """Anomaly severity levels for Brain triage."""
    NONE = 0       # Clean — no issues detected
    INFO = 1       # Notable but not problematic
    WARNING = 2    # Potential issue — Brain should investigate
    CRITICAL = 3   # Definite problem — Brain must act


class DigestKind(StrEnum):
    """What type of system artifact was digested."""
    AGENT_OUTPUT = "agent_output"
    MISSION_RESULT = "mission_result"
    CAMPAIGN_STATUS = "campaign_status"
    THREAD_STATE = "thread_state"
    ECONOMY_SNAPSHOT = "economy_snapshot"
    WORKFLOW_EVENT = "workflow_event"
    AGENT_SPEC = "agent_spec"
    RAW_TEXT = "raw_text"


# ── DigestCell ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class DigestCell:
    """Brain-readable compressed summary of a system artifact.

    Combines MahaCompression (seed/position) with content-aware extraction.
    Deterministic: same input always produces same DigestCell.
    """

    kind: DigestKind
    seed: int                              # MahaCompression deterministic seed
    position: int                          # MahaCompression position
    content_hash: str                      # SHA-256 prefix (dedup/identity)
    word_count: int                        # Raw word count of source
    line_count: int                        # Raw line count of source
    compression_ratio: float               # MahaCompression ratio
    severity: Severity = Severity.NONE     # Anomaly detection result
    anomalies: tuple[str, ...] = ()        # Specific anomaly descriptions
    key_metrics: dict = field(default_factory=dict)  # Extracted numeric facts
    summary: str = ""                      # Deterministic content summary (no AI)
    source_label: str = ""                 # Human-readable origin (e.g. "sys_vyasa:#26")

    def render_for_brain(self) -> str:
        """Render as compact Brain-readable text block."""
        parts = [f"[{self.kind.value}] {self.source_label}"]
        parts.append(
            f"  seed={self.seed} pos={self.position} "
            f"words={self.word_count} ratio={self.compression_ratio:.1f}"
        )
        if self.summary:
            parts.append(f"  digest: {self.summary}")
        if self.key_metrics:
            metrics_str = ", ".join(f"{k}={v}" for k, v in self.key_metrics.items())
            parts.append(f"  metrics: {metrics_str}")
        if self.severity >= Severity.WARNING:
            parts.append(f"  ⚠ severity={self.severity.name}: {'; '.join(self.anomalies)}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Serialize for storage/logging."""
        return {
            "kind": self.kind.value,
            "seed": self.seed,
            "position": self.position,
            "content_hash": self.content_hash,
            "word_count": self.word_count,
            "line_count": self.line_count,
            "compression_ratio": self.compression_ratio,
            "severity": self.severity.value,
            "anomalies": list(self.anomalies),
            "key_metrics": self.key_metrics,
            "summary": self.summary,
            "source_label": self.source_label,
        }


# ── Core Digest Functions ────────────────────────────────────────────


def _base_digest(text: str) -> tuple[int, int, str, int, int, float]:
    """Extract base metrics from raw text via MahaCompression + hashing."""
    comp = _get_compression()
    result = comp.compress(text)

    content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    words = text.split()
    lines = text.strip().split("\n") if text.strip() else []

    return (
        result.seed,
        result.position,
        content_hash,
        len(words),
        len(lines),
        result.compression_ratio,
    )


# ── Anomaly Detection (deterministic, no AI) ────────────────────────

# Repetition: same sentence appearing 3+ times
_REPETITION_THRESHOLD = 3
# Suspiciously short output for a "response"
_MIN_MEANINGFUL_WORDS = 5
# Suspiciously long output (likely dump, not thought)
_MAX_REASONABLE_WORDS = 500
# Patterns indicating templated/mechanical output
_MECHANICAL_PATTERNS = [
    re.compile(r"(?:Gunatraya|Triguṇa|three modes).*(?:Gunatraya|Triguṇa|three modes)", re.I),
    re.compile(r"(?:sattva|rajas|tamas).*(?:sattva|rajas|tamas).*(?:sattva|rajas|tamas)", re.I),
]


def _detect_anomalies(text: str, word_count: int) -> tuple[Severity, list[str]]:
    """Deterministic anomaly detection on text content."""
    anomalies: list[str] = []
    severity = Severity.NONE

    # Check for sentence-level repetition
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip().lower() for s in sentences if len(s.strip()) > 10]
    if sentences:
        from collections import Counter
        counts = Counter(sentences)
        for sent, count in counts.most_common(3):
            if count >= _REPETITION_THRESHOLD:
                anomalies.append(f"repeated_sentence({count}x): '{sent[:40]}...'")
                severity = max(severity, Severity.WARNING)

    # Check for too-short output
    if word_count < _MIN_MEANINGFUL_WORDS:
        anomalies.append(f"too_short({word_count} words)")
        severity = max(severity, Severity.INFO)

    # Check for too-long output (dump, not thought)
    if word_count > _MAX_REASONABLE_WORDS:
        anomalies.append(f"too_long({word_count} words, likely raw dump)")
        severity = max(severity, Severity.INFO)

    # Check for mechanical/templated patterns
    for pattern in _MECHANICAL_PATTERNS:
        if pattern.search(text):
            anomalies.append("mechanical_pattern_detected")
            severity = max(severity, Severity.WARNING)
            break

    # Check for empty or whitespace-only
    if not text.strip():
        anomalies.append("empty_content")
        severity = max(severity, Severity.CRITICAL)

    return severity, anomalies


# ── Digest Builders (per DigestKind) ─────────────────────────────────


def digest_agent_output(
    text: str,
    agent_name: str = "",
    discussion_number: int = 0,
) -> DigestCell:
    """Digest an agent's discussion response for Brain evaluation."""
    seed, position, content_hash, wc, lc, ratio = _base_digest(text)
    severity, anomalies = _detect_anomalies(text, wc)

    # Extract key metrics from the output
    metrics: dict = {"word_count": wc}
    if "Comprehension" in text:
        metrics["has_brain_thought"] = True
    if "Routed:" in text:
        # Extract routing score if present
        match = re.search(r"score=([\d.]+)", text)
        if match:
            metrics["routing_score"] = float(match.group(1))

    # Build deterministic summary (first meaningful line + stats)
    first_line = ""
    for line in text.strip().split("\n"):
        stripped = line.strip()
        if stripped and len(stripped) > 10:
            first_line = stripped[:80]
            break

    label = f"{agent_name}:#{discussion_number}" if agent_name else "unknown"

    return DigestCell(
        kind=DigestKind.AGENT_OUTPUT,
        seed=seed,
        position=position,
        content_hash=content_hash,
        word_count=wc,
        line_count=lc,
        compression_ratio=ratio,
        severity=severity,
        anomalies=tuple(anomalies),
        key_metrics=metrics,
        summary=first_line,
        source_label=label,
    )


def digest_mission_result(
    result: dict,
    mission_id: str = "",
) -> DigestCell:
    """Digest a mission result dict for Brain evaluation."""
    text = str(result)
    seed, position, content_hash, wc, lc, ratio = _base_digest(text)

    status = result.get("status", "unknown")
    owner = result.get("owner", "unknown")
    anomalies: list[str] = []
    severity = Severity.NONE

    if status == "failed":
        anomalies.append(f"mission_failed:{mission_id}")
        severity = Severity.WARNING
    if status == "timeout":
        anomalies.append(f"mission_timeout:{mission_id}")
        severity = Severity.WARNING

    metrics = {
        "status": status,
        "owner": owner,
    }
    if "duration" in result:
        metrics["duration_s"] = result["duration"]
    if "pr_number" in result:
        metrics["pr_number"] = result["pr_number"]

    return DigestCell(
        kind=DigestKind.MISSION_RESULT,
        seed=seed,
        position=position,
        content_hash=content_hash,
        word_count=wc,
        line_count=lc,
        compression_ratio=ratio,
        severity=severity,
        anomalies=tuple(anomalies),
        key_metrics=metrics,
        summary=f"{mission_id}: {status} (owner={owner})",
        source_label=f"mission:{mission_id}",
    )


def digest_campaign_status(campaign: dict) -> DigestCell:
    """Digest a strategic campaign summary for Brain orientation."""
    text = str(campaign)
    seed, position, content_hash, wc, lc, ratio = _base_digest(text)

    campaign_id = campaign.get("id", "?")
    title = campaign.get("title") or campaign_id
    status = campaign.get("status", "unknown")
    gaps = tuple(campaign.get("last_gap_summary", [])[:3])
    severity = Severity.INFO if gaps else Severity.NONE
    anomalies = tuple(f"campaign_gap:{campaign_id}:{gap}" for gap in gaps)

    metrics: dict = {
        "status": status,
        "gap_count": len(gaps),
    }
    if "last_evaluated_heartbeat" in campaign:
        metrics["last_evaluated_heartbeat"] = campaign["last_evaluated_heartbeat"]

    summary = f"{title}: {status}"
    if gaps:
        summary += f" | gaps={'; '.join(gaps)}"

    return DigestCell(
        kind=DigestKind.CAMPAIGN_STATUS,
        seed=seed,
        position=position,
        content_hash=content_hash,
        word_count=wc,
        line_count=lc,
        compression_ratio=ratio,
        severity=severity,
        anomalies=anomalies,
        key_metrics=metrics,
        summary=summary,
        source_label=f"campaign:{campaign_id}",
    )


def digest_thread_state(
    discussion_number: int,
    status: str,
    energy: float,
    human_count: int,
    response_count: int,
    unresolved: bool,
    last_human_author: str = "",
) -> DigestCell:
    """Digest thread state for Brain evaluation."""
    text = (
        f"thread #{discussion_number} status={status} energy={energy:.2f} "
        f"human_comments={human_count} responses={response_count} "
        f"unresolved={unresolved} last_human={last_human_author}"
    )
    seed, position, content_hash, wc, lc, ratio = _base_digest(text)

    anomalies: list[str] = []
    severity = Severity.NONE

    # Anomaly: high human comments but low responses (agent not engaging)
    if human_count > 3 and response_count == 0:
        anomalies.append(f"unresponsive_thread({human_count} human, 0 agent)")
        severity = Severity.WARNING

    # Anomaly: energy near zero but unresolved
    if energy < 0.1 and unresolved:
        anomalies.append("dying_thread_with_unresolved")
        severity = Severity.WARNING

    # Anomaly: response_count >> human_count (agent spamming)
    if response_count > human_count * 2 and response_count > 3:
        anomalies.append(f"agent_spam({response_count} responses vs {human_count} human)")
        severity = Severity.CRITICAL

    metrics = {
        "energy": round(energy, 2),
        "human_comments": human_count,
        "agent_responses": response_count,
        "unresolved": unresolved,
    }

    return DigestCell(
        kind=DigestKind.THREAD_STATE,
        seed=seed,
        position=position,
        content_hash=content_hash,
        word_count=wc,
        line_count=lc,
        compression_ratio=ratio,
        severity=severity,
        anomalies=tuple(anomalies),
        key_metrics=metrics,
        summary=f"#{discussion_number}: {status} (energy={energy:.2f})",
        source_label=f"thread:#{discussion_number}",
    )


def digest_economy(
    total_prana: int,
    avg_prana: float,
    dormant_count: int,
    agent_count: int,
    min_prana: int = 0,
    max_prana: int = 0,
) -> DigestCell:
    """Digest economy snapshot for Brain evaluation."""
    text = (
        f"economy: total={total_prana} avg={avg_prana:.1f} dormant={dormant_count} "
        f"agents={agent_count} min={min_prana} max={max_prana}"
    )
    seed, position, content_hash, wc, lc, ratio = _base_digest(text)

    anomalies: list[str] = []
    severity = Severity.NONE

    # Anomaly: high dormancy rate
    if agent_count > 0 and dormant_count / agent_count > 0.5:
        anomalies.append(f"high_dormancy({dormant_count}/{agent_count}={dormant_count/agent_count:.0%})")
        severity = Severity.WARNING

    # Anomaly: extreme prana inequality
    if max_prana > 0 and min_prana == 0 and agent_count > 5:
        anomalies.append("prana_inequality(some agents at 0)")
        severity = Severity.WARNING

    # Anomaly: economy collapse
    if total_prana == 0 and agent_count > 0:
        anomalies.append("economy_collapsed(total_prana=0)")
        severity = Severity.CRITICAL

    metrics = {
        "total_prana": total_prana,
        "avg_prana": round(avg_prana, 1),
        "dormant": dormant_count,
        "agents": agent_count,
        "gini_proxy": round(max_prana / max(avg_prana, 1), 2) if avg_prana > 0 else 0,
    }

    return DigestCell(
        kind=DigestKind.ECONOMY_SNAPSHOT,
        seed=seed,
        position=position,
        content_hash=content_hash,
        word_count=wc,
        line_count=lc,
        compression_ratio=ratio,
        severity=severity,
        anomalies=tuple(anomalies),
        key_metrics=metrics,
        summary=f"prana={total_prana}, {agent_count} agents, {dormant_count} dormant",
        source_label="economy",
    )


def digest_text(text: str, label: str = "") -> DigestCell:
    """Generic text digest — for any unstructured system output."""
    seed, position, content_hash, wc, lc, ratio = _base_digest(text)
    severity, anomalies = _detect_anomalies(text, wc)

    first_line = ""
    for line in text.strip().split("\n"):
        stripped = line.strip()
        if stripped and len(stripped) > 10:
            first_line = stripped[:80]
            break

    return DigestCell(
        kind=DigestKind.RAW_TEXT,
        seed=seed,
        position=position,
        content_hash=content_hash,
        word_count=wc,
        line_count=lc,
        compression_ratio=ratio,
        severity=severity,
        anomalies=tuple(anomalies),
        key_metrics={"word_count": wc, "line_count": lc},
        summary=first_line,
        source_label=label,
    )


# ── Token Budget Estimation ──────────────────────────────────────────

# Rough token-per-char ratio (conservative for mixed prose/data)
_CHARS_PER_TOKEN = 4
# Default max chars for field summary (fits ~1000 tokens)
_DEFAULT_MAX_CHARS = 4000
# Minimum chars — always allow at least critical items
_MIN_CHARS = 800
# Max chars — even with infinite budget, cap total context
_MAX_CHARS = 12000


def estimate_token_budget(
    remaining_prana: int,
    prana_per_call: int = 9,
    base_tokens: int = 1000,
) -> int:
    """Estimate how many characters the field summary can use.

    10E: Dynamic budget — more prana = more context for the Brain.
    The compression ratio adjusts to available resources.

    Formula: base_tokens + (remaining_prana / prana_per_call) * 500 tokens
    Each additional 'call worth' of prana buys 500 more tokens of context.
    Clamped to [_MIN_CHARS, _MAX_CHARS].
    """
    calls_worth = remaining_prana / max(prana_per_call, 1)
    extra_tokens = int(calls_worth * 500)
    total_chars = (base_tokens + extra_tokens) * _CHARS_PER_TOKEN
    return max(_MIN_CHARS, min(total_chars, _MAX_CHARS))


# ── Batch Digest (Field Summary) ────────────────────────────────────


def render_field_summary(
    cells: list[DigestCell],
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """Render a batch of DigestCells as a compact Brain-readable field summary.

    10E: Dynamic budget — max_chars controls total output size.
    Critical/warning cells always included. Low-severity cells truncated
    when budget is tight. Higher severity = higher priority for inclusion.

    This is the Kshetra (Field) report — what the Kshetrajna (Brain) reads.
    """
    if not cells:
        return "[FIELD EMPTY — no artifacts to evaluate]"

    # Sort: critical first, then by kind for grouping
    sorted_cells = sorted(cells, key=lambda c: (-c.severity, c.kind.value))

    # Count anomalies
    total = len(cells)
    warnings = sum(1 for c in cells if c.severity >= Severity.WARNING)
    critical = sum(1 for c in cells if c.severity >= Severity.CRITICAL)

    header = (
        f"[FIELD SUMMARY] {total} artifacts | "
        f"{critical} critical | {warnings} warnings"
    )
    parts = [header]
    used = len(header)

    if critical > 0:
        line = "⚠ CRITICAL ISSUES REQUIRE IMMEDIATE ATTENTION:"
        parts.append(line)
        used += len(line)

    # Phase 1: always include critical + warning cells
    included = 0
    skipped = 0
    for cell in sorted_cells:
        rendered = cell.render_for_brain()
        if cell.severity >= Severity.WARNING:
            # Always include warnings/critical regardless of budget
            parts.append(rendered)
            used += len(rendered)
            included += 1
        elif used + len(rendered) <= max_chars:
            # Include lower severity only if budget allows
            parts.append(rendered)
            used += len(rendered)
            included += 1
        else:
            skipped += 1

    if skipped > 0:
        note = f"[{skipped} low-severity artifacts omitted — budget={max_chars} chars]"
        parts.append(note)

    return "\n".join(parts)
