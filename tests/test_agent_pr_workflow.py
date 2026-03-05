"""Agent PR Workflow Tests (7C) — agent mission execution + PR attribution.

Tests the 7C pipeline: mission routing → Cartridge process() → executor → PR
with agent attribution.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from city.heal_executor import FixResult, HealExecutor, PRResult


# ── Executor Agent Attribution (7C-2) ──────────────────────────────


def test_create_fix_pr_dry_run_with_agent_name():
    """7C-2: create_fix_pr includes agent_name in dry_run result."""
    executor = HealExecutor(_cwd=Path("/tmp"), _dry_run=True)
    fix = FixResult(
        contract_name="ruff_clean",
        success=True,
        action_taken="ruff_fix",
        files_changed=["city/foo.py"],
        message="fixed",
    )
    result = executor.create_fix_pr(fix, heartbeat_count=42, agent_name="sys_vyasa")
    assert result is not None
    assert result.success
    assert result.branch == "fix/ruff_clean_42"


def test_create_fix_pr_dry_run_without_agent_name():
    """7C-2: create_fix_pr works without agent_name (backward compat)."""
    executor = HealExecutor(_cwd=Path("/tmp"), _dry_run=True)
    fix = FixResult(
        contract_name="audit_clean",
        success=True,
        action_taken="cellular_heal",
        files_changed=["city/bar.py"],
        message="healed",
    )
    result = executor.create_fix_pr(fix, heartbeat_count=10)
    assert result is not None
    assert result.success


def test_create_fix_pr_returns_none_on_failure():
    """create_fix_pr returns None when fix was not successful."""
    executor = HealExecutor(_cwd=Path("/tmp"), _dry_run=True)
    fix = FixResult(
        contract_name="ruff_clean",
        success=False,
        action_taken="escalate",
    )
    assert executor.create_fix_pr(fix) is None


def test_create_fix_pr_returns_none_on_no_files():
    """create_fix_pr returns None when no files changed."""
    executor = HealExecutor(_cwd=Path("/tmp"), _dry_run=True)
    fix = FixResult(
        contract_name="ruff_clean",
        success=True,
        action_taken="ruff_fix",
        files_changed=[],
    )
    assert executor.create_fix_pr(fix) is None


# ── Mission Routing + Cartridge Integration (7C-1) ─────────────────


def test_record_pr_event_includes_agent_name():
    """7C-1: _record_pr_event stores agent_name in event dict."""
    from city.karma_handlers.sankalpa import _record_pr_event

    ctx = MagicMock()
    ctx.recent_events = []
    ctx.heartbeat_count = 5

    pr = MagicMock()
    pr.pr_url = "https://github.com/test/pr/1"
    pr.branch = "fix/test_1"
    pr.commit_hash = "abc123"

    _record_pr_event(ctx, 42, pr, agent_name="sys_kapila")

    assert len(ctx.recent_events) == 1
    event = ctx.recent_events[0]
    assert event["type"] == "pr_created"
    assert event["agent_name"] == "sys_kapila"
    assert event["issue_number"] == 42


def test_record_pr_event_defaults_to_mayor():
    """7C-1: _record_pr_event defaults agent_name to 'mayor'."""
    from city.karma_handlers.sankalpa import _record_pr_event

    ctx = MagicMock()
    ctx.recent_events = []
    ctx.heartbeat_count = 5

    pr = MagicMock()
    pr.pr_url = "https://github.com/test/pr/2"
    pr.branch = "fix/test_2"
    pr.commit_hash = "def456"

    _record_pr_event(ctx, 0, pr)

    event = ctx.recent_events[0]
    assert event["agent_name"] == "mayor"


# ── Mission Router Integration ─────────────────────────────────────


def test_route_mission_picks_best_agent():
    """Mission router picks agent with highest score."""
    from city.mission_router import route_mission

    specs = {
        "agent_a": {
            "capabilities": ["execute", "dispatch"],
            "capability_tier": "verified",
            "domain": "ENGINEERING",
            "capability_protocol": "infer",
            "qos": {"latency_multiplier": 1.0},
        },
        "agent_b": {
            "capabilities": ["observe"],
            "capability_tier": "observer",
            "domain": "DISCOVERY",
            "capability_protocol": "parse",
            "qos": {"latency_multiplier": 2.0},
        },
    }
    active = {"agent_a", "agent_b"}

    mission = MagicMock()
    mission.id = "exec_test_1"

    result = route_mission(mission, specs, active)
    assert result["agent_name"] == "agent_a"
    assert result["score"] > 0
    assert not result["blocked"]


def test_route_mission_blocked_when_no_capability():
    """Mission router blocks when no agent has required caps."""
    from city.mission_router import route_mission

    specs = {
        "agent_a": {
            "capabilities": ["observe"],
            "capability_tier": "observer",
            "domain": "DISCOVERY",
            "qos": {"latency_multiplier": 1.0},
        },
    }
    active = {"agent_a"}

    mission = MagicMock()
    mission.id = "exec_test_2"  # requires "execute" + verified tier

    result = route_mission(mission, specs, active)
    assert result["agent_name"] is None
    assert result["blocked"]
