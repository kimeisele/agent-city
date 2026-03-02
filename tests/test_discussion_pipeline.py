"""Discussion Pipeline Integration Tests — full inbound→think→respond→ledger loop.

Phase 6B-5: Tests the complete discussion pipeline end-to-end with
mocked external services (GitHub API, LLM) but real internal wiring.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from city.discussions_commands import (
    ConversationTracker,
    DiscussionCommand,
    execute_command,
    parse_commands,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def tmp():
    d = Path(tempfile.mkdtemp(prefix="disc_pipeline_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def pokedex(tmp):
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp / "economy.db"))
    return Pokedex(db_path=str(tmp / "city.db"), bank=bank)


@pytest.fixture
def thread_state(tmp):
    from city.thread_state import ThreadStateEngine

    return ThreadStateEngine(db_path=str(tmp / "threads.db"))


@pytest.fixture
def brain_memory(tmp):
    from city.brain_memory import BrainMemory

    return BrainMemory(path=tmp / "brain_memory.json")


@pytest.fixture
def conversation_tracker():
    return ConversationTracker()


@pytest.fixture
def mock_discussions():
    """Mock DiscussionsBridge — records posts instead of calling GitHub API."""
    disc = MagicMock()
    disc.can_respond.return_value = True
    disc.comment.return_value = True
    disc.record_response = MagicMock()
    disc._seed_threads = {}
    return disc


@pytest.fixture
def mock_ctx(tmp, pokedex, thread_state, brain_memory, conversation_tracker, mock_discussions):
    """Build a mock PhaseContext with real Pokedex + ThreadState + BrainMemory."""
    from city.registry import (
        SVC_BRAIN_MEMORY,
        SVC_CONVERSATION_TRACKER,
        SVC_DISCUSSIONS,
        SVC_THREAD_STATE,
        CityServiceRegistry,
    )

    registry = CityServiceRegistry()
    registry.register(SVC_THREAD_STATE, thread_state)
    registry.register(SVC_BRAIN_MEMORY, brain_memory)
    registry.register(SVC_DISCUSSIONS, mock_discussions)
    registry.register(SVC_CONVERSATION_TRACKER, conversation_tracker)

    ctx = MagicMock()
    ctx.pokedex = pokedex
    ctx.heartbeat_count = 10
    ctx.offline_mode = False
    ctx.state_path = tmp / "mayor_state.json"
    ctx.active_agents = set()
    ctx.gateway_queue = []
    ctx.registry = registry

    # Wire properties to use real registry
    type(ctx).discussions = property(lambda self: self.registry.get(SVC_DISCUSSIONS))
    type(ctx).thread_state = property(lambda self: self.registry.get(SVC_THREAD_STATE))
    type(ctx).brain_memory = property(lambda self: self.registry.get(SVC_BRAIN_MEMORY))
    type(ctx).conversation_tracker = property(
        lambda self: self.registry.get(SVC_CONVERSATION_TRACKER)
    )
    ctx.brain = None
    ctx.sankalpa = None
    ctx.council = None
    ctx.contracts = None
    ctx.learning = None
    ctx.agent_nadi = None
    return ctx


# ── Command Pipeline Tests ──────────────────────────────────────────


def test_command_pipeline_status(mock_ctx, mock_discussions):
    """Full pipeline: /status comment → parse → execute → post → ledger."""
    comment_body = "/status"
    comment_id = "test_comment_abc"

    # 1. Parse commands
    commands = parse_commands(
        comment_body, author="alice", discussion_number=42, comment_id=comment_id,
    )
    assert len(commands) == 1
    assert commands[0].command == "status"

    # 2. Ingest comment into ledger
    mock_ctx.thread_state.ingest_comment(
        comment_id=comment_id,
        discussion_number=42,
        author="alice",
        body=comment_body,
    )

    # 3. Execute command
    response = execute_command(commands[0], mock_ctx)
    assert response is not None
    assert "City Status" in response
    assert "Heartbeat #10" in response

    # 4. Post response
    mock_discussions.comment(42, response)
    mock_discussions.comment.assert_called()

    # 5. Mark replied in ledger
    mock_ctx.thread_state.mark_replied(comment_id)
    # After reply, comment should no longer appear in unreplied list
    unreplied = mock_ctx.thread_state.unreplied_comments(42)
    assert all(c.comment_id != comment_id for c in unreplied)


def test_command_pipeline_help(mock_ctx, mock_discussions):
    """/help → parse → execute → verify response content."""
    commands = parse_commands("/help", author="bob", discussion_number=10)
    assert len(commands) == 1

    response = execute_command(commands[0], mock_ctx)
    assert response is not None
    assert "Available Commands" in response
    assert "`/status`" in response
    assert "`/agents`" in response
    assert "`/mission`" in response


def test_command_pipeline_agents(mock_ctx, mock_discussions):
    """/agents with registered agents → full list returned."""
    mock_ctx.pokedex.register("AgentAlpha")
    mock_ctx.pokedex.register("AgentBeta")

    commands = parse_commands("/agents", author="carol", discussion_number=5)
    response = execute_command(commands[0], mock_ctx)
    assert response is not None
    assert "AgentAlpha" in response
    assert "AgentBeta" in response


def test_command_pipeline_ping_agent(mock_ctx, mock_discussions):
    """/ping existing agent → agent info returned."""
    mock_ctx.pokedex.register("PingTarget")

    commands = parse_commands("/ping PingTarget", author="dave", discussion_number=7)
    response = execute_command(commands[0], mock_ctx)
    assert response is not None
    assert "PingTarget" in response
    assert "Status" in response


def test_command_pipeline_ping_unknown(mock_ctx):
    """/ping unknown agent → not found."""
    commands = parse_commands("/ping GhostAgent", author="eve", discussion_number=8)
    response = execute_command(commands[0], mock_ctx)
    assert response is not None
    assert "not found" in response


# ── Comment Ledger Lifecycle Tests ──────────────────────────────────


def test_comment_ledger_lifecycle(thread_state):
    """Full comment lifecycle: ingest → enqueue → reply."""
    cid = "comment_lifecycle_001"

    # Ingest
    thread_state.ingest_comment(
        comment_id=cid, discussion_number=99, author="alice", body="Hello city!",
    )
    assert thread_state.is_comment_seen(cid)
    # After ingest, should appear as unreplied
    unreplied = thread_state.unreplied_comments(99)
    assert any(c.comment_id == cid for c in unreplied)

    # Enqueue
    thread_state.mark_enqueued(cid)
    unreplied = thread_state.unreplied_comments(99)
    assert any(c.comment_id == cid for c in unreplied)  # still unreplied

    # Reply
    thread_state.mark_replied(cid)
    unreplied = thread_state.unreplied_comments(99)
    assert all(c.comment_id != cid for c in unreplied)  # now resolved


def test_comment_self_post_tracked(thread_state):
    """Self-posts are ingested with source='self' and don't appear in unreplied."""
    cid = "self_post_001"
    thread_state.ingest_comment(
        comment_id=cid, discussion_number=99,
        author="github-actions[bot]", body="[Brain] thinking...",
        is_own=True,
    )
    assert thread_state.is_comment_seen(cid)
    # Self-posts are excluded from unreplied
    unreplied = thread_state.unreplied_comments(99)
    assert all(c.comment_id != cid for c in unreplied)


def test_comment_stats_accuracy(thread_state):
    """comment_stats() accurately reports ledger state."""
    thread_state.ingest_comment("c1", 10, "alice", "hello")
    thread_state.ingest_comment("c2", 10, "bob", "world")
    thread_state.mark_enqueued("c1")
    thread_state.mark_replied("c1")

    stats = thread_state.comment_stats()
    assert stats["total"] == 2
    assert stats.get("external:replied", 0) >= 1


# ── Brain Feedback Ingestion Tests ──────────────────────────────────


def test_brain_feedback_pipeline(mock_ctx, brain_memory):
    """Human comment → extract_brain_feedback → record_external."""
    from city.discussions_commands import extract_brain_feedback

    feedback = extract_brain_feedback(
        "I think we need better error handling in the immune system",
        author="alice",
        discussion_number=42,
        heartbeat=10,
    )
    assert feedback is not None
    assert feedback["intent"] == "external_feedback"

    # Record in brain memory
    brain_memory.record_external(feedback)
    assert brain_memory.cell_count == 1

    recent = brain_memory.recent(1)
    assert len(recent) == 1
    assert recent[0]["source"] == "external"


def test_brain_feedback_skips_bot(brain_memory):
    """Bot comments don't enter brain memory."""
    from city.discussions_commands import extract_brain_feedback

    feedback = extract_brain_feedback(
        "Some automated response",
        author="github-actions[bot]",
    )
    assert feedback is None


# ── ConversationTracker Persistence Tests ───────────────────────────


def test_tracker_persistence_roundtrip(tmp):
    """Tracker survives save → load cycle (simulating GitHub Actions restart)."""
    import json

    # Session 1: create tracker, record state
    tracker1 = ConversationTracker()
    t1 = tracker1.get_or_create(42)
    t1.participants.add("alice")
    cmd = DiscussionCommand(
        command="status", args="", author="alice",
        discussion_number=42, comment_id="c1", raw_line="/status",
    )
    t1.record_command(cmd)
    t1.record_response(heartbeat=10)

    # Save
    tracker_path = tmp / "conversation_tracker.json"
    tracker_path.write_text(json.dumps(tracker1.snapshot(), indent=2))

    # Session 2: new tracker, restore from disk
    tracker2 = ConversationTracker()
    data = json.loads(tracker_path.read_text())
    tracker2.restore(data)

    assert tracker2.active_count == 1
    t2 = tracker2.get(42)
    assert t2 is not None
    assert "alice" in t2.participants
    assert "/status" in t2.command_history
    assert t2.last_agent_response_hb == 10
    assert t2.turn_count == 2  # 1 command + 1 response


def test_tracker_multiple_threads(tmp):
    """Multiple discussion threads tracked independently."""
    import json

    tracker = ConversationTracker()
    t1 = tracker.get_or_create(1)
    t1.participants.add("alice")
    t2 = tracker.get_or_create(2)
    t2.participants.add("bob")
    t3 = tracker.get_or_create(3)
    t3.participants.add("carol")

    # Roundtrip
    path = tmp / "tracker.json"
    path.write_text(json.dumps(tracker.snapshot(), indent=2))
    restored = ConversationTracker()
    restored.restore(json.loads(path.read_text()))

    assert restored.active_count == 3
    assert "alice" in restored.get(1).participants
    assert "bob" in restored.get(2).participants
    assert "carol" in restored.get(3).participants


# ── Multi-Command Tests ─────────────────────────────────────────────


def test_multi_command_in_single_comment(mock_ctx):
    """Multiple commands in one comment are all parsed and executable."""
    body = "/status\nSome text\n/agents\n/help"
    commands = parse_commands(body, author="alice", discussion_number=42)
    assert len(commands) == 3

    for cmd in commands:
        assert cmd.is_valid
        result = execute_command(cmd, mock_ctx)
        assert result is not None


def test_mixed_command_and_prose_feedback(mock_ctx, brain_memory):
    """Comment with commands + prose: commands execute, prose feeds brain."""
    from city.discussions_commands import extract_brain_feedback

    body = "/status\nThe immune system needs better error handling for edge cases"

    # Commands parsed
    commands = parse_commands(body, author="alice", discussion_number=42)
    assert len(commands) == 1
    assert commands[0].command == "status"

    # Prose extracted for brain
    feedback = extract_brain_feedback(body, author="alice", discussion_number=42, heartbeat=10)
    assert feedback is not None
    assert "immune system" in feedback["comprehension"]

    # Both paths work
    response = execute_command(commands[0], mock_ctx)
    assert "City Status" in response

    brain_memory.record_external(feedback)
    assert brain_memory.cell_count == 1


# ── Triage Pipeline Tests ──────────────────────────────────────────


def test_triage_respond_action(mock_ctx, mock_discussions, thread_state):
    """Triage RESPOND action → post to discussion."""
    from city.karma_handlers.triage import TriageHandler, _handle_respond
    from city.community_triage import TriageItem

    item = TriageItem(
        action="respond",
        discussion_number=42,
        title="Test Thread",
        energy=0.8,
        priority=0.8,
        reason="Unresolved human comment",
        suggested_agent="TestAgent",
    )

    operations = []
    result = _handle_respond(mock_ctx, item, operations)
    assert result == 1
    assert any("triage_responded" in op for op in operations)
    mock_discussions.comment.assert_called()


def test_triage_handler_gate(mock_ctx):
    """TriageHandler.should_run() gates on _triage_items."""
    from city.karma_handlers.triage import TriageHandler

    handler = TriageHandler()

    # No triage items → should not run
    mock_ctx._triage_items = []
    assert handler.should_run(mock_ctx) is False

    # With triage items → should run
    mock_ctx._triage_items = [MagicMock()]
    assert handler.should_run(mock_ctx) is True


# ── Action Hint Execution Tests ─────────────────────────────────────


def _make_citizen(mock_ctx, name="CitizenUser"):
    """Register a citizen in mock_ctx.pokedex so authorization passes."""
    mock_ctx.pokedex.register(name)


def test_action_hint_create_mission(mock_ctx):
    """Brain action_hint create_mission: creates Sankalpa mission."""
    from city.karma_handlers.gateway import _execute_action_hint
    from tests.conftest import MockSankalpa

    mock_ctx.sankalpa = MockSankalpa()
    _make_citizen(mock_ctx)

    thought = MagicMock()
    thought.action_hint = "create_mission:Improve test coverage"
    thought.intent = MagicMock()
    thought.intent.value = "propose"

    operations = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", operations,
        comment_author="CitizenUser",
    )
    assert any("brain_hint_mission" in op for op in operations)


def test_action_hint_investigate(mock_ctx):
    """Brain action_hint investigate: creates investigation mission."""
    from city.karma_handlers.gateway import _execute_action_hint
    from tests.conftest import MockSankalpa

    mock_ctx.sankalpa = MockSankalpa()
    _make_citizen(mock_ctx)

    thought = MagicMock()
    thought.action_hint = "investigate:immune system edge cases"
    thought.intent = MagicMock()
    thought.intent.value = "inquiry"

    operations = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", operations,
        comment_author="CitizenUser",
    )
    assert any("brain_hint_investigate" in op for op in operations)


def test_action_hint_unknown_logged(mock_ctx):
    """Unknown action_hint is logged but doesn't crash."""
    from city.karma_handlers.gateway import _execute_action_hint

    _make_citizen(mock_ctx)

    thought = MagicMock()
    thought.action_hint = "unknown_hint:something"

    operations = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", operations,
        comment_author="CitizenUser",
    )
    assert any("brain_hint_unknown" in op for op in operations)


def test_action_hint_empty_noop(mock_ctx):
    """Empty action_hint is a no-op."""
    from city.karma_handlers.gateway import _execute_action_hint

    thought = MagicMock()
    thought.action_hint = ""

    operations = []
    _execute_action_hint(mock_ctx, thought, 42, "TestAgent", operations)
    assert len(operations) == 0


def test_action_hint_denied_for_unknown_user(mock_ctx):
    """6C-8: State-mutating hint denied for non-citizen/non-operator."""
    from city.karma_handlers.gateway import _execute_action_hint

    # Real Pokedex returns None for unknown users — no setup needed

    thought = MagicMock()
    thought.action_hint = "create_mission:hack the system"
    thought.intent = MagicMock()
    thought.intent.value = "propose"

    operations = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", operations,
        comment_author="RandomUser",
    )
    assert any("brain_hint_denied" in op for op in operations)
    assert not any("brain_hint_mission" in op for op in operations)


def test_action_hint_readonly_allowed_for_anyone(mock_ctx):
    """6C-8: Read-only hints pass without authorization."""
    from city.karma_handlers.gateway import _execute_action_hint

    # Real Pokedex returns None for unknown users — no setup needed

    thought = MagicMock()
    thought.action_hint = "run_status"

    operations = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", operations,
        comment_author="AnyoneAtAll",
    )
    assert any("brain_hint_run_status" in op for op in operations)
    assert not any("denied" in op for op in operations)


def test_action_hint_edit_dedup(mock_ctx):
    """6C-9: Same hint for same comment_id is skipped on re-fire."""
    from city.karma_handlers.gateway import _execute_action_hint, _executed_hints
    from tests.conftest import MockSankalpa

    mock_ctx.sankalpa = MockSankalpa()
    _make_citizen(mock_ctx)

    thought = MagicMock()
    thought.action_hint = "create_mission:Build something"
    thought.intent = MagicMock()
    thought.intent.value = "propose"

    # Clear dedup state
    _executed_hints.clear()

    # First fire: should execute
    ops1 = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", ops1,
        comment_author="CitizenUser", comment_id="comment_abc",
    )
    assert any("brain_hint_mission" in op for op in ops1)

    # Second fire with same comment_id + same hint: should dedup
    ops2 = []
    _execute_action_hint(
        mock_ctx, thought, 42, "TestAgent", ops2,
        comment_author="CitizenUser", comment_id="comment_abc",
    )
    assert any("brain_hint_dedup" in op for op in ops2)
    assert not any("brain_hint_mission" in op for op in ops2)

    # Third fire with same comment_id + DIFFERENT hint: should execute (not dedup)
    thought2 = MagicMock()
    thought2.action_hint = "investigate:something else"
    thought2.intent = MagicMock()
    thought2.intent.value = "inquiry"
    ops3 = []
    _execute_action_hint(
        mock_ctx, thought2, 42, "TestAgent", ops3,
        comment_author="CitizenUser", comment_id="comment_abc",
    )
    assert any("brain_hint_investigate" in op for op in ops3)
    assert not any("dedup" in op for op in ops3)


# ── TTL Cleanup Tests (6C-6) ──────────────────────────────────────────


def test_purge_stale_threads(thread_state):
    """6C-6: Archived threads older than TTL are purged."""
    import time

    # Create a thread, archive it, then backdate it
    thread_state.record_human_comment(1, "alice", title="Old Thread")
    # Manually set energy to 0 and status to archived
    thread_state._conn.execute(
        "UPDATE thread_state SET energy = 0.0, status = 'archived', "
        "last_human_comment_at = ?, last_agent_response_at = ? "
        "WHERE discussion_number = 1",
        (time.time() - 800000, time.time() - 800000),
    )
    thread_state._conn.commit()

    # Create a fresh thread (should NOT be purged)
    thread_state.record_human_comment(2, "bob", title="Fresh Thread")

    stats = thread_state.purge_stale(thread_ttl_s=86400)
    assert stats["threads_purged"] == 1
    assert thread_state.get(1) is None  # purged
    assert thread_state.get(2) is not None  # still alive


def test_purge_stale_comments(thread_state):
    """6C-6: Old replied/self comments are purged from ledger."""
    import time

    # Ingest + reply to a comment, then backdate it
    thread_state.ingest_comment("c1", 1, "alice", "old msg", is_own=False)
    thread_state.mark_replied("c1")
    thread_state._conn.execute(
        "UPDATE comment_ledger SET seen_at = ? WHERE comment_id = 'c1'",
        (time.time() - 400000,),
    )
    thread_state._conn.commit()

    # Fresh unreplied comment (should NOT be purged)
    thread_state.ingest_comment("c2", 1, "bob", "new msg", is_own=False)

    stats = thread_state.purge_stale(comment_ttl_s=86400)
    assert stats["comments_purged"] == 1
    assert not thread_state.is_comment_seen("c1")  # purged
    assert thread_state.is_comment_seen("c2")  # still there


def test_prune_stale_bridge():
    """6C-6: DiscussionsBridge prunes old rate-limit entries."""
    import time
    from city.discussions_bridge import DiscussionsBridge

    bridge = DiscussionsBridge.__new__(DiscussionsBridge)
    bridge._responded_discussions = {
        1: time.time() - 200000,  # old — should be pruned
        2: time.time() - 100,     # recent — should stay
    }

    pruned = bridge.prune_stale(ttl_s=86400)
    assert pruned == 1
    assert 1 not in bridge._responded_discussions
    assert 2 in bridge._responded_discussions
