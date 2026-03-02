"""Discussions Commands Tests — command parsing, conversation state, brain feedback."""

from city.discussions_commands import (
    ConversationThread,
    ConversationTracker,
    DiscussionCommand,
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
    """Long comments are truncated to 300 chars."""
    long_text = "a" * 500
    fb = extract_brain_feedback(long_text, author="alice")
    assert fb is not None
    assert len(fb["comprehension"]) <= 300


def test_extract_brain_feedback_mixed_command_and_prose():
    """Comments with commands + prose extract just the prose."""
    fb = extract_brain_feedback(
        "/status\nI think we should focus on improving test coverage for the immune system.",
        author="alice",
    )
    assert fb is not None
    assert "test coverage" in fb["comprehension"]
