"""Community Triage — thread prioritization and moderation tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from city.community_triage import (
    TriageAction,
    TriageItem,
    triage_threads,
)
from city.thread_state import ThreadStateEngine


def _make_engine() -> ThreadStateEngine:
    tmp = Path(tempfile.mkdtemp()) / "test_city.db"
    return ThreadStateEngine(db_path=str(tmp))


def _mock_pokedex():
    pokedex = MagicMock()
    pokedex.list_by_zone.return_value = [
        {"name": "eng_agent", "status": "citizen"},
    ]
    return pokedex


# ── Basic Triage ───────────────────────────────────────────────────


def test_triage_empty_returns_nothing():
    engine = _make_engine()
    items = triage_threads(engine, _mock_pokedex())
    assert items == []


def test_triage_unresolved_thread():
    engine = _make_engine()
    engine.record_human_comment(42, "alice", title="Bug in CI")

    items = triage_threads(engine, _mock_pokedex())
    assert len(items) == 1
    assert items[0].action == TriageAction.RESPOND
    assert items[0].discussion_number == 42
    assert items[0].reason == "Unresolved human comment"


def test_triage_resolved_thread_excluded():
    engine = _make_engine()
    engine.record_human_comment(42, "alice", title="Bug")
    engine.record_agent_response(42)

    items = triage_threads(engine, _mock_pokedex())
    assert len(items) == 0


def test_triage_escalation_highest_priority():
    engine = _make_engine()
    # Repetition: same user posts 3x without response
    engine.record_human_comment(42, "alice", title="Please fix this")
    engine.record_human_comment(42, "alice")
    engine.record_human_comment(42, "alice")
    # Normal unresolved thread
    engine.record_human_comment(99, "bob", title="New idea")

    items = triage_threads(engine, _mock_pokedex())
    assert len(items) >= 2
    # Stuck thread gets RESPOND (retry with MicroBrain) instead of ESCALATE (give up)
    assert items[0].action == TriageAction.RESPOND
    assert items[0].discussion_number == 42
    assert "MicroBrain" in items[0].reason or "Retry" in items[0].reason


def test_triage_respects_max_actions():
    engine = _make_engine()
    for i in range(10):
        engine.record_human_comment(100 + i, f"user{i}", title=f"Thread {i}")

    items = triage_threads(engine, _mock_pokedex(), max_actions=3)
    assert len(items) == 3


def test_triage_skips_seed_threads():
    engine = _make_engine()
    engine.record_human_comment(26, "alice", title="City Ideas & Proposals")
    engine.record_human_comment(99, "bob", title="Real question")

    seed_threads = {"ideas": 26}
    items = triage_threads(engine, _mock_pokedex(), seed_threads=seed_threads)
    assert len(items) == 1
    assert items[0].discussion_number == 99


def test_triage_agent_matching_by_title():
    engine = _make_engine()
    engine.record_human_comment(42, "alice", title="Bug in code build system")

    pokedex = MagicMock()
    pokedex.list_by_zone.return_value = [
        {"name": "builder_bot", "status": "citizen"},
    ]

    items = triage_threads(engine, pokedex)
    assert len(items) == 1
    assert items[0].suggested_agent == "builder_bot"


def test_triage_falls_back_to_mayor():
    engine = _make_engine()
    engine.record_human_comment(42, "alice", title="Random topic")

    pokedex = MagicMock()
    pokedex.list_by_zone.return_value = []

    items = triage_threads(engine, pokedex)
    assert len(items) == 1
    assert items[0].suggested_agent == "mayor"


# ── Priority Ordering ──────────────────────────────────────────────


def test_triage_higher_energy_threads_first():
    engine = _make_engine()
    engine.record_human_comment(10, "alice", title="Old thread")
    # Decay thread 10 to lower energy
    for _ in range(5):
        engine.decay_all()
    engine.record_human_comment(20, "bob", title="Fresh thread")

    items = triage_threads(engine, _mock_pokedex())
    assert len(items) == 2
    # Fresh thread (energy=1.0) should come before decayed thread
    assert items[0].discussion_number == 20
    assert items[1].discussion_number == 10
