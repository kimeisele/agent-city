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
    # 6C-4: Rich context fields
    agent_roster: tuple[dict, ...] = ()       # [{name, domain, status, prana}]
    economy_stats: dict = None  # type: ignore[assignment]  # {total_prana, avg_prana, dormant, ...}
    discussion_activity: dict = None  # type: ignore[assignment]  # {unreplied, total_seen, ...}
    active_missions: tuple[dict, ...] = ()    # [{id, name, status, owner}]
    thread_stats: dict = None  # type: ignore[assignment]  # comment ledger stats

    def __post_init__(self) -> None:
        # Replace None with empty dicts (frozen workaround)
        if self.learning_stats is None:
            object.__setattr__(self, "learning_stats", {})
        if self.immune_stats is None:
            object.__setattr__(self, "immune_stats", {})
        if self.council_summary is None:
            object.__setattr__(self, "council_summary", {})
        if self.economy_stats is None:
            object.__setattr__(self, "economy_stats", {})
        if self.discussion_activity is None:
            object.__setattr__(self, "discussion_activity", {})
        if self.thread_stats is None:
            object.__setattr__(self, "thread_stats", {})


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
            "agent_roster": list(snapshot.agent_roster),
            "economy_stats": snapshot.economy_stats,
            "discussion_activity": snapshot.discussion_activity,
            "active_missions": list(snapshot.active_missions),
            "thread_stats": snapshot.thread_stats,
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
            agent_roster=tuple(data.get("agent_roster", [])),
            economy_stats=data.get("economy_stats", {}),
            discussion_activity=data.get("discussion_activity", {}),
            active_missions=tuple(data.get("active_missions", [])),
            thread_stats=data.get("thread_stats", {}),
        )
        # Clean up after loading (one-shot: prevents stale reads)
        path.unlink(missing_ok=True)
        logger.debug("Loaded before_snapshot from %s", path)
        return snap
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning("Failed to load before_snapshot: %s", e)
        return None


def build_field_digest(ctx: object) -> str:
    """Assemble BrainDigest field summary from PhaseContext services.

    10A: Adapted MahaCompression — compresses system state into
    Brain-readable DigestCells. Returns rendered field summary string.
    """
    from city.brain_digest import (
        digest_economy,
        digest_thread_state,
        render_field_summary,
        DigestCell,
    )

    cells: list[DigestCell] = []

    # Economy digest
    try:
        pokedex = ctx.pokedex  # type: ignore[union-attr]
        if pokedex is not None:
            all_agents = pokedex.list_all()
            pranas = [a.get("prana", 0) for a in all_agents if a.get("prana") is not None]
            dormant_count = len([a for a in all_agents if a.get("status") == "frozen"])
            if pranas:
                cells.append(digest_economy(
                    total_prana=sum(pranas),
                    avg_prana=sum(pranas) / max(len(pranas), 1),
                    dormant_count=dormant_count,
                    agent_count=len(all_agents),
                    min_prana=min(pranas),
                    max_prana=max(pranas),
                ))
    except Exception:
        pass

    # Thread state digests
    try:
        thread_state = ctx.thread_state  # type: ignore[union-attr]
        if thread_state is not None:
            for t in thread_state.active_threads():
                cells.append(digest_thread_state(
                    discussion_number=t.discussion_number,
                    status=t.status,
                    energy=t.energy,
                    human_count=t.human_comment_count,
                    response_count=t.response_count,
                    unresolved=t.unresolved,
                    last_human_author=getattr(t, "last_human_author", ""),
                ))
    except Exception:
        pass

    # TODO: 10E — digest agent outputs from recent discussion responses
    # TODO: 10E — digest mission results from Sankalpa

    field_str = render_field_summary(cells)

    # 10D: Append TODO scan to field summary
    try:
        from city.todo_scanner import render_todo_digest, scan_todos
        from pathlib import Path
        city_root = Path(__file__).parent.parent
        todos = scan_todos(city_root)
        if todos:
            field_str += "\n\n" + render_todo_digest(todos)
    except Exception:
        pass

    return field_str


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

    # 6C-4: Agent roster (top 20 by name, minimal fields)
    agent_roster: list[dict] = []
    try:
        pokedex = ctx.pokedex  # type: ignore[union-attr]
        if pokedex is not None:
            citizens = pokedex.list_citizens()
            for a in citizens[:20]:
                agent_roster.append({
                    "name": a.get("name", ""),
                    "domain": a.get("domain", ""),
                    "status": a.get("status", ""),
                    "prana": a.get("prana", 0),
                    "zone": a.get("zone", ""),
                })
    except Exception:
        pass

    # 6C-4: Economy aggregate stats
    economy_stats: dict = {}
    try:
        pokedex = ctx.pokedex  # type: ignore[union-attr]
        if pokedex is not None:
            all_agents = pokedex.list_all()
            pranas = [a.get("prana", 0) for a in all_agents if a.get("prana") is not None]
            dormant_count = len([a for a in all_agents if a.get("status") == "frozen"])
            economy_stats = {
                "total_prana": sum(pranas),
                "avg_prana": round(sum(pranas) / max(len(pranas), 1), 1),
                "min_prana": min(pranas) if pranas else 0,
                "max_prana": max(pranas) if pranas else 0,
                "dormant_count": dormant_count,
            }
    except Exception:
        pass

    # 6C-4: Discussion activity from DiscussionsBridge
    discussion_activity: dict = {}
    try:
        discussions = ctx.discussions  # type: ignore[union-attr]
        if discussions is not None:
            discussion_activity = discussions.stats()
    except Exception:
        pass

    # 6C-4: Active missions from Sankalpa
    active_missions_data: list[dict] = []
    try:
        sankalpa = ctx.sankalpa  # type: ignore[union-attr]
        if sankalpa is not None and hasattr(sankalpa, "registry"):
            missions = sankalpa.registry.get_active_missions()
            for m in missions[:10]:
                active_missions_data.append({
                    "id": getattr(m, "id", ""),
                    "name": getattr(m, "name", ""),
                    "status": m.status.value if hasattr(m.status, "value") else str(getattr(m, "status", "")),
                    "owner": getattr(m, "owner", "unknown"),
                })
    except Exception:
        pass

    # 6C-4: Thread state (comment ledger stats)
    thread_stats: dict = {}
    try:
        thread_state = ctx.thread_state  # type: ignore[union-attr]
        if thread_state is not None:
            thread_stats = thread_state.comment_stats()
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
        agent_roster=tuple(agent_roster),
        economy_stats=economy_stats,
        discussion_activity=discussion_activity,
        active_missions=tuple(active_missions_data),
        thread_stats=thread_stats,
    )
