"""HeartbeatObserver Tests — Self-observation + anomaly detection.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from city.heartbeat_observer import (
    DiscussionActivity,
    HeartbeatDiagnosis,
    HeartbeatObserver,
    RunInfo,
)


# ── HeartbeatDiagnosis Tests ─────────────────────────────────────────


class TestHeartbeatDiagnosis:
    def test_healthy_when_no_anomalies(self):
        diag = HeartbeatDiagnosis()
        assert diag.healthy is True

    def test_unhealthy_when_anomalies(self):
        diag = HeartbeatDiagnosis(anomalies=["something_bad"])
        assert diag.healthy is False

    def test_summary(self):
        diag = HeartbeatDiagnosis(
            recent_runs=[RunInfo("1", "success", 0, 0)],
            success_rate=1.0,
            discussions=[DiscussionActivity(1, "test", 10, "")],
        )
        s = diag.summary()
        assert "runs=1" in s
        assert "success=100%" in s
        assert "discussions=1" in s

    def test_summary_with_anomalies(self):
        diag = HeartbeatDiagnosis(
            recent_runs=[],
            anomalies=["heartbeat_gap: too old"],
        )
        s = diag.summary()
        assert "anomalies=1" in s


# ── Anomaly Detection Tests ──────────────────────────────────────────


class TestAnomalyDetection:
    def _make_observer(self):
        return HeartbeatObserver(
            _owner="test",
            _repo="test",
            _max_gap_minutes=45,
            _min_success_rate=0.7,
            _stale_discussion_hours=6.0,
        )

    def test_low_success_rate(self):
        obs = self._make_observer()
        diag = HeartbeatDiagnosis(
            recent_runs=[
                RunInfo("1", "failure", 0, 100),
                RunInfo("2", "failure", 0, 200),
                RunInfo("3", "failure", 0, 300),
                RunInfo("4", "success", 0, 400),
            ],
            success_rate=0.25,
        )
        obs._detect_anomalies(diag)
        assert any("heartbeat_failing" in a for a in diag.anomalies)

    def test_high_success_rate_no_anomaly(self):
        obs = self._make_observer()
        diag = HeartbeatDiagnosis(
            recent_runs=[
                RunInfo("1", "success", 0, 100),
                RunInfo("2", "success", 0, 200),
            ],
            success_rate=1.0,
        )
        obs._detect_anomalies(diag)
        assert not any("heartbeat_failing" in a for a in diag.anomalies)

    def test_heartbeat_gap(self):
        obs = self._make_observer()
        diag = HeartbeatDiagnosis(
            recent_runs=[RunInfo("1", "success", 0, 3600)],
            last_success_age_s=3600,  # 60 min > 45 min threshold
        )
        obs._detect_anomalies(diag)
        assert any("heartbeat_gap" in a for a in diag.anomalies)

    def test_no_gap_when_recent(self):
        obs = self._make_observer()
        diag = HeartbeatDiagnosis(
            recent_runs=[RunInfo("1", "success", 0, 600)],
            last_success_age_s=600,  # 10 min < 45 min threshold
        )
        obs._detect_anomalies(diag)
        assert not any("heartbeat_gap" in a for a in diag.anomalies)

    def test_crash_loop_detection(self):
        obs = self._make_observer()
        diag = HeartbeatDiagnosis(
            recent_runs=[
                RunInfo("1", "failure", 0, 100),
                RunInfo("2", "failure", 0, 200),
                RunInfo("3", "failure", 0, 300),
            ],
            success_rate=0.0,
        )
        obs._detect_anomalies(diag)
        assert any("crash_loop" in a for a in diag.anomalies)

    def test_no_crash_loop_with_mixed(self):
        obs = self._make_observer()
        diag = HeartbeatDiagnosis(
            recent_runs=[
                RunInfo("1", "success", 0, 100),
                RunInfo("2", "failure", 0, 200),
                RunInfo("3", "success", 0, 300),
            ],
            success_rate=0.67,
        )
        obs._detect_anomalies(diag)
        assert not any("crash_loop" in a for a in diag.anomalies)

    def test_stale_discussions(self):
        from datetime import datetime, timedelta, timezone

        obs = self._make_observer()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        diag = HeartbeatDiagnosis(
            last_discussion_update=old_time,
        )
        obs._detect_anomalies(diag)
        assert any("discussions_stale" in a for a in diag.anomalies)

    def test_fresh_discussions_no_anomaly(self):
        from datetime import datetime, timezone

        obs = self._make_observer()
        recent = datetime.now(timezone.utc).isoformat()
        diag = HeartbeatDiagnosis(
            last_discussion_update=recent,
        )
        obs._detect_anomalies(diag)
        assert not any("discussions_stale" in a for a in diag.anomalies)


# ── Observer Stats ───────────────────────────────────────────────────


class TestObserverStats:
    def test_stats(self):
        obs = HeartbeatObserver(_owner="foo", _repo="bar")
        s = obs.stats()
        assert s["owner"] == "foo"
        assert s["repo"] == "bar"


# ── Observer Hook Integration ────────────────────────────────────────


class TestObserverHook:
    def test_hook_skips_offline(self):
        from city.hooks.genesis.heartbeat_observer_hook import HeartbeatObserverHook

        hook = HeartbeatObserverHook()
        ctx = MagicMock()
        ctx.offline_mode = True
        assert hook.should_run(ctx) is False

    def test_hook_runs_online(self):
        from city.hooks.genesis.heartbeat_observer_hook import HeartbeatObserverHook

        hook = HeartbeatObserverHook()
        ctx = MagicMock()
        ctx.offline_mode = False
        assert hook.should_run(ctx) is True

    def test_hook_properties(self):
        from city.hooks.genesis.heartbeat_observer_hook import HeartbeatObserverHook

        hook = HeartbeatObserverHook()
        assert hook.name == "heartbeat_observer"
        assert hook.phase == "genesis"
        assert hook.priority == 5


# ── SystemHealthHook integration ─────────────────────────────────────


class TestSystemHealthObserverIntegration:
    def test_check_heartbeat_observer_no_diagnosis(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock(spec=[])  # no _heartbeat_diagnosis attribute
        issues = _check_heartbeat_observer(ctx)
        assert issues == []

    def test_check_heartbeat_observer_healthy(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = HeartbeatDiagnosis()
        issues = _check_heartbeat_observer(ctx)
        assert issues == []

    def test_check_heartbeat_observer_anomalies(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = HeartbeatDiagnosis(
            anomalies=["heartbeat_crash_loop: 3+ consecutive failures"],
            success_rate=0.0,
            recent_runs=[RunInfo("1", "failure", 0, 100)],
            total_comments=200,
        )
        issues = _check_heartbeat_observer(ctx)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert "crash_loop" in issues[0]["signal"]

    def test_warning_severity_for_gap(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = HeartbeatDiagnosis(
            anomalies=["heartbeat_gap: last success was 60min ago"],
        )
        issues = _check_heartbeat_observer(ctx)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
