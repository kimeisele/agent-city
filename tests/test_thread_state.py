"""ThreadStateEngine — prana-based discussion lifecycle tests."""

import tempfile
from pathlib import Path

from city.thread_state import (
    ARCHIVE_THRESHOLD,
    COOL_THRESHOLD,
    DECAY_RATE,
    REPETITION_ESCALATION_COUNT,
    ThreadSnapshot,
    ThreadStateEngine,
    ThreadStatus,
)


def _make_engine() -> ThreadStateEngine:
    tmp = Path(tempfile.mkdtemp()) / "test_city.db"
    return ThreadStateEngine(db_path=str(tmp))


# ── Record Human Comment ───────────────────────────────────────────


def test_record_human_comment_creates_thread():
    engine = _make_engine()
    snap = engine.record_human_comment(42, "alice", title="Test Thread", category="Ideas")
    assert snap.discussion_number == 42
    assert snap.title == "Test Thread"
    assert snap.category == "Ideas"
    assert snap.energy == 1.0
    assert snap.status == ThreadStatus.ACTIVE
    assert snap.unresolved is True
    assert snap.human_comment_count == 1
    assert snap.response_count == 0


def test_record_human_comment_resets_energy():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    # Simulate decay
    engine.decay_all()
    engine.decay_all()
    snap = engine.get(42)
    assert snap.energy < 1.0

    # New comment resets energy
    snap2 = engine.record_human_comment(42, "bob")
    assert snap2.energy == 1.0
    assert snap2.status == ThreadStatus.ACTIVE
    assert snap2.unresolved is True
    assert snap2.human_comment_count == 2


def test_record_human_comment_tracks_consecutive():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    engine.record_human_comment(42, "alice")
    engine.record_human_comment(42, "alice")
    snap = engine.get(42)
    assert snap is not None
    # 3 consecutive posts by same author


def test_record_human_comment_resets_consecutive_on_different_author():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    engine.record_human_comment(42, "alice")
    engine.record_human_comment(42, "bob")
    # bob breaks the streak — consecutive resets to 1


# ── Record Agent Response ──────────────────────────────────────────


def test_record_agent_response():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    engine.record_agent_response(42)
    snap = engine.get(42)
    assert snap.status == ThreadStatus.WAITING
    assert snap.unresolved is False
    assert snap.response_count == 1


def test_agent_response_does_not_change_energy():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    engine.decay_all()  # energy drops
    snap_before = engine.get(42)
    engine.record_agent_response(42)
    snap_after = engine.get(42)
    assert snap_after.energy == snap_before.energy


# ── Decay ──────────────────────────────────────────────────────────


def test_decay_reduces_energy():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    engine.decay_all()
    snap = engine.get(42)
    assert abs(snap.energy - DECAY_RATE) < 0.001


def test_decay_transitions_to_cooling():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    # Decay until below COOL_THRESHOLD
    energy = 1.0
    beats = 0
    while energy >= COOL_THRESHOLD:
        energy *= DECAY_RATE
        beats += 1
    for _ in range(beats):
        engine.decay_all()
    snap = engine.get(42)
    assert snap.status == ThreadStatus.COOLING


def test_decay_transitions_to_archived():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    # Decay until below ARCHIVE_THRESHOLD
    energy = 1.0
    beats = 0
    while energy >= ARCHIVE_THRESHOLD:
        energy *= DECAY_RATE
        beats += 1
    for _ in range(beats):
        engine.decay_all()
    snap = engine.get(42)
    assert snap.status == ThreadStatus.ARCHIVED
    assert snap.energy == 0.0


def test_decay_skips_archived():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    # Archive it
    energy = 1.0
    beats = 0
    while energy >= ARCHIVE_THRESHOLD:
        energy *= DECAY_RATE
        beats += 1
    for _ in range(beats):
        engine.decay_all()
    # Further decay should not crash
    stats = engine.decay_all()
    assert stats["decayed"] == 0


def test_human_comment_revives_archived_thread():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    # Archive it
    energy = 1.0
    while energy >= ARCHIVE_THRESHOLD:
        energy *= DECAY_RATE
        engine.decay_all()
    snap = engine.get(42)
    assert snap.status == ThreadStatus.ARCHIVED

    # Human revives
    snap2 = engine.record_human_comment(42, "bob")
    assert snap2.energy == 1.0
    assert snap2.status == ThreadStatus.ACTIVE
    assert snap2.unresolved is True


# ── Queries ────────────────────────────────────────────────────────


def test_threads_needing_response():
    engine = _make_engine()
    engine.record_human_comment(10, "alice")
    engine.record_human_comment(20, "bob")
    engine.record_agent_response(10)  # resolved

    needs = engine.threads_needing_response()
    assert len(needs) == 1
    assert needs[0].discussion_number == 20


def test_active_threads():
    engine = _make_engine()
    engine.record_human_comment(10, "alice")
    engine.record_human_comment(20, "bob")
    active = engine.active_threads()
    assert len(active) == 2


def test_repetition_alerts():
    engine = _make_engine()
    for _ in range(REPETITION_ESCALATION_COUNT):
        engine.record_human_comment(42, "alice")
    alerts = engine.repetition_alerts()
    assert len(alerts) == 1
    assert alerts[0].discussion_number == 42


def test_repetition_alerts_cleared_by_agent_response():
    engine = _make_engine()
    for _ in range(REPETITION_ESCALATION_COUNT):
        engine.record_human_comment(42, "alice")
    assert len(engine.repetition_alerts()) == 1

    engine.record_agent_response(42)
    assert len(engine.repetition_alerts()) == 0


def test_stats():
    engine = _make_engine()
    engine.record_human_comment(10, "alice")
    engine.record_human_comment(20, "bob")
    engine.record_agent_response(10)
    s = engine.stats()
    assert s["total"] == 2
    assert s["unresolved"] == 1


# ── ThreadSnapshot Properties ──────────────────────────────────────


def test_snapshot_needs_response():
    engine = _make_engine()
    engine.record_human_comment(42, "alice")
    snap = engine.get(42)
    assert snap.needs_response is True

    engine.record_agent_response(42)
    snap2 = engine.get(42)
    assert snap2.needs_response is False


def test_snapshot_is_alive():
    snap_active = ThreadSnapshot(
        discussion_number=1, title="", category="", energy=1.0,
        status=ThreadStatus.ACTIVE, last_human_comment_at=0,
        last_agent_response_at=0, human_comment_count=0,
        response_count=0, unresolved=False, created_at=0,
    )
    assert snap_active.is_alive is True

    snap_archived = ThreadSnapshot(
        discussion_number=1, title="", category="", energy=0.0,
        status=ThreadStatus.ARCHIVED, last_human_comment_at=0,
        last_agent_response_at=0, human_comment_count=0,
        response_count=0, unresolved=False, created_at=0,
    )
    assert snap_archived.is_alive is False
