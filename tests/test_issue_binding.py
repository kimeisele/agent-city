"""
Tests for D1: Issue Binding Protocol — IssueDirective lifecycle.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.issues import CityIssueManager, IssueDirective, IssueType


def test_issue_directive_frozen():
    """IssueDirective is a frozen dataclass."""
    d = IssueDirective(
        issue_number=42,
        title="Fix CI",
        action="intent_needed",
        reason="low_prana",
        issue_type=IssueType.ITERATIVE,
        prana=500,
    )
    assert d.issue_number == 42
    assert d.action == "intent_needed"
    assert d.mission_id == ""
    # Frozen — cannot mutate
    try:
        d.prana = 100  # type: ignore[misc]
        assert False, "Should raise FrozenInstanceError"
    except AttributeError:
        pass


def test_issue_directive_with_mission_id():
    """IssueDirective can carry a bound mission_id."""
    d = IssueDirective(
        issue_number=7,
        title="Audit ruff",
        action="contract_check",
        reason="audit_needed",
        issue_type=IssueType.CONTRACT,
        prana=800,
        mission_id="issue_7_42",
    )
    assert d.mission_id == "issue_7_42"


def test_bind_mission():
    """bind_mission() links an issue to a mission."""
    mgr = CityIssueManager()
    # Simulate a directive in _last_directives
    d = IssueDirective(
        issue_number=10,
        title="Test issue",
        action="intent_needed",
        reason="low_prana",
        issue_type=IssueType.ITERATIVE,
        prana=300,
    )
    mgr._last_directives = [d]

    result = mgr.bind_mission(10, "issue_10_5")
    assert result is not None
    assert result.mission_id == "issue_10_5"
    assert result.issue_number == 10
    assert mgr._bound_missions[10] == "issue_10_5"


def test_bind_mission_unknown_issue():
    """bind_mission() returns None for unknown issue number."""
    mgr = CityIssueManager()
    mgr._last_directives = []
    assert mgr.bind_mission(999, "mission_x") is None


def test_resolve_issue():
    """resolve_issue() closes the loop for a bound mission."""
    mgr = CityIssueManager()
    mgr._bound_missions[42] = "issue_42_10"

    assert mgr.resolve_issue(42, "issue_42_10") is True
    assert 42 not in mgr._bound_missions


def test_resolve_issue_mismatch():
    """resolve_issue() rejects if mission_id doesn't match."""
    mgr = CityIssueManager()
    mgr._bound_missions[42] = "issue_42_10"

    assert mgr.resolve_issue(42, "wrong_mission") is False
    assert 42 in mgr._bound_missions  # Not removed


def test_issue_open_and_bound_helpers():
    """Issue manager exposes read-only helpers for campaign dedupe."""
    mgr = CityIssueManager()
    mgr._issue_cells[42] = object()
    mgr._bound_missions[42] = "issue_42_10"

    assert mgr.is_issue_open(42) is True
    assert mgr.is_issue_open(99) is False
    assert mgr.get_bound_mission(42) == "issue_42_10"
    assert mgr.get_bound_mission(99) is None


if __name__ == "__main__":
    test_issue_directive_frozen()
    test_issue_directive_with_mission_id()
    test_bind_mission()
    test_bind_mission_unknown_issue()
    test_resolve_issue()
    test_resolve_issue_mismatch()
    print("All 6 issue binding tests passed.")
