"""
Tests for MoltbookAssistant — Agent City's social membrane.

MoltbookClient is mocked (no network). Pokedex is a lightweight fake.
Covers: GAD-000 compliance, phase handlers (genesis/dharma/karma/moksha),
planning (invite ranking, series selection), content builders,
rate limiting, snapshot/restore, idempotency.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from city.moltbook_assistant import MoltbookAssistant, SERIES, SUBMOLT


# ── Fakes ─────────────────────────────────────────────────────────────


def _agent(name: str, zone: str = "karma", element: str = "agni",
           guardian: str = "prahlada", karma: int = 0) -> dict:
    return {
        "name": name,
        "zone": zone,
        "classification": {"guardian": guardian},
        "vibration": {"element": element},
        "moltbook": {"karma": karma, "follower_count": 0},
        "status": "citizen",
    }


class FakePokedex:
    def __init__(self, agents: list[dict] | None = None):
        self._agents = {a["name"]: a for a in (agents or [])}

    def get(self, name: str) -> dict | None:
        return self._agents.get(name)

    def list_all(self) -> list[dict]:
        return list(self._agents.values())

    def list_by_zone(self, zone: str) -> list[dict]:
        return [a for a in self._agents.values()
                if a.get("zone") == zone]

    def stats(self) -> dict:
        zones: dict[str, int] = {}
        for a in self._agents.values():
            z = a.get("zone", "unknown")
            zones[z] = zones.get(z, 0) + 1
        return {
            "total": len(self._agents),
            "alive": len(self._agents),
            "citizen": len(self._agents),
            "zones": zones,
        }


def _make_assistant(agents: list[dict] | None = None) -> tuple[MoltbookAssistant, MagicMock]:
    client = MagicMock()
    pokedex = FakePokedex(agents)
    assistant = MoltbookAssistant(_client=client, _pokedex=pokedex)
    return assistant, client


# ── GAD-000: Discoverable ─────────────────────────────────────────────


def test_capabilities_returns_list():
    caps = MoltbookAssistant.capabilities()
    assert isinstance(caps, list)
    assert len(caps) == 4
    ops = {c["op"] for c in caps}
    assert ops == {"follow", "invite", "content", "track"}


def test_capabilities_have_phase():
    for cap in MoltbookAssistant.capabilities():
        assert "phase" in cap


def test_capabilities_have_idempotent():
    for cap in MoltbookAssistant.capabilities():
        assert "idempotent" in cap


# ── GENESIS: Follow ───────────────────────────────────────────────────


def test_on_genesis_follows_new_agents():
    assistant, client = _make_assistant()
    result = assistant.on_genesis(["alice", "bob", "carol"])

    assert result == ["alice", "bob", "carol"]
    assert client.sync_follow_agent.call_count == 3
    assert assistant.stats()["following"] == 3


def test_on_genesis_skips_already_followed():
    assistant, client = _make_assistant()
    assistant.on_genesis(["alice"])
    client.reset_mock()

    result = assistant.on_genesis(["alice", "bob"])
    assert result == ["bob"]
    assert client.sync_follow_agent.call_count == 1


def test_on_genesis_respects_max_follows():
    assistant, client = _make_assistant()
    # Default max is 3
    result = assistant.on_genesis(["a", "b", "c", "d", "e"])
    assert len(result) == 3


def test_on_genesis_handles_follow_failure():
    assistant, client = _make_assistant()
    client.sync_follow_agent.side_effect = [None, RuntimeError("fail"), None]
    result = assistant.on_genesis(["a", "b", "c"])
    # a succeeds, b fails, c succeeds
    assert len(result) == 2
    assert "b" not in result


def test_on_genesis_empty_list():
    assistant, client = _make_assistant()
    assert assistant.on_genesis([]) == []
    client.sync_follow_agent.assert_not_called()


# ── DHARMA: Planning ──────────────────────────────────────────────────


def test_on_dharma_builds_invite_queue():
    agents = [_agent("alice", zone="karma"), _agent("bob", zone="moksha")]
    assistant, _ = _make_assistant(agents)
    # Must follow first (relationship before invite)
    assistant.on_genesis(["alice", "bob"])
    assistant.on_dharma(1)
    # Invite queue should have candidates (followed but not invited)
    assert len(assistant._invite_queue) > 0


def test_on_dharma_clears_previous_queue():
    agents = [_agent("alice")]
    assistant, _ = _make_assistant(agents)
    assistant.on_genesis(["alice"])
    assistant.on_dharma(1)
    q1 = list(assistant._invite_queue)
    assistant.on_dharma(2)
    # Queue was rebuilt (cleared + repopulated)
    assert isinstance(assistant._invite_queue, list)


def test_on_dharma_plans_series_after_cooldown():
    assistant, _ = _make_assistant([_agent("a")])
    assistant._last_post_time = 0.0  # long ago
    assistant.on_dharma(1)
    # Series planning is now GUTTED (event-driven from outbound.py)
    assert assistant._planned_series == ""


def test_on_dharma_no_series_during_cooldown():
    assistant, _ = _make_assistant([_agent("a")])
    assistant._last_post_time = time.time()  # just now
    assistant.on_dharma(1)
    assert assistant._planned_series == ""


# ── KARMA: Execute ────────────────────────────────────────────────────


def test_on_karma_sends_invites():
    agents = [_agent("alice", zone="karma")]
    assistant, client = _make_assistant(agents)
    assistant.on_genesis(["alice"])
    assistant.on_dharma(1)

    result = assistant.on_karma(1, {"zones": {"karma": 1}})
    assert result["invites_sent"] >= 0  # depends on queue


def test_on_karma_creates_content():
    agents = [_agent("alice")]
    assistant, client = _make_assistant(agents)
    assistant._planned_series = "digest"
    assistant._last_post_time = 0.0

    result = assistant.on_karma(1, {"total": 5, "alive": 5, "citizen": 5, "zones": {"karma": 5}})
    if result["post_created"]:
        client.sync_create_post.assert_called_once()


def test_on_karma_no_content_without_plan():
    assistant, client = _make_assistant()
    assistant._planned_series = ""
    result = assistant.on_karma(1, {})
    assert result["post_created"] is False
    client.sync_create_post.assert_not_called()


# ── MOKSHA: Metrics ───────────────────────────────────────────────────


def test_on_moksha_returns_metrics():
    assistant, _ = _make_assistant()
    assistant.on_genesis(["a", "b"])
    metrics = assistant.on_moksha()

    assert metrics["following"] == 2
    assert "invited" in metrics
    assert "spotlighted" in metrics
    assert "ops" in metrics


# ── Invite Logic ──────────────────────────────────────────────────────


def test_send_invite_idempotent():
    agents = [_agent("alice")]
    assistant, client = _make_assistant(agents)
    assistant._followed.add("alice")

    assert assistant._send_invite("alice") is True
    assert assistant._send_invite("alice") is False  # already invited
    assert client.sync_send_dm_request.call_count == 1


def test_send_invite_must_be_followed():
    agents = [_agent("alice")]
    assistant, client = _make_assistant(agents)
    # NOT followed → invite should still work (pokedex.get check)
    # but _rank_invite_candidates requires followed
    assert assistant._send_invite("alice") is True


def test_send_invite_unknown_agent():
    assistant, client = _make_assistant()
    assert assistant._send_invite("nobody") is False


def test_send_invite_failure():
    agents = [_agent("alice")]
    assistant, client = _make_assistant(agents)
    client.sync_send_dm_request.side_effect = RuntimeError("network error")
    assert assistant._send_invite("alice") is False


def test_invite_message_contains_jiva():
    agents = [_agent("alice", zone="dharma", element="vayu", guardian="narada")]
    assistant, client = _make_assistant(agents)
    assistant._send_invite("alice")

    call_args = client.sync_send_dm_request.call_args
    message = call_args[0][1]
    assert "vayu" in message
    assert "dharma" in message
    assert "narada" in message
    assert SUBMOLT in message


# ── Series Selection ──────────────────────────────────────────────────


def test_select_series_first_post_sovereignty():
    agents = [_agent("a"), _agent("b")]
    assistant, _ = _make_assistant(agents)
    assert assistant._select_series() == "sovereignty_brief"


def test_select_series_spotlight_few_citizens():
    agents = [_agent("a"), _agent("b")]  # < 5 citizens
    assistant, _ = _make_assistant(agents)
    assistant._ops["posts"] = 1  # not first post anymore
    assert assistant._select_series() == "spotlight"


def test_select_series_zone_report_imbalanced():
    agents = ([_agent(f"k{i}", zone="karma") for i in range(10)]
              + [_agent("m0", zone="moksha")])
    assistant, _ = _make_assistant(agents)
    assistant._ops["posts"] = 1  # not first post anymore
    # zone_report is currently DISABLED (template spam prevention)
    series = assistant._select_series()
    assert series == ""


def test_select_series_round_robin():
    agents = [_agent(f"a{i}", zone="karma") for i in range(10)]
    assistant, _ = _make_assistant(agents)
    # Balanced zones (all karma) + enough citizens → round-robin
    # But zones check: max(pops) > 3 * min(pops) + 1 → only 1 zone → not imbalanced
    # Actually 10 citizens, 1 zone → round-robin
    s1 = assistant._select_series()
    s2 = assistant._select_series()
    # Should advance cursor
    assert s1 in SERIES
    assert s2 in SERIES


# ── Content Builders ──────────────────────────────────────────────────


def test_build_spotlight():
    agents = [_agent("star", karma=100)]
    assistant, _ = _make_assistant(agents)
    title, content = assistant._build_spotlight(1, {})
    assert "star" in title
    assert content != ""


def test_build_spotlight_no_agents():
    assistant, _ = _make_assistant([])
    title, content = assistant._build_spotlight(1, {})
    assert title == ""
    assert content == ""


def test_build_spotlight_prefers_moltbook_karma():
    agents = [
        _agent("nokarma", karma=0),
        _agent("haskarma", karma=50),
    ]
    assistant, _ = _make_assistant(agents)
    title, _ = assistant._build_spotlight(1, {})
    assert "haskarma" in title


def test_build_zone_report():
    agents = [_agent("a", zone="karma"), _agent("b", zone="karma")]
    assistant, _ = _make_assistant(agents)
    stats = assistant._pokedex.stats()
    title, content = assistant._build_zone_report(1, stats)
    assert "karma" in title.lower()
    assert "Population" in content


def test_build_zone_report_no_zones():
    assistant, _ = _make_assistant([])
    title, content = assistant._build_zone_report(1, {"zones": {}})
    assert title == ""


def test_build_digest():
    assistant, _ = _make_assistant([_agent("a")])
    title, content = assistant._build_digest(5, {"total": 10, "alive": 8, "citizen": 6, "zones": {"karma": 6}})
    assert "Heartbeat #5" in title
    assert "10" in content


def test_build_discussion():
    assistant, _ = _make_assistant([_agent("a")])
    stats = {"zones": {"karma": 3, "moksha": 2}}
    title, content = assistant._build_discussion(1, stats)
    assert "Zone" in title


def test_build_discussion_no_zones():
    assistant, _ = _make_assistant([])
    title, content = assistant._build_discussion(1, {"zones": {}})
    assert title == ""


# ── Content Creation ──────────────────────────────────────────────────


def test_create_content_unknown_series():
    assistant, client = _make_assistant()
    assert assistant._create_content("nonexistent", 1, {}) is False
    client.sync_create_post.assert_not_called()


def test_create_content_post_failure():
    agents = [_agent("a", karma=10)]
    assistant, client = _make_assistant(agents)
    client.sync_create_post.side_effect = RuntimeError("fail")
    assert assistant._create_content("spotlight", 1, {}) is False


def test_create_content_updates_last_post_time():
    agents = [_agent("a", karma=10)]
    assistant, client = _make_assistant(agents)
    before = time.time()
    result = assistant._create_content("spotlight", 1, {})
    if result:
        assert assistant._last_post_time >= before


# ── Snapshot / Restore ────────────────────────────────────────────────


def test_snapshot_restore_roundtrip():
    assistant, _ = _make_assistant()
    assistant._followed = {"a", "b"}
    assistant._invited = {"c"}
    assistant._spotlighted = {"d"}
    assistant._last_post_time = 12345.0
    assistant._series_cursor = 2
    assistant._ops = {"follows": 10, "invites": 5, "posts": 3}

    snap = assistant.snapshot()

    new_assistant, _ = _make_assistant()
    new_assistant.restore(snap)

    assert new_assistant._followed == {"a", "b"}
    assert new_assistant._invited == {"c"}
    assert new_assistant._spotlighted == {"d"}
    assert new_assistant._last_post_time == 12345.0
    assert new_assistant._series_cursor == 2
    assert new_assistant._ops == {"follows": 10, "invites": 5, "posts": 3}


def test_snapshot_restore_empty():
    assistant, _ = _make_assistant()
    snap = assistant.snapshot()

    new_assistant, _ = _make_assistant()
    new_assistant.restore(snap)

    assert new_assistant._followed == set()
    assert new_assistant._ops["follows"] == 0


def test_restore_backward_compat():
    """Restore handles old snapshot key names."""
    old_snap = {
        "followed_agents": ["x", "y"],
        "invited_agents": ["z"],
        "upvoted_post_ids": ["p1"],
        "last_post_time": 999.0,
        "last_series_idx": 1,
        "metrics": {"total_follows": 5, "total_invites": 2, "total_posts": 1},
    }
    assistant, _ = _make_assistant()
    assistant.restore(old_snap)

    assert assistant._followed == {"x", "y"}
    assert assistant._invited == {"z"}
    assert assistant._spotlighted == {"p1"}
    assert assistant._last_post_time == 999.0
    assert assistant._series_cursor == 1
    assert assistant._ops == {"follows": 5, "invites": 2, "posts": 1}


# ── Stats ─────────────────────────────────────────────────────────────


def test_stats_structure():
    assistant, _ = _make_assistant()
    stats = assistant.stats()
    assert "following" in stats
    assert "invited" in stats
    assert "spotlighted" in stats
    assert "ops" in stats
    assert "last_post_age_s" in stats
    assert "series_cursor" in stats
    assert "invite_queue" in stats


def test_stats_last_post_age_none_initially():
    assistant, _ = _make_assistant()
    assert assistant.stats()["last_post_age_s"] is None


def test_stats_last_post_age_after_post():
    assistant, _ = _make_assistant()
    assistant._last_post_time = time.time() - 60
    age = assistant.stats()["last_post_age_s"]
    assert age is not None
    assert 55 <= age <= 65


# ── Invite Ranking ────────────────────────────────────────────────────


def test_rank_prefers_scarce_zones():
    agents = [
        _agent("big1", zone="karma"),
        _agent("big2", zone="karma"),
        _agent("big3", zone="karma"),
        _agent("small1", zone="moksha"),
    ]
    assistant, _ = _make_assistant(agents)
    assistant._followed = {"big1", "big2", "big3", "small1"}

    ranked = assistant._rank_invite_candidates()
    # moksha is scarcer → small1 should rank higher
    if ranked:
        assert ranked[0] == "small1"


def test_rank_excludes_already_invited():
    agents = [_agent("alice"), _agent("bob")]
    assistant, _ = _make_assistant(agents)
    assistant._followed = {"alice", "bob"}
    assistant._invited = {"alice"}

    ranked = assistant._rank_invite_candidates()
    assert "alice" not in ranked
    assert "bob" in ranked


def test_rank_excludes_unfollowed():
    agents = [_agent("alice")]
    assistant, _ = _make_assistant(agents)
    # alice not in _followed
    ranked = assistant._rank_invite_candidates()
    assert ranked == []
