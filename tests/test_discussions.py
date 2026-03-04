"""
Tests for DiscussionsBridge + DiscussionsInbox.

All GitHub API calls are mocked — zero network.
Tests cover: scan dedup, comment posting, rate limiting, seed threads,
agent intro/action posts, city reports, cross-posting, snapshot/restore,
and discussions_inbox composition/dispatch.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import patch


from city.discussions_bridge import DiscussionsBridge

# ── Helpers ────────────────────────────────────────────────────────────


def _make_bridge(**overrides) -> DiscussionsBridge:
    """Create a DiscussionsBridge with test defaults."""
    kwargs = {
        "_repo_id": "R_test123",
        "_owner": "testowner",
        "_repo": "testrepo",
        "_categories": {"General": "CAT_general", "Ideas": "CAT_ideas",
                         "Announcements": "CAT_announce", "Show and tell": "CAT_show"},
    }
    kwargs.update(overrides)
    return DiscussionsBridge(**kwargs)


def _scan_response(nodes: list[dict]) -> dict:
    """Build a mock scan response."""
    return {
        "data": {
            "repository": {
                "discussions": {"nodes": nodes},
            }
        }
    }


def _discussion_node(number: int, title: str = "Test", author: str = "alice",
                     comments: list[dict] | None = None) -> dict:
    return {
        "number": number,
        "title": title,
        "createdAt": "2025-01-01T00:00:00Z",
        "author": {"login": author},
        "comments": {"nodes": comments or []},
    }


def _comment_node(cid: str, body: str = "hello", author: str = "bob") -> dict:
    return {"id": cid, "body": body, "author": {"login": author}, "createdAt": "2025-01-01"}


def _get_discussion_response(disc_id: str, number: int) -> dict:
    return {
        "data": {
            "repository": {
                "discussion": {
                    "id": disc_id, "number": number, "title": "T", "body": "B",
                    "comments": {"nodes": []},
                }
            }
        }
    }


def _add_comment_response(comment_id: str) -> dict:
    return {
        "data": {
            "addDiscussionComment": {
                "comment": {"id": comment_id},
            }
        }
    }


def _create_discussion_response(number: int) -> dict:
    return {
        "data": {
            "createDiscussion": {
                "discussion": {"number": number, "url": f"https://example.com/{number}"},
            }
        }
    }


# ── GAD-000: Discoverable ─────────────────────────────────────────────


def test_capabilities_returns_list():
    caps = DiscussionsBridge.capabilities()
    assert isinstance(caps, list)
    assert len(caps) >= 4
    ops = {c["op"] for c in caps}
    assert "scan" in ops
    assert "create_discussion" in ops
    assert "comment" in ops
    assert "post_city_report" in ops


# ── Scan ──────────────────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_scan_returns_new_discussions(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = _scan_response([
        _discussion_node(1, "First"),
        _discussion_node(2, "Second"),
    ])

    signals = bridge.scan()
    assert len(signals) == 2
    assert signals[0]["number"] == 1
    assert signals[0]["is_new"] is True
    assert signals[1]["number"] == 2


@patch("city.discussions_bridge._gh_graphql")
def test_scan_dedup_discussions(mock_gql):
    bridge = _make_bridge()
    node = _discussion_node(1, "First")
    mock_gql.return_value = _scan_response([node])

    # First scan: new
    signals = bridge.scan()
    assert len(signals) == 1
    assert signals[0]["is_new"] is True

    # Second scan: same discussion, no new comments → empty
    mock_gql.return_value = _scan_response([node])
    signals = bridge.scan()
    assert len(signals) == 0


@patch("city.discussions_bridge._gh_graphql")
def test_scan_dedup_comments(mock_gql):
    bridge = _make_bridge()
    c1 = _comment_node("c1", "hi")
    node = _discussion_node(1, "First", comments=[c1])
    mock_gql.return_value = _scan_response([node])

    signals = bridge.scan()
    assert len(signals) == 1
    assert len(signals[0]["new_comments"]) == 1

    # Same comment again → no new comments, discussion already seen
    mock_gql.return_value = _scan_response([node])
    signals = bridge.scan()
    assert len(signals) == 0


@patch("city.discussions_bridge._gh_graphql")
def test_scan_new_comment_on_old_discussion(mock_gql):
    bridge = _make_bridge()
    # First scan: discussion with comment c1
    mock_gql.return_value = _scan_response([
        _discussion_node(1, "First", comments=[_comment_node("c1")]),
    ])
    bridge.scan()

    # Second scan: same discussion, new comment c2
    mock_gql.return_value = _scan_response([
        _discussion_node(1, "First", comments=[_comment_node("c1"), _comment_node("c2", "new")]),
    ])
    signals = bridge.scan()
    assert len(signals) == 1
    assert signals[0]["is_new"] is False
    assert len(signals[0]["new_comments"]) == 1
    assert signals[0]["new_comments"][0]["id"] == "c2"


@patch("city.discussions_bridge._gh_graphql")
def test_scan_gh_failure_returns_empty(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = None
    assert bridge.scan() == []


@patch("city.discussions_bridge._gh_graphql")
def test_scan_increments_ops(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = _scan_response([])
    bridge.scan()
    bridge.scan()
    assert bridge.stats()["ops"]["scans"] == 2


# ── Comment ───────────────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_comment_success(mock_gql):
    bridge = _make_bridge()
    mock_gql.side_effect = [
        _get_discussion_response("D_abc", 1),
        _add_comment_response("C_new"),
    ]
    assert bridge.comment(1, "test body") is True
    assert bridge.stats()["ops"]["comments"] == 1


@patch("city.discussions_bridge._gh_graphql")
def test_comment_discussion_not_found(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = {"data": {"repository": {"discussion": None}}}
    assert bridge.comment(999, "test") is False


@patch("city.discussions_bridge._gh_graphql")
def test_comment_gh_failure(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = None
    assert bridge.comment(1, "test") is False


# ── Create Discussion ─────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_create_discussion_success(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = _create_discussion_response(42)

    number = bridge.create_discussion("Title", "Body", category="General")
    assert number == 42
    assert bridge.stats()["ops"]["posts"] == 1


@patch("city.discussions_bridge._gh_graphql")
def test_create_discussion_unknown_category(mock_gql):
    bridge = _make_bridge()
    number = bridge.create_discussion("T", "B", category="NONEXISTENT")
    assert number is None
    mock_gql.assert_not_called()


@patch("city.discussions_bridge._gh_graphql")
def test_create_discussion_gh_failure(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = None
    number = bridge.create_discussion("T", "B", category="General")
    assert number is None


# ── Rate Limiting ─────────────────────────────────────────────────────


def test_rate_limit_per_cycle():
    bridge = _make_bridge()
    # Config max_agent_comments_per_cycle (default 5 in city.yaml)
    from city.discussions_bridge import _MAX_COMMENTS_PER_CYCLE

    for i in range(_MAX_COMMENTS_PER_CYCLE):
        bridge.record_response(i + 1)
    assert bridge.can_respond(99) is False

    bridge.reset_cycle()
    assert bridge.can_respond(99) is True


def test_rate_limit_per_thread_cooldown():
    bridge = _make_bridge()
    bridge.record_response(1)

    # Just responded → can't respond again (cooldown 600s)
    assert bridge.can_respond(1) is False
    # Different thread → ok (within cycle limit)
    assert bridge.can_respond(2) is True


def test_is_own_comment():
    from city.discussions_bridge import _SKIP_OWN_USERNAME

    assert DiscussionsBridge.is_own_comment(_SKIP_OWN_USERNAME) is True
    assert DiscussionsBridge.is_own_comment("alice") is False


# ── Seed Discussions ──────────────────────────────────────────────────


def _empty_scan_response():
    """Empty discussion scan result (no existing discussions)."""
    return {"data": {"repository": {"discussions": {"nodes": []}}}}


@patch("city.discussions_bridge._gh_graphql")
def test_seed_discussions_creates_threads(mock_gql):
    bridge = _make_bridge()
    # First call: recover_seed_threads scan (finds nothing)
    # Then 5 create calls (welcome, registry, ideas, city_log, brainstream)
    mock_gql.side_effect = [
        _empty_scan_response(),
        _create_discussion_response(10),
        _create_discussion_response(11),
        _create_discussion_response(12),
        _create_discussion_response(13),
        _create_discussion_response(14),
    ]
    created = bridge.seed_discussions()
    assert len(created) == 5
    assert "welcome" in created
    assert "registry" in created
    assert "ideas" in created
    assert "city_log" in created
    assert "brainstream" in created


@patch("city.discussions_bridge._gh_graphql")
def test_seed_discussions_idempotent(mock_gql):
    bridge = _make_bridge()
    mock_gql.side_effect = [
        _empty_scan_response(),  # recovery scan
        _create_discussion_response(10),
        _create_discussion_response(11),
        _create_discussion_response(12),
        _create_discussion_response(13),
        _create_discussion_response(14),
    ]
    bridge.seed_discussions()

    # Second call should not create anything (threads in _seed_threads)
    mock_gql.reset_mock()
    created = bridge.seed_discussions()
    assert len(created) == 0
    mock_gql.assert_not_called()


@patch("city.discussions_bridge._gh_graphql")
def test_recover_seed_threads_from_scan(mock_gql):
    """recover_seed_threads() finds existing threads by title match."""
    bridge = _make_bridge()
    assert len(bridge._seed_threads) == 0

    # Simulate scan returning existing seed threads
    mock_gql.return_value = {
        "data": {"repository": {"discussions": {"nodes": [
            {"number": 24, "title": "Welcome to Agent City",
             "createdAt": "2026-01-01", "author": {"login": "bot"},
             "comments": {"nodes": []}},
            {"number": 25, "title": "Active Agents Registry",
             "createdAt": "2026-01-01", "author": {"login": "bot"},
             "comments": {"nodes": []}},
            {"number": 26, "title": "City Ideas & Proposals",
             "createdAt": "2026-01-01", "author": {"login": "bot"},
             "comments": {"nodes": []}},
            {"number": 41, "title": "City Log — Heartbeat Reports",
             "createdAt": "2026-01-01", "author": {"login": "bot"},
             "comments": {"nodes": []}},
        ]}}}
    }

    result = bridge.recover_seed_threads()
    assert result["welcome"] == 24
    assert result["registry"] == 25
    assert result["ideas"] == 26
    assert result["city_log"] == 41


# ── Agent Intro ───────────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_post_agent_intro(mock_gql):
    bridge = _make_bridge()
    bridge._seed_threads["registry"] = 11

    mock_gql.side_effect = [
        _get_discussion_response("D_reg", 11),
        _add_comment_response("C_intro"),
    ]

    spec = {
        "name": "TestAgent", "domain": "ENGINEERING", "guna": "RAJAS",
        "element": "agni", "guardian": "prahlada", "capability_tier": "contributor",
        "capability_protocol": "validate", "role": "testing", "capabilities": ["validate"],
        "chapter": 1, "chapter_significance": "Test", "element_capabilities": ["observe"],
        "guardian_capabilities": ["enforce"], "qos": {"latency_multiplier": 1, "parallel": True},
    }

    assert bridge.post_agent_intro(spec) is True


def test_post_agent_intro_no_registry():
    bridge = _make_bridge()
    # No seed threads → returns False
    assert bridge.post_agent_intro({"name": "X"}) is False


# ── Agent Action Post ────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_post_agent_action(mock_gql):
    bridge = _make_bridge()
    bridge._seed_threads["city_log"] = 12

    mock_gql.side_effect = [
        _get_discussion_response("D_log", 12),
        _add_comment_response("C_action"),
    ]

    spec = {"name": "TestAgent", "domain": "ENGINEERING", "guna": "RAJAS",
            "element": "agni", "guardian": "prahlada", "capability_tier": "contributor",
            "capability_protocol": "validate", "role": "testing", "capabilities": ["validate"]}
    action = {"function": "BRAHMA", "_operation": "council_propose",
              "composed": "test signal", "chapter": 3, "prana": 100, "integrity": 0.95}

    assert bridge.post_agent_action(spec, action, "mission_42") is True


# ── City Pulse ────────────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_post_pulse(mock_gql):
    bridge = _make_bridge()
    bridge._seed_threads["welcome"] = 10

    mock_gql.side_effect = [
        _get_discussion_response("D_welcome", 10),
        _add_comment_response("C_pulse"),
    ]

    assert bridge.post_pulse(1, {"alive": 5, "total": 10, "events": 3}) is True


def test_post_pulse_no_welcome():
    bridge = _make_bridge()
    assert bridge.post_pulse(1, {}) is False


# ── City Report ──────────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_post_city_report(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = _create_discussion_response(99)

    reflection = {
        "city_stats": {"total": 10, "alive": 8},
        "chain_valid": True,
    }
    assert bridge.post_city_report(1, reflection) is True
    assert bridge._last_report_hb == 1


@patch("city.discussions_bridge._gh_graphql")
def test_post_city_report_rate_limited(mock_gql):
    bridge = _make_bridge()
    mock_gql.return_value = _create_discussion_response(99)

    reflection = {"city_stats": {"total": 10, "alive": 8}, "chain_valid": True}
    bridge.post_city_report(1, reflection)

    # Same heartbeat → blocked
    assert bridge.post_city_report(1, reflection) is False

    # Too soon (gap < _REPORT_EVERY_N=4)
    assert bridge.post_city_report(3, reflection) is False

    # Enough gap → allowed
    mock_gql.return_value = _create_discussion_response(100)
    assert bridge.post_city_report(5, reflection) is True


# ── Cross-Post ────────────────────────────────────────────────────────


@patch("city.discussions_bridge._gh_graphql")
def test_cross_post_mission_results(mock_gql):
    bridge = _make_bridge()
    mock_gql.side_effect = [
        _create_discussion_response(50),
        _create_discussion_response(51),
    ]

    results = [
        {"name": "heal_ruff", "status": "completed", "owner": "immune"},
        {"name": "audit_lint", "status": "completed", "owner": "immune", "pr_url": "https://pr/1"},
    ]
    count = bridge.cross_post_mission_results(results)
    assert count == 2


# ── Snapshot / Restore ────────────────────────────────────────────────


def test_snapshot_restore_roundtrip():
    bridge = _make_bridge()
    bridge._seen_discussion_numbers = {1, 2, 3}
    bridge._seen_comment_ids = {"c1", "c2"}
    bridge._last_report_hb = 42
    bridge._ops = {"scans": 10, "posts": 5, "comments": 3}
    bridge._responded_discussions = {1: 1000.0, 2: 2000.0}
    bridge._seed_threads = {"welcome": 10, "registry": 11}

    snap = bridge.snapshot()

    # Restore into fresh bridge
    new_bridge = _make_bridge()
    new_bridge.restore(snap)

    assert new_bridge._seen_discussion_numbers == {1, 2, 3}
    assert new_bridge._seen_comment_ids == {"c1", "c2"}
    assert new_bridge._last_report_hb == 42
    assert new_bridge._ops["scans"] == 10
    assert new_bridge._responded_discussions[1] == 1000.0
    assert new_bridge._seed_threads["welcome"] == 10


def test_snapshot_restore_empty():
    bridge = _make_bridge()
    snap = bridge.snapshot()

    new_bridge = _make_bridge()
    new_bridge.restore(snap)
    assert new_bridge.stats()["discussions_seen"] == 0


# ── Stats ─────────────────────────────────────────────────────────────


def test_stats_structure():
    bridge = _make_bridge()
    stats = bridge.stats()
    assert "discussions_seen" in stats
    assert "comments_seen" in stats
    assert "last_report_hb" in stats
    assert "ops" in stats
    assert stats["ops"]["scans"] == 0


# ══════════════════════════════════════════════════════════════════════
# DiscussionsInbox Tests
# ══════════════════════════════════════════════════════════════════════


from city.discussions_inbox import (
    AgentDiscussionResponse,
    DiscussionSignal,
    build_action_report,
    build_agent_intro,
    classify_discussion_intent,
    dispatch_discussion,
    extract_mentions,
)


# ── Mention Extraction ────────────────────────────────────────────────


def test_extract_mentions_basic():
    assert extract_mentions("hello @alice and @bob") == ["alice", "bob"]


def test_extract_mentions_none():
    assert extract_mentions("no mentions here") == []


def test_extract_mentions_with_hyphens():
    assert extract_mentions("cc @my-agent") == ["my-agent"]


# ── Intent Classification ─────────────────────────────────────────────


def test_classify_brahma_propose():
    assert classify_discussion_intent({"buddhi_function": "BRAHMA"}) == "propose"


def test_classify_vishnu_inquiry():
    assert classify_discussion_intent({"buddhi_function": "VISHNU"}) == "inquiry"


def test_classify_shiva_govern():
    assert classify_discussion_intent({"buddhi_function": "SHIVA"}) == "govern"


def test_classify_unknown_observe():
    assert classify_discussion_intent({"buddhi_function": ""}) == "observe"
    assert classify_discussion_intent({}) == "observe"


# ── Agent Intro ───────────────────────────────────────────────────────


def test_build_agent_intro_contains_identity():
    spec = {
        "name": "Arjuna", "domain": "ENGINEERING", "guna": "RAJAS",
        "element": "agni", "guardian": "prahlada", "capability_tier": "contributor",
        "capability_protocol": "validate", "role": "warrior architect",
        "capabilities": ["validate", "transform"], "chapter": 2,
        "chapter_significance": "Strategic clarity",
        "element_capabilities": ["observe", "transform"],
        "guardian_capabilities": ["enforce"],
        "qos": {"latency_multiplier": 1, "parallel": True},
    }
    intro = build_agent_intro(spec)
    assert "Arjuna" in intro
    assert "ENGINEERING" in intro
    assert "warrior architect" in intro
    assert "validate" in intro
    assert "Strategic clarity" in intro


def test_build_agent_intro_minimal():
    spec = {"name": "Min", "domain": "?", "guna": "?", "element": "?",
            "guardian": "?", "capability_tier": "observer",
            "capability_protocol": "?", "role": "agent", "capabilities": []}
    intro = build_agent_intro(spec)
    assert "Min" in intro


# ── Action Report ─────────────────────────────────────────────────────


def test_build_action_report_structure():
    spec = {"name": "TestBot", "domain": "GOVERNANCE", "guna": "SATTVA",
            "element": "akasha", "guardian": "shuka", "capability_tier": "steward",
            "capability_protocol": "enforce", "role": "agent"}
    action = {"function": "SHIVA", "_operation": "trigger_audit",
              "composed": "integrity check needed", "chapter": 5,
              "prana": 200, "integrity": 0.99}

    report = build_action_report(spec, action, "mission_99")
    assert "TestBot" in report
    assert "triggered a code audit" in report
    assert "99" in report


def test_build_action_report_no_composed():
    spec = {"name": "Bot", "domain": "?", "guna": "?", "element": "?",
            "guardian": "?", "capability_tier": "observer",
            "capability_protocol": "?", "role": "agent"}
    action = {"function": "BRAHMA", "_operation": "create", "composed": "",
              "chapter": 1, "prana": 50, "integrity": 1.0}
    report = build_action_report(spec, action, "m1")
    assert "Bot" in report
    assert "performed action: create" in report


# ── Dispatch ──────────────────────────────────────────────────────────


def test_dispatch_returns_response():
    from city.brain import Thought

    signal = DiscussionSignal(
        discussion_number=42, title="Test", body="hello @TestBot",
        author="alice", mentioned_agents=["TestBot"],
    )
    gateway_result = {"buddhi_function": "VISHNU", "buddhi_chapter": 3}
    spec = {"name": "TestBot", "domain": "DISCOVERY", "guna": "SATTVA",
            "element": "akasha", "guardian": "shuka", "capability_tier": "contributor",
            "capability_protocol": "observe", "role": "observer",
            "capabilities": ["observe", "report"]}
    city_stats = {"active": 3, "citizen": 2, "total": 10}

    response = dispatch_discussion(signal, gateway_result, spec, city_stats,
                                   brain_thought=Thought(comprehension="test"))
    assert isinstance(response, AgentDiscussionResponse)
    assert response.discussion_number == 42
    assert response.agent_name == "TestBot"
    assert "TestBot" in response.body
    assert "DISCOVERY" in response.body
    assert "5/10" in response.body


def test_dispatch_different_gunas():
    """Each guna produces different frame label."""
    from city.brain import Thought

    signal = DiscussionSignal(1, "T", "B", "alice", [])
    spec_base = {"name": "A", "domain": "D", "element": "e", "guardian": "g",
                 "capability_tier": "t", "capability_protocol": "p",
                 "role": "r", "capabilities": []}

    _thought = Thought(comprehension="test")
    frames = set()
    for guna in ("SATTVA", "RAJAS", "TAMAS"):
        spec = {**spec_base, "guna": guna}
        resp = dispatch_discussion(signal, {"buddhi_function": "BRAHMA"}, spec, {},
                                   brain_thought=_thought)
        frames.add(resp.body)

    # All three should be different (different frame labels)
    assert len(frames) == 3
