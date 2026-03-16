"""Discussions Commands Tests — command parsing, execution, conversation state, brain feedback."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from city.discussions_commands import (
    ConversationThread,
    ConversationTracker,
    DiscussionCommand,
    execute_command,
    extract_brain_feedback,
    format_help,
    parse_commands,
)


# ── Command Parsing ──────────────────────────────────────────────────


def test_parse_single_command():
    """Parse a single /status command."""
    cmds = parse_commands("/status", author="alice", discussion_number=42)
    assert len(cmds) == 1
    assert cmds[0].command == "status"
    assert cmds[0].args == ""
    assert cmds[0].author == "alice"
    assert cmds[0].discussion_number == 42


def test_parse_command_with_args():
    """Parse /mission with arguments."""
    cmds = parse_commands("/mission fix the flaky tests", author="bob")
    assert len(cmds) == 1
    assert cmds[0].command == "mission"
    assert cmds[0].args == "fix the flaky tests"


def test_parse_ping_command():
    """Parse /ping with agent name."""
    cmds = parse_commands("/ping SecurityAgent", author="carol")
    assert len(cmds) == 1
    assert cmds[0].command == "ping"
    assert cmds[0].args == "SecurityAgent"


def test_parse_multiple_commands():
    """Parse multiple commands in a single body."""
    body = "/status\nSome text here\n/agents"
    cmds = parse_commands(body)
    assert len(cmds) == 2
    assert cmds[0].command == "status"
    assert cmds[1].command == "agents"


def test_parse_no_commands():
    """No commands in plain text."""
    cmds = parse_commands("Just a regular comment with no commands")
    assert len(cmds) == 0


def test_parse_command_case_insensitive():
    """Commands are lowercased."""
    cmds = parse_commands("/Status")
    assert len(cmds) == 1
    assert cmds[0].command == "status"


def test_parse_command_with_leading_whitespace():
    """Commands can have leading whitespace."""
    cmds = parse_commands("  /help")
    assert len(cmds) == 1
    assert cmds[0].command == "help"


def test_command_is_valid():
    """is_valid checks against known commands."""
    cmds = parse_commands("/status\n/bogus")
    assert cmds[0].is_valid is True
    assert cmds[1].is_valid is False


def test_parse_heal_command():
    """Parse /heal with contract name."""
    cmds = parse_commands("/heal ruff_clean")
    assert len(cmds) == 1
    assert cmds[0].command == "heal"
    assert cmds[0].args == "ruff_clean"


def test_format_help():
    """format_help returns markdown with all commands."""
    text = format_help()
    assert "Available Commands" in text
    assert "`/status`" in text
    assert "`/help`" in text
    assert "`/mission`" in text


# ── Conversation State ───────────────────────────────────────────────


def test_conversation_thread_tracks_commands():
    """ConversationThread records commands and participants."""
    thread = ConversationThread(
        discussion_number=42, participants=set(), command_history=[],
    )
    cmd = DiscussionCommand(
        command="status", args="", author="alice",
        discussion_number=42, comment_id="abc", raw_line="/status",
    )
    thread.record_command(cmd)
    assert "alice" in thread.participants
    assert "/status" in thread.command_history
    assert thread.turn_count == 1


def test_conversation_thread_tracks_responses():
    """record_response updates heartbeat and turn count."""
    thread = ConversationThread(
        discussion_number=1, participants=set(), command_history=[],
    )
    thread.record_response(heartbeat=10)
    assert thread.last_agent_response_hb == 10
    assert thread.turn_count == 1


def test_conversation_thread_roundtrip():
    """to_dict/from_dict roundtrip preserves state."""
    thread = ConversationThread(
        discussion_number=42,
        participants={"alice", "bob"},
        command_history=["/status", "/agents"],
        last_agent_response_hb=5,
        turn_count=4,
        brain_feedback_count=1,
    )
    d = thread.to_dict()
    restored = ConversationThread.from_dict(d)
    assert restored.discussion_number == 42
    assert restored.participants == {"alice", "bob"}
    assert restored.command_history == ["/status", "/agents"]
    assert restored.last_agent_response_hb == 5
    assert restored.turn_count == 4
    assert restored.brain_feedback_count == 1


def test_tracker_get_or_create():
    """get_or_create creates new thread on first access."""
    tracker = ConversationTracker()
    assert tracker.active_count == 0
    thread = tracker.get_or_create(42)
    assert tracker.active_count == 1
    # Second call returns same thread
    same = tracker.get_or_create(42)
    assert same is thread
    assert tracker.active_count == 1


def test_tracker_get_returns_none():
    """get() returns None for unknown threads."""
    tracker = ConversationTracker()
    assert tracker.get(999) is None


def test_tracker_snapshot_restore():
    """snapshot/restore preserves all threads."""
    tracker = ConversationTracker()
    t1 = tracker.get_or_create(1)
    t1.participants.add("alice")
    t2 = tracker.get_or_create(2)
    t2.participants.add("bob")

    data = tracker.snapshot()
    assert len(data) == 2

    tracker2 = ConversationTracker()
    tracker2.restore(data)
    assert tracker2.active_count == 2
    assert "alice" in tracker2.get(1).participants
    assert "bob" in tracker2.get(2).participants


# ── Brain Feedback ───────────────────────────────────────────────────


def test_extract_brain_feedback_normal():
    """Human comment becomes brain feedback dict."""
    fb = extract_brain_feedback(
        "This is a great idea, we should explore the healing capabilities further.",
        author="alice",
        discussion_number=42,
        heartbeat=10,
    )
    assert fb is not None
    assert fb["intent"] == "external_feedback"
    assert fb["source"] == "discussion"
    assert fb["discussion_number"] == 42
    assert fb["heartbeat"] == 10
    assert "alice" in fb["key_concepts"][0]
    assert len(fb["comprehension"]) > 0


def test_extract_brain_feedback_skips_bot():
    """Bot comments are not fed back."""
    fb = extract_brain_feedback(
        "Some bot output text here.",
        author="github-actions[bot]",
    )
    assert fb is None


def test_extract_brain_feedback_skips_empty():
    """Empty or trivially short comments are skipped."""
    assert extract_brain_feedback("hi") is None
    assert extract_brain_feedback("") is None
    assert extract_brain_feedback("   ok   ") is None


def test_extract_brain_feedback_skips_pure_command():
    """Comments that are only commands are skipped."""
    fb = extract_brain_feedback("/status\n/agents", author="alice")
    assert fb is None


def test_extract_brain_feedback_truncates_long():
    """Long comments are truncated to 800 chars."""
    long_text = "a" * 1000
    fb = extract_brain_feedback(long_text, author="alice")
    assert fb is not None
    assert len(fb["comprehension"]) <= 800


def test_extract_brain_feedback_mixed_command_and_prose():
    """Comments with commands + prose extract just the prose."""
    fb = extract_brain_feedback(
        "/status\nI think we should focus on improving test coverage for the immune system.",
        author="alice",
    )
    assert fb is not None
    assert "test coverage" in fb["comprehension"]


# ── Command Execution ───────────────────────────────────────────────


def _make_cmd(command: str, args: str = "", author: str = "testuser") -> DiscussionCommand:
    """Helper to build a DiscussionCommand for testing."""
    return DiscussionCommand(
        command=command,
        args=args,
        author=author,
        discussion_number=42,
        comment_id="test_comment_1",
        raw_line=f"/{command} {args}".strip(),
    )


def _make_mock_ctx(tmp: Path):
    """Build a minimal mock PhaseContext for command execution tests."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp / "economy.db"))
    pokedex = Pokedex(db_path=str(tmp / "city.db"), bank=bank)

    ctx = MagicMock()
    ctx.pokedex = pokedex
    ctx.heartbeat_count = 10
    ctx.council = None
    ctx.contracts = None
    ctx.thread_state = None
    ctx.sankalpa = None
    ctx.offline_mode = True
    ctx.state_path = tmp / "mayor_state.json"
    return ctx


def test_exec_help():
    """/help returns available commands."""
    cmd = _make_cmd("help")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "Available Commands" in result
        assert "`/status`" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_status():
    """/status returns city status."""
    cmd = _make_cmd("status")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "City Status" in result
        assert "Heartbeat #10" in result
        assert "Population" in result
        assert "Chain integrity" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_agents_empty():
    """/agents with no citizens returns appropriate message."""
    cmd = _make_cmd("agents")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "None" in result or "Active Agents" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_agents_with_citizens():
    """/agents lists registered citizens."""
    cmd = _make_cmd("agents")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        ctx.pokedex.register("TestAgent")
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "TestAgent" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_ping_found():
    """/ping existing agent returns info."""
    cmd = _make_cmd("ping", "TestBot")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        ctx.pokedex.discover("TestBot", moltbook_profile={})
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "TestBot" in result
        assert "Status" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_ping_not_found():
    """/ping unknown agent returns not found."""
    cmd = _make_cmd("ping", "GhostAgent")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "not found" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_ping_no_args():
    """/ping without args returns usage."""
    cmd = _make_cmd("ping")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "Usage" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_mission_no_args():
    """/mission without args returns usage."""
    cmd = _make_cmd("mission")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "Usage" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_mission_no_sankalpa():
    """/mission with no sankalpa returns unavailable."""
    cmd = _make_cmd("mission", "fix tests")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "not available" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_invalid_command():
    """Invalid command returns None."""
    cmd = _make_cmd("bogus")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is None
    finally:
        shutil.rmtree(tmp)


def test_exec_heal_no_args():
    """/heal without args returns usage."""
    cmd = _make_cmd("heal")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "Usage" in result
    finally:
        shutil.rmtree(tmp)


def test_exec_heal_no_contracts():
    """/heal with no contract system returns unavailable."""
    cmd = _make_cmd("heal", "integrity")
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_mock_ctx(tmp)
        result = execute_command(cmd, ctx)
        assert result is not None
        assert "not available" in result
    finally:
        shutil.rmtree(tmp)
