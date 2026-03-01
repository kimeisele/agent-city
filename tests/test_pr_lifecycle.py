"""
Tests for D5: PR Lifecycle Manager — track, check, auto-merge, stale.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.pr_lifecycle import PRLifecycleManager, PRRecord


def test_track_pr():
    """track() stores a PRRecord."""
    mgr = PRLifecycleManager(_dry_run=True)
    record = mgr.track(
        pr_url="https://github.com/test/repo/pull/1",
        branch="fix/ruff_clean_5",
        contract_name="ruff_clean",
        heartbeat=5,
    )
    assert record.status == "open"
    assert record.contract_name == "ruff_clean"
    assert mgr.stats()["total_tracked"] == 1


def test_pr_record_serialization():
    """PRRecord round-trips through dict."""
    record = PRRecord(
        pr_url="https://github.com/test/repo/pull/2",
        branch="fix/audit_clean_10",
        contract_name="audit_clean",
        created_at_heartbeat=10,
        status="merged",
        checks_passed=True,
    )
    d = record.to_dict()
    restored = PRRecord.from_dict(d)
    assert restored.pr_url == record.pr_url
    assert restored.status == "merged"
    assert restored.checks_passed is True


def test_stale_pr_detection():
    """check_all() marks old open PRs as stale."""
    mgr = PRLifecycleManager(_dry_run=True)
    mgr.track("https://github.com/test/repo/pull/3", "fix/x_1", "ruff_clean", heartbeat=1)

    # 50 heartbeats later (> 40 stale threshold)
    changes = mgr.check_all(current_heartbeat=50)
    assert len(changes) == 1
    assert changes[0]["action"] == "closed_stale"
    assert mgr._records["https://github.com/test/repo/pull/3"].status == "stale"


def test_stats_by_status():
    """stats() groups PRs by status."""
    mgr = PRLifecycleManager(_dry_run=True)
    mgr.track("url1", "b1", "c1", 1)
    mgr.track("url2", "b2", "c2", 2)
    mgr._records["url2"].status = "merged"

    stats = mgr.stats()
    assert stats["by_status"]["open"] == 1
    assert stats["by_status"]["merged"] == 1


def test_non_stale_pr_not_touched():
    """Recent PRs are not closed in dry_run mode."""
    mgr = PRLifecycleManager(_dry_run=True)
    mgr.track("url_recent", "branch", "ruff_clean", heartbeat=10)

    changes = mgr.check_all(current_heartbeat=15)
    assert len(changes) == 0
    assert mgr._records["url_recent"].status == "open"


if __name__ == "__main__":
    test_track_pr()
    test_pr_record_serialization()
    test_stale_pr_detection()
    test_stats_by_status()
    test_non_stale_pr_not_touched()
    print("All 5 PR lifecycle tests passed.")
