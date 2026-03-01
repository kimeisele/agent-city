"""
Tests for R2: GhRateLimiter — Sliding window + backoff for gh CLI.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.gh_rate import GhRateLimiter


def test_window_enforcement():
    """Calls exceeding max_per_minute are throttled."""
    limiter = GhRateLimiter(max_per_minute=3)

    results = []
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        for _ in range(5):
            results.append(limiter.call(["pr", "list"]))

    # First 3 succeed, last 2 throttled
    assert results[:3] == ["ok", "ok", "ok"]
    assert results[3] is None
    assert results[4] is None
    assert limiter._throttled_calls == 2


def test_backoff_on_rate_limit():
    """403/429 triggers exponential backoff."""
    limiter = GhRateLimiter(max_per_minute=10)

    with patch("subprocess.run") as mock_run:
        # First call: 403 rate limit
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="403 rate limit exceeded")
        result1 = limiter.call(["pr", "list"])
        assert result1 is None
        assert limiter._backoff_step == 1

        # Second call: should be blocked by backoff
        result2 = limiter.call(["pr", "list"])
        assert result2 is None
        assert limiter._throttled_calls == 1  # Blocked by backoff, not window


def test_gajendra_pr_check_interval():
    """In GAJENDRA mode (5Hz), PRs checked every N heartbeats only."""
    limiter = GhRateLimiter()

    # SAMADHI (0.5Hz) — always check
    assert limiter.should_check_prs(1, 0.5) is True
    assert limiter.should_check_prs(2, 0.5) is True

    # SADHANA (1.0Hz) — always check
    assert limiter.should_check_prs(1, 1.0) is True

    # GAJENDRA (5.0Hz) — check only every 10
    assert limiter.should_check_prs(10, 5.0) is True
    assert limiter.should_check_prs(20, 5.0) is True
    assert limiter.should_check_prs(7, 5.0) is False
    assert limiter.should_check_prs(13, 5.0) is False


def test_passthrough_samadhi():
    """In SAMADHI, all calls pass through (within window)."""
    limiter = GhRateLimiter(max_per_minute=30)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="success", stderr="")
        for i in range(10):
            result = limiter.call(["pr", "checks", str(i)])
            assert result == "success"

    assert limiter._total_calls == 10
    assert limiter._throttled_calls == 0


def test_stats():
    """stats() reports correct metrics."""
    limiter = GhRateLimiter(max_per_minute=5)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        limiter.call(["pr", "list"])
        limiter.call(["pr", "list"])

    s = limiter.stats()
    assert s["total_calls"] == 2
    assert s["calls_in_window"] == 2
    assert s["max_per_minute"] == 5
    assert s["backoff_active"] is False


if __name__ == "__main__":
    test_window_enforcement()
    test_backoff_on_rate_limit()
    test_gajendra_pr_check_interval()
    test_passthrough_samadhi()
    test_stats()
    print("All 5 GhRateLimiter tests passed.")
