"""Moltbook ↔ Agent City Viral Loop Tests (7B).

Tests engagement prana, agent-attributed posts, cross-posting.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from city.moltbook_bridge import MoltbookBridge


# ── 7B-1: Engagement Prana ─────────────────────────────────────────


def test_award_prana_basic(tmp_path):
    """7B-1: award_prana grants prana and records event."""
    from city.pokedex import Pokedex

    db = tmp_path / "test.db"
    pdx = Pokedex(str(db))
    pdx.discover("test_agent")

    # Get initial prana via cell
    cell_before = pdx.get_cell("test_agent")
    initial_prana = cell_before.prana

    pdx.award_prana("test_agent", 25, source="moltbook:test")

    cell_after = pdx.get_cell("test_agent")
    assert cell_after.prana >= initial_prana + 25


def test_award_prana_rejects_non_positive(tmp_path):
    """7B-1: award_prana rejects zero/negative amounts."""
    from city.pokedex import Pokedex

    db = tmp_path / "test.db"
    pdx = Pokedex(str(db))
    pdx.discover("test_agent")

    with pytest.raises(ValueError, match="positive"):
        pdx.award_prana("test_agent", 0)

    with pytest.raises(ValueError, match="positive"):
        pdx.award_prana("test_agent", -5)


def test_award_prana_unknown_agent(tmp_path):
    """7B-1: award_prana raises for unknown agent."""
    from city.pokedex import Pokedex

    db = tmp_path / "test.db"
    pdx = Pokedex(str(db))

    with pytest.raises((ValueError, KeyError)):
        pdx.award_prana("nonexistent", 10)


def test_award_prana_event_recorded(tmp_path):
    """7B-1: award_prana records event in ledger."""
    from city.pokedex import Pokedex

    db = tmp_path / "test.db"
    pdx = Pokedex(str(db))
    pdx.discover("test_agent")

    pdx.award_prana("test_agent", 15, source="moltbook:submolt_post:abc123")

    events = pdx.get_events("test_agent")
    award_events = [e for e in events if e.get("event_type") == "prana_award"]
    assert len(award_events) >= 1
    last = award_events[-1]
    assert "moltbook" in last.get("details", "")


# ── 7B-2: Agent-Attributed Moltbook Posts ──────────────────────────


def test_post_agent_update_basic():
    """7B-2: post_agent_update creates agent-attributed post."""
    client = MagicMock()
    bridge = MoltbookBridge(
        _client=client,
        _post_cooldown_s=0,  # no cooldown for test
    )

    result = bridge.post_agent_update(
        agent_name="sys_vyasa",
        action="healed ruff_clean",
        detail="Fixed 3 lint errors",
        pr_url="https://github.com/test/pr/1",
    )

    assert result is True
    client.sync_create_post.assert_called_once()
    call_args = client.sync_create_post.call_args
    title = call_args[0][0] if call_args[0] else call_args[1].get("title", "")
    assert "sys_vyasa" in title
    assert "healed" in title


def test_post_agent_update_rate_limited():
    """7B-2: post_agent_update respects cooldown."""
    client = MagicMock()
    bridge = MoltbookBridge(
        _client=client,
        _post_cooldown_s=3600,
        _last_post_time=time.time(),  # just posted
    )

    result = bridge.post_agent_update(
        agent_name="sys_kapila",
        action="responded to discussion #42",
    )

    assert result is False
    client.sync_create_post.assert_not_called()


# ── 7B-3: Cross-Post Wiring ───────────────────────────────────────


def test_moltbook_bridge_has_post_agent_update():
    """7B-3: MoltbookBridge exposes post_agent_update method."""
    assert hasattr(MoltbookBridge, "post_agent_update")
    client = MagicMock()
    bridge = MoltbookBridge(_client=client)
    assert callable(bridge.post_agent_update)


def test_post_agent_update_handles_failure_gracefully():
    """7B-3: post_agent_update returns False on client error."""
    client = MagicMock()
    client.sync_create_post.side_effect = Exception("network error")
    bridge = MoltbookBridge(
        _client=client,
        _post_cooldown_s=0,
    )

    result = bridge.post_agent_update(
        agent_name="sys_narada",
        action="proposed governance change",
    )

    assert result is False
