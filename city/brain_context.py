"""
BRAIN CONTEXT — Dynamic Context Snapshot for Brain Cognition.

Assembles system state from available services. No hardcoded prompts —
the snapshot IS the prompt.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.BRAIN_CONTEXT")


@dataclass(frozen=True)
class ContextSnapshot:
    """Immutable snapshot of city system state for brain cognition."""

    agent_count: int = 0
    alive_count: int = 0
    dead_count: int = 0
    chain_valid: bool = True
    failing_contracts: tuple[str, ...] = ()
    learning_stats: dict = None  # type: ignore[assignment]
    immune_stats: dict = None  # type: ignore[assignment]
    council_summary: dict = None  # type: ignore[assignment]
    recent_events_count: int = 0
    recent_brain_thoughts: tuple[dict, ...] = ()
    audit_findings_count: int = 0
    critical_findings: tuple[str, ...] = ()
    venu_tick: int = 0
    murali_phase: str = ""

    def __post_init__(self) -> None:
        # Replace None with empty dicts (frozen workaround)
        if self.learning_stats is None:
            object.__setattr__(self, "learning_stats", {})
        if self.immune_stats is None:
            object.__setattr__(self, "immune_stats", {})
        if self.council_summary is None:
            object.__setattr__(self, "council_summary", {})

    def to_system_context(self, kind: str) -> str:
        """Format as system prompt section. Content varies by ThoughtKind."""
        parts: list[str] = []

        if kind == "health_check":
            parts.append(
                f"City status: {self.alive_count}/{self.agent_count} agents alive, "
                f"{self.dead_count} dead."
            )
            parts.append(
                f"Chain integrity: {'valid' if self.chain_valid else 'BROKEN'}."
            )
            if self.failing_contracts:
                parts.append(
                    f"Failing contracts: {', '.join(self.failing_contracts[:5])}."
                )
            if self.immune_stats:
                breaker = self.immune_stats.get("breaker_tripped", False)
                attempts = self.immune_stats.get("heals_attempted", 0)
                parts.append(
                    f"Immune: {attempts} heal attempts, "
                    f"breaker {'TRIPPED' if breaker else 'ok'}."
                )
            if self.learning_stats:
                avg_w = self.learning_stats.get("avg_weight", 0)
                synapses = self.learning_stats.get("synapses", 0)
                parts.append(
                    f"Learning: {synapses} synapses, avg weight {avg_w:.2f}."
                )
            if self.council_summary:
                mayor = self.council_summary.get("mayor", "none")
                seats = self.council_summary.get("seats_filled", 0)
                parts.append(f"Council: mayor={mayor}, {seats} seats filled.")
            parts.append(
                "Evaluate system health. Identify bottlenecks or anomalies. "
                "Respond with JSON: "
                '{"comprehension": "1-2 sentence health assessment", '
                '"intent": "propose|inquiry|govern|observe|connect", '
                '"domain_relevance": "which domain is affected", '
                '"key_concepts": ["up to 5"], '
                '"confidence": 0.0 to 1.0, '
                '"action_hint": "" or "flag_bottleneck:<domain>" or "investigate:<topic>", '
                '"evidence": ["up to 3 data points"]}'
            )

        elif kind == "reflection":
            parts.append(
                f"End of MURALI rotation. {self.alive_count}/{self.agent_count} alive."
            )
            if self.recent_brain_thoughts:
                summaries = []
                for t in self.recent_brain_thoughts[-3:]:
                    thought = t.get("thought", {})
                    summaries.append(
                        f"hb#{t.get('heartbeat', '?')}: "
                        f"{thought.get('intent', '?')} "
                        f"(conf={thought.get('confidence', 0):.0%})"
                    )
                parts.append(f"Recent brain thoughts: {'; '.join(summaries)}.")
            if self.audit_findings_count:
                parts.append(f"Audit findings: {self.audit_findings_count}.")
            if self.critical_findings:
                parts.append(
                    f"Critical: {', '.join(self.critical_findings[:3])}."
                )
            parts.append(
                "Reflect on this cycle. What worked? What should change? "
                "Respond with JSON: "
                '{"comprehension": "1-2 sentence reflection", '
                '"intent": "propose|inquiry|govern|observe|connect", '
                '"domain_relevance": "which domain", '
                '"key_concepts": ["up to 5"], '
                '"confidence": 0.0 to 1.0, '
                '"action_hint": "" or "create_mission:<description>" or "investigate:<topic>", '
                '"evidence": ["up to 3 observations"]}'
            )

        else:
            # COMPREHENSION: minimal context (backward compat)
            parts.append(
                f"City: {self.alive_count}/{self.agent_count} agents alive."
            )

        return " ".join(parts)


# ── Snapshot Diffing ──────────────────────────────────────────────────


def diff_snapshots(before: ContextSnapshot, after: ContextSnapshot) -> dict:
    """Compute meaningful delta between two snapshots.

    Pure data — no LLM, no side effects.
    """
    before_failing = set(before.failing_contracts)
    after_failing = set(after.failing_contracts)
    return {
        "agent_delta": after.alive_count - before.alive_count,
        "chain_changed": before.chain_valid != after.chain_valid,
        "new_failing": tuple(c for c in after.failing_contracts if c not in before_failing),
        "resolved": tuple(c for c in before.failing_contracts if c not in after_failing),
        "learning_delta": {
            "synapse_delta": (
                after.learning_stats.get("synapses", 0)
                - before.learning_stats.get("synapses", 0)
            ),
            "weight_delta": round(
                after.learning_stats.get("avg_weight", 0)
                - before.learning_stats.get("avg_weight", 0),
                4,
            ),
        },
    }


# ── Before-Snapshot Disk Persistence (Fix #1: Ephemeral Registry Trap) ─

_BEFORE_SNAPSHOT_FILENAME = "before_snapshot.json"


def save_before_snapshot(snapshot: ContextSnapshot, state_dir: Path) -> None:
    """Persist before_snapshot to disk so it survives GitHub Actions runner death."""
    path = state_dir / _BEFORE_SNAPSHOT_FILENAME
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "agent_count": snapshot.agent_count,
            "alive_count": snapshot.alive_count,
            "dead_count": snapshot.dead_count,
            "chain_valid": snapshot.chain_valid,
            "failing_contracts": list(snapshot.failing_contracts),
            "learning_stats": snapshot.learning_stats,
            "immune_stats": snapshot.immune_stats,
            "council_summary": snapshot.council_summary,
            "recent_events_count": snapshot.recent_events_count,
            "audit_findings_count": snapshot.audit_findings_count,
            "critical_findings": list(snapshot.critical_findings),
            "venu_tick": snapshot.venu_tick,
            "murali_phase": snapshot.murali_phase,
        }
        path.write_text(json.dumps(data, indent=2))
        logger.debug("Saved before_snapshot to %s", path)
    except Exception as e:
        logger.warning("Failed to save before_snapshot: %s", e)


def load_before_snapshot(state_dir: Path) -> ContextSnapshot | None:
    """Load before_snapshot from disk. Returns None if missing or corrupt."""
    path = state_dir / _BEFORE_SNAPSHOT_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        snap = ContextSnapshot(
            agent_count=data.get("agent_count", 0),
            alive_count=data.get("alive_count", 0),
            dead_count=data.get("dead_count", 0),
            chain_valid=data.get("chain_valid", True),
            failing_contracts=tuple(data.get("failing_contracts", [])),
            learning_stats=data.get("learning_stats", {}),
            immune_stats=data.get("immune_stats", {}),
            council_summary=data.get("council_summary", {}),
            recent_events_count=data.get("recent_events_count", 0),
            audit_findings_count=data.get("audit_findings_count", 0),
            critical_findings=tuple(data.get("critical_findings", [])),
            venu_tick=data.get("venu_tick", 0),
            murali_phase=data.get("murali_phase", ""),
        )
        # Clean up after loading (one-shot: prevents stale reads)
        path.unlink(missing_ok=True)
        logger.debug("Loaded before_snapshot from %s", path)
        return snap
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning("Failed to load before_snapshot: %s", e)
        return None


def build_context_snapshot(ctx: object) -> ContextSnapshot:
    """Assemble ContextSnapshot from PhaseContext services.

    Pure data assembly. Handles None services gracefully.
    """
    # Pokedex stats
    stats: dict = {}
    try:
        stats = ctx.pokedex.stats()  # type: ignore[union-attr]
    except Exception:
        pass

    total = stats.get("total", 0)
    active = stats.get("active", 0) + stats.get("citizen", 0)

    # Chain validity
    chain_valid = True
    try:
        chain_valid = ctx.pokedex.verify_event_chain()  # type: ignore[union-attr]
    except Exception:
        pass

    # Failing contracts
    failing: list[str] = []
    try:
        contracts = ctx.contracts  # type: ignore[union-attr]
        if contracts is not None:
            for c in contracts.failing():
                failing.append(c.name)
    except Exception:
        pass

    # Learning stats
    learning_stats: dict = {}
    try:
        learning = ctx.learning  # type: ignore[union-attr]
        if learning is not None:
            learning_stats = learning.stats() or {}
    except Exception:
        pass

    # Immune stats
    immune_stats: dict = {}
    try:
        immune = ctx.immune  # type: ignore[union-attr]
        if immune is not None:
            immune_stats = immune.stats() or {}
    except Exception:
        pass

    # Council summary
    council_summary: dict = {}
    try:
        council = ctx.council  # type: ignore[union-attr]
        if council is not None:
            council_summary = {
                "mayor": council.elected_mayor or "none",
                "seats_filled": council.member_count,
                "open_proposals": len(council.get_open_proposals()),
            }
    except Exception:
        pass

    # Audit findings
    audit_count = 0
    critical: list[str] = []
    try:
        audit = ctx.audit  # type: ignore[union-attr]
        if audit is not None:
            summary = audit.summary()
            audit_count = summary.get("total_findings", 0) if summary else 0
            for f in audit.critical_findings():
                critical.append(str(getattr(f, "message", f))[:80])
    except Exception:
        pass

    # Brain memory
    brain_thoughts: list[dict] = []
    try:
        brain_memory = ctx.brain_memory  # type: ignore[union-attr]
        if brain_memory is not None:
            brain_thoughts = brain_memory.recent(6)
    except Exception:
        pass

    # Recent events count
    events_count = 0
    try:
        events_count = len(ctx.recent_events)  # type: ignore[union-attr]
    except Exception:
        pass

    # Heartbeat / phase info
    venu_tick = 0
    murali_phase = ""
    try:
        venu_tick = ctx.heartbeat_count  # type: ignore[union-attr]
    except Exception:
        pass
    try:
        # Derive phase name from heartbeat position in MURALI rotation
        _PHASE_NAMES = {0: "GENESIS", 1: "DHARMA", 2: "KARMA", 3: "MOKSHA"}
        murali_phase = _PHASE_NAMES.get(venu_tick % 4, "")
    except Exception:
        pass

    return ContextSnapshot(
        agent_count=total,
        alive_count=active,
        dead_count=total - active,
        chain_valid=chain_valid,
        failing_contracts=tuple(failing[:10]),
        learning_stats=learning_stats,
        immune_stats=immune_stats,
        council_summary=council_summary,
        recent_events_count=events_count,
        recent_brain_thoughts=tuple(brain_thoughts),
        audit_findings_count=audit_count,
        critical_findings=tuple(critical[:5]),
        venu_tick=venu_tick,
        murali_phase=murali_phase,
    )
