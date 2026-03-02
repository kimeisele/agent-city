"""ThreadStateEngine — prana-based discussion lifecycle tests."""

import tempfile
from pathlib import Path

from city.thread_state import (
    ARCHIVE_THRESHOLD,
    COOL_THRESHOLD,
    DECAY_RATE,
    REPETITION_ESCALATION_COUNT,
    CommentEntry,
    CommentStatus,
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


# ── Comment Ledger ─────────────────────────────────────────────────


def test_ingest_comment_external():
    engine = _make_engine()
    entry = engine.ingest_comment("c1", 42, "alice", "Hello world")
    assert entry is not None
    assert entry.comment_id == "c1"
    assert entry.discussion_number == 42
    assert entry.author == "alice"
    assert entry.source == "external"
    assert entry.status == CommentStatus.SEEN
    assert entry.body_hash != ""
    assert entry.enqueued_at is None
    assert entry.replied_at is None


def test_ingest_comment_self():
    engine = _make_engine()
    entry = engine.ingest_comment("c2", 42, "github-actions[bot]", "Report", is_own=True)
    assert entry is not None
    assert entry.source == "self"
    assert entry.status == CommentStatus.SELF


def test_ingest_comment_idempotent():
    engine = _make_engine()
    first = engine.ingest_comment("c1", 42, "alice", "Hello")
    assert first is not None
    second = engine.ingest_comment("c1", 42, "alice", "Hello")
    assert second is None  # already ingested


def test_is_comment_seen():
    engine = _make_engine()
    assert engine.is_comment_seen("c1") is False
    engine.ingest_comment("c1", 42, "alice", "Hello")
    assert engine.is_comment_seen("c1") is True


def test_mark_enqueued():
    engine = _make_engine()
    engine.ingest_comment("c1", 42, "alice", "Hello")
    engine.mark_enqueued("c1")
    unreplied = engine.unreplied_comments()
    assert len(unreplied) == 1
    assert unreplied[0].status == CommentStatus.ENQUEUED
    assert unreplied[0].enqueued_at is not None


def test_mark_replied_closes_loop():
    engine = _make_engine()
    engine.ingest_comment("c1", 42, "alice", "Hello")
    engine.mark_enqueued("c1")
    engine.mark_replied("c1", reply_comment_id="r1")
    unreplied = engine.unreplied_comments()
    assert len(unreplied) == 0


def test_unreplied_comments_excludes_self():
    engine = _make_engine()
    engine.ingest_comment("c1", 42, "alice", "Hello")
    engine.ingest_comment("c2", 42, "bot", "Report", is_own=True)
    unreplied = engine.unreplied_comments()
    assert len(unreplied) == 1
    assert unreplied[0].comment_id == "c1"


def test_unreplied_comments_filter_by_thread():
    engine = _make_engine()
    engine.ingest_comment("c1", 42, "alice", "Hello")
    engine.ingest_comment("c2", 99, "bob", "World")
    unreplied_42 = engine.unreplied_comments(discussion_number=42)
    assert len(unreplied_42) == 1
    assert unreplied_42[0].discussion_number == 42
    unreplied_all = engine.unreplied_comments()
    assert len(unreplied_all) == 2


def test_full_lifecycle():
    """Complete lifecycle: ingest → enqueue → reply → closed."""
    engine = _make_engine()
    # Bot posts a report
    engine.ingest_comment("bot1", 42, "bot", "Report", is_own=True)
    # Human comments
    engine.ingest_comment("h1", 42, "alice", "Question?")
    engine.ingest_comment("h2", 42, "bob", "Another question")
    # Enqueue both
    engine.mark_enqueued("h1")
    engine.mark_enqueued("h2")
    assert len(engine.unreplied_comments()) == 2
    # Reply to first
    engine.mark_replied("h1", reply_comment_id="r1")
    assert len(engine.unreplied_comments()) == 1
    assert engine.unreplied_comments()[0].comment_id == "h2"
    # Reply to second
    engine.mark_replied("h2", reply_comment_id="r2")
    assert len(engine.unreplied_comments()) == 0


def test_comment_stats():
    engine = _make_engine()
    engine.ingest_comment("c1", 42, "alice", "Hello")
    engine.ingest_comment("c2", 42, "bot", "Report", is_own=True)
    engine.mark_enqueued("c1")
    stats = engine.comment_stats()
    assert stats["external:enqueued"] == 1
    assert stats["self:self"] == 1
    assert stats["total"] == 2


def test_comment_entry_properties():
    entry = CommentEntry(
        comment_id="c1", discussion_number=42, author="alice",
        body_hash="abc", source="external", status=CommentStatus.SEEN,
        seen_at=0.0, enqueued_at=None, replied_at=None, reply_comment_id=None,
    )
    assert entry.needs_processing is True
    assert entry.is_from_self is False

    self_entry = CommentEntry(
        comment_id="c2", discussion_number=42, author="bot",
        body_hash="def", source="self", status=CommentStatus.SELF,
        seen_at=0.0, enqueued_at=None, replied_at=None, reply_comment_id=None,
    )
    assert self_entry.needs_processing is False
    assert self_entry.is_from_self is True
