"""
Tests for BrainMemory — persistent bounded FIFO.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from city.brain_memory import BrainMemory


def _make_thought(comprehension: str = "test", confidence: float = 0.5) -> MagicMock:
    t = MagicMock()
    t.to_dict.return_value = {
        "comprehension": comprehension,
        "confidence": confidence,
        "intent": "observe",
        "kind": "comprehension",
    }
    return t


class TestBrainMemory:
    def test_record_and_recent(self):
        mem = BrainMemory(max_entries=24)
        t1 = _make_thought("first", 0.3)
        t2 = _make_thought("second", 0.8)
        mem.record(t1, heartbeat=1)
        mem.record(t2, heartbeat=2)
        recent = mem.recent(6)
        assert len(recent) == 2
        assert recent[0]["heartbeat"] == 1
        assert recent[1]["heartbeat"] == 2
        assert recent[1]["thought"]["confidence"] == 0.8

    def test_eviction(self):
        mem = BrainMemory(max_entries=3)
        for i in range(5):
            mem.record(_make_thought(f"t{i}"), heartbeat=i)
        recent = mem.recent(10)
        assert len(recent) == 3
        # Oldest (0, 1) evicted, remaining are 2, 3, 4
        assert recent[0]["heartbeat"] == 2
        assert recent[2]["heartbeat"] == 4

    def test_flush_load_roundtrip(self, tmp_path: Path):
        path = tmp_path / "brain_memory.json"
        mem = BrainMemory(path=path, max_entries=24)
        mem.record(_make_thought("persisted", 0.9), heartbeat=42)
        mem.flush()
        assert path.exists()

        mem2 = BrainMemory(path=path, max_entries=24)
        mem2.load()
        recent = mem2.recent(6)
        assert len(recent) == 1
        assert recent[0]["heartbeat"] == 42
        assert recent[0]["thought"]["comprehension"] == "persisted"

    def test_pattern_summary(self):
        mem = BrainMemory(max_entries=24)
        mem.record(_make_thought("a", 0.9), heartbeat=1)
        mem.record(_make_thought("b", 0.8), heartbeat=2)
        mem.record(_make_thought("c", 0.3), heartbeat=3)
        summary = mem.pattern_summary()
        assert "2/3" in summary  # 2 of 3 high confidence
        assert "0.67" in summary  # avg

    def test_empty_memory(self):
        mem = BrainMemory(max_entries=24)
        assert mem.recent() == []
        assert "No brain" in mem.pattern_summary()

    def test_load_missing_file(self, tmp_path: Path):
        path = tmp_path / "does_not_exist.json"
        mem = BrainMemory(path=path)
        mem.load()  # Should not raise
        assert mem.recent() == []

    def test_posted_flag(self):
        mem = BrainMemory(max_entries=24)
        mem.record(_make_thought(), heartbeat=1, posted=True)
        entry = mem.recent(1)[0]
        assert entry["posted"] is True


# ── External Feedback Tests (Phase 5) ────────────────────────────────


class TestRecordExternal:
    def test_record_external_basic(self):
        mem = BrainMemory(max_entries=24)
        feedback = {
            "comprehension": "System stable",
            "intent": "observe",
            "confidence": 0.8,
            "heartbeat": 5,
        }
        mem.record_external(feedback)
        recent = mem.recent(1)
        assert len(recent) == 1
        assert recent[0]["source"] == "external"
        assert recent[0]["heartbeat"] == 5
        assert recent[0]["posted"] is True

    def test_record_external_eviction(self):
        mem = BrainMemory(max_entries=2)
        mem.record_external({"heartbeat": 1})
        mem.record_external({"heartbeat": 2})
        mem.record_external({"heartbeat": 3})
        recent = mem.recent(10)
        assert len(recent) == 2
        assert recent[0]["heartbeat"] == 2

    def test_mixed_internal_external(self):
        mem = BrainMemory(max_entries=24)
        mem.record(_make_thought("internal"), heartbeat=1)
        mem.record_external({"comprehension": "external", "heartbeat": 2})
        recent = mem.recent(10)
        assert len(recent) == 2
        assert "source" not in recent[0]  # internal has no source
        assert recent[1]["source"] == "external"
