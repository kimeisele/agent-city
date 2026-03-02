"""BrainCell + BrainMemory v2 Tests — MahaCellUnified wrapping, TTL decay, prana cost."""

import tempfile
from pathlib import Path
from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

from city.brain import Thought, BrainIntent, ThoughtKind
from city.brain_cell import (
    BRAIN_CALL_COST,
    BRAIN_CELL_TTL,
    BRAIN_HEALTH_COST,
    BrainCellPayload,
    create_brain_cell,
    create_brain_cell_from_dict,
    get_cell_prana_cost,
    is_cell_alive,
)
from city.brain_memory import BrainMemory


# ── BrainCell Creation ───────────────────────────────────────────────


def test_create_brain_cell_returns_maha_cell():
    """create_brain_cell wraps a Thought in MahaCellUnified."""
    thought = Thought(
        comprehension="test",
        intent=BrainIntent.OBSERVE,
        confidence=0.8,
        kind=ThoughtKind.COMPREHENSION,
    )
    cell = create_brain_cell(thought, heartbeat=10)
    assert isinstance(cell, MahaCellUnified)
    assert cell.payload is not None
    assert isinstance(cell.payload, BrainCellPayload)
    assert cell.payload.heartbeat == 10
    assert cell.payload.kind == "comprehension"
    assert cell.payload.source == "internal"


def test_brain_cell_health_check_cost():
    """Health check cells cost BRAIN_HEALTH_COST (TRINITY=3)."""
    thought = Thought(kind=ThoughtKind.HEALTH_CHECK)
    cell = create_brain_cell(thought, heartbeat=1, kind=ThoughtKind.HEALTH_CHECK)
    assert get_cell_prana_cost(cell) == BRAIN_HEALTH_COST
    assert BRAIN_HEALTH_COST == 3


def test_brain_cell_comprehension_cost():
    """Non-health cells cost BRAIN_CALL_COST (NAVA=9)."""
    thought = Thought(kind=ThoughtKind.COMPREHENSION)
    cell = create_brain_cell(thought, heartbeat=1)
    assert get_cell_prana_cost(cell) == BRAIN_CALL_COST
    assert BRAIN_CALL_COST == 9


def test_brain_cell_reflection_cost():
    """Reflection cells cost BRAIN_CALL_COST (NAVA=9)."""
    thought = Thought(kind=ThoughtKind.REFLECTION)
    cell = create_brain_cell(thought, heartbeat=1, kind=ThoughtKind.REFLECTION)
    assert get_cell_prana_cost(cell) == BRAIN_CALL_COST


def test_brain_cell_payload_roundtrip():
    """BrainCellPayload serializes and deserializes correctly."""
    payload = BrainCellPayload(
        thought={"intent": "observe", "confidence": 0.9},
        heartbeat=42,
        kind="health_check",
        posted=True,
        source="internal",
    )
    d = payload.to_dict()
    restored = BrainCellPayload.from_dict(d)
    assert restored.thought == payload.thought
    assert restored.heartbeat == 42
    assert restored.kind == "health_check"
    assert restored.posted is True
    assert restored.source == "internal"


def test_create_brain_cell_from_dict():
    """create_brain_cell_from_dict creates cells from raw dicts (external)."""
    cell = create_brain_cell_from_dict(
        {"intent": "observe"}, heartbeat=5, source="external",
    )
    assert isinstance(cell, MahaCellUnified)
    assert cell.payload.source == "external"
    assert get_cell_prana_cost(cell) == 0  # external = free


# ── Cell Lifecycle (TTL) ─────────────────────────────────────────────


def test_cell_alive_within_ttl():
    """Cell is alive within its TTL window."""
    thought = Thought()
    cell = create_brain_cell(thought, heartbeat=10)
    assert is_cell_alive(cell, current_heartbeat=10) is True
    assert is_cell_alive(cell, current_heartbeat=10 + BRAIN_CELL_TTL - 1) is True


def test_cell_dead_after_ttl():
    """Cell is dead after TTL expires."""
    thought = Thought()
    cell = create_brain_cell(thought, heartbeat=10)
    assert is_cell_alive(cell, current_heartbeat=10 + BRAIN_CELL_TTL) is False
    assert is_cell_alive(cell, current_heartbeat=10 + BRAIN_CELL_TTL + 100) is False


def test_cell_ttl_is_nava_times_trinity():
    """BRAIN_CELL_TTL = NAVA × TRINITY = 27."""
    assert BRAIN_CELL_TTL == 27


# ── BrainMemory v2 ──────────────────────────────────────────────────


def test_memory_record_returns_prana_cost():
    """BrainMemory.record() returns the prana cost of the cell."""
    mem = BrainMemory(max_entries=10)
    thought = Thought(kind=ThoughtKind.HEALTH_CHECK)
    cost = mem.record(thought, heartbeat=1)
    assert cost == BRAIN_HEALTH_COST


def test_memory_record_tracks_total_prana():
    """total_prana_spent accumulates across records."""
    mem = BrainMemory(max_entries=10)
    t1 = Thought(kind=ThoughtKind.HEALTH_CHECK)
    t2 = Thought(kind=ThoughtKind.COMPREHENSION)
    mem.record(t1, heartbeat=1)
    mem.record(t2, heartbeat=2)
    assert mem.total_prana_spent == BRAIN_HEALTH_COST + BRAIN_CALL_COST


def test_memory_cell_count():
    """cell_count tracks number of live cells."""
    mem = BrainMemory(max_entries=10)
    assert mem.cell_count == 0
    mem.record(Thought(), heartbeat=1)
    assert mem.cell_count == 1
    mem.record(Thought(), heartbeat=2)
    assert mem.cell_count == 2


def test_memory_decay_reaps_old_cells():
    """decay() removes cells past their TTL."""
    mem = BrainMemory(max_entries=10)
    mem.record(Thought(), heartbeat=1)
    mem.record(Thought(), heartbeat=2)
    mem.record(Thought(), heartbeat=50)  # young cell

    # At heartbeat 50, cells from hb=1 and hb=2 are > 27 beats old
    reaped = mem.decay(current_heartbeat=50)
    assert reaped == 2
    assert mem.cell_count == 1
    assert len(mem.recent()) == 1


def test_memory_decay_keeps_young_cells():
    """decay() keeps cells within TTL."""
    mem = BrainMemory(max_entries=10)
    mem.record(Thought(), heartbeat=10)
    mem.record(Thought(), heartbeat=11)

    reaped = mem.decay(current_heartbeat=15)
    assert reaped == 0
    assert mem.cell_count == 2


def test_memory_backward_compat_recent():
    """recent() returns dict entries, same format as old BrainMemory."""
    mem = BrainMemory(max_entries=10)
    thought = Thought(
        comprehension="test thought",
        intent=BrainIntent.OBSERVE,
        confidence=0.75,
    )
    mem.record(thought, heartbeat=42)
    entries = mem.recent(1)
    assert len(entries) == 1
    assert entries[0]["heartbeat"] == 42
    assert entries[0]["thought"]["comprehension"] == "test thought"
    assert entries[0]["thought"]["confidence"] == 0.75


def test_memory_backward_compat_pattern_summary():
    """pattern_summary() returns the same format as before."""
    mem = BrainMemory(max_entries=10)
    mem.record(Thought(confidence=0.9), heartbeat=1)
    mem.record(Thought(confidence=0.3), heartbeat=2)
    summary = mem.pattern_summary()
    assert "1/2" in summary  # 1 high confidence out of 2
    assert "0.60" in summary  # avg of 0.9 and 0.3


def test_memory_backward_compat_record_external():
    """record_external() works with cell population."""
    mem = BrainMemory(max_entries=10)
    mem.record_external({
        "intent": "observe",
        "confidence": 0.5,
        "heartbeat": 7,
    })
    assert mem.cell_count == 1
    entries = mem.recent(1)
    assert entries[0]["source"] == "external"
    assert entries[0]["posted"] is True
    # External thoughts cost 0 prana
    assert mem.total_prana_spent == 0


def test_memory_fifo_eviction_syncs_cells_and_entries():
    """FIFO eviction removes both cells and entries in sync."""
    mem = BrainMemory(max_entries=3)
    for i in range(5):
        mem.record(Thought(), heartbeat=i)
    assert mem.cell_count == 3
    assert len(mem.recent(10)) == 3
    # Oldest entries should be heartbeats 2, 3, 4
    entries = mem.recent(10)
    assert entries[0]["heartbeat"] == 2


def test_memory_flush_and_load_roundtrip():
    """flush() + load() preserves entries and recreates cells."""
    tmp = Path(tempfile.mkdtemp())
    path = tmp / "brain_memory.json"

    mem = BrainMemory(path=path, max_entries=10)
    mem.record(Thought(confidence=0.8, kind=ThoughtKind.HEALTH_CHECK), heartbeat=5)
    mem.record(Thought(confidence=0.6), heartbeat=6)
    mem.flush()

    # Reload into fresh instance
    mem2 = BrainMemory(path=path, max_entries=10)
    mem2.load()
    assert len(mem2.recent(10)) == 2
    assert mem2.cell_count == 2
    assert mem2.recent(10)[0]["heartbeat"] == 5
    assert mem2.recent(10)[1]["heartbeat"] == 6


def test_memory_load_empty_file():
    """load() with no file starts empty."""
    tmp = Path(tempfile.mkdtemp())
    mem = BrainMemory(path=tmp / "nonexistent.json")
    mem.load()
    assert mem.cell_count == 0
    assert len(mem.recent()) == 0
