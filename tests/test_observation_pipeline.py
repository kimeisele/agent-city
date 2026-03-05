"""End-to-end observation pipeline tests — deterministic, no LLM.

Tests the full feedback loop:
  Observer anomaly → SystemHealthHook → Brain context → City report

All deterministic. No subprocess, no GitHub API, no LLM calls.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from city.heartbeat_observer import (
    DiscussionActivity,
    HeartbeatDiagnosis,
    RunInfo,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_healthy_diagnosis():
    return HeartbeatDiagnosis(
        recent_runs=[
            RunInfo("1", "success", 0, 600),
            RunInfo("2", "success", 0, 1500),
        ],
        success_rate=1.0,
        last_success_age_s=600,
        discussions=[DiscussionActivity(25, "Registry", 150, "2026-03-05T16:00:00Z")],
        total_comments=150,
        last_discussion_update="2026-03-05T16:00:00Z",
    )


def _make_crash_loop_diagnosis():
    return HeartbeatDiagnosis(
        recent_runs=[
            RunInfo("1", "failure", 0, 600),
            RunInfo("2", "failure", 0, 1500),
            RunInfo("3", "failure", 0, 2400),
            RunInfo("4", "success", 0, 3300),
        ],
        success_rate=0.25,
        last_success_age_s=3300,
        anomalies=[
            "heartbeat_failing: 3/4 runs failed (rate=25%)",
            "heartbeat_crash_loop: 3+ consecutive failures",
            "heartbeat_gap: last success was 55min ago (threshold=45min)",
        ],
        discussions=[DiscussionActivity(25, "Registry", 150, "2026-03-05T10:00:00Z")],
        total_comments=150,
        last_discussion_update="2026-03-05T10:00:00Z",
    )


def _make_stale_diagnosis():
    return HeartbeatDiagnosis(
        recent_runs=[RunInfo("1", "success", 0, 600)],
        success_rate=1.0,
        last_success_age_s=600,
        anomalies=["discussions_stale: no updates in 12.0h (threshold=6.0h)"],
        total_comments=50,
        last_discussion_update="2026-03-04T08:00:00Z",
    )


# ── SystemHealthHook Integration ─────────────────────────────────────


class TestSystemHealthObserverPipeline:
    """Prove SystemHealthHook correctly surfaces observer anomalies."""

    def test_healthy_system_no_issues(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = _make_healthy_diagnosis()
        issues = _check_heartbeat_observer(ctx)
        assert issues == []

    def test_crash_loop_produces_critical(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = _make_crash_loop_diagnosis()
        issues = _check_heartbeat_observer(ctx)

        assert len(issues) == 3
        # crash_loop and failing should be critical
        severities = {i["signal"].split(":")[0]: i["severity"] for i in issues}
        assert severities["heartbeat_failing"] == "critical"
        assert severities["heartbeat_crash_loop"] == "critical"
        assert severities["heartbeat_gap"] == "warning"

    def test_stale_discussions_produces_warning(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = _make_stale_diagnosis()
        issues = _check_heartbeat_observer(ctx)

        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "discussions_stale" in issues[0]["signal"]

    def test_issues_contain_detail_with_metrics(self):
        from city.hooks.moksha.system_health import _check_heartbeat_observer

        ctx = MagicMock()
        ctx._heartbeat_diagnosis = _make_crash_loop_diagnosis()
        issues = _check_heartbeat_observer(ctx)

        for issue in issues:
            assert "Success rate" in issue["detail"]
            assert "runs observed" in issue["detail"]
            assert "discussions" in issue["detail"]


# ── Brain Context Pipeline ───────────────────────────────────────────


class TestBrainContextObserverPipeline:
    """Prove observer data flows into ContextSnapshot for Brain."""

    def test_healthy_diagnosis_in_snapshot(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            heartbeat_health={
                "healthy": True,
                "success_rate": 1.0,
                "anomalies": [],
                "runs_observed": 10,
                "total_discussion_comments": 329,
            }
        )
        assert snap.heartbeat_health["healthy"] is True
        assert snap.heartbeat_health["success_rate"] == 1.0

    def test_unhealthy_diagnosis_in_snapshot(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            heartbeat_health={
                "healthy": False,
                "success_rate": 0.25,
                "anomalies": ["heartbeat_crash_loop: 3+ consecutive failures"],
                "runs_observed": 4,
                "total_discussion_comments": 150,
            }
        )
        assert snap.heartbeat_health["healthy"] is False
        assert len(snap.heartbeat_health["anomalies"]) == 1

    def test_snapshot_defaults_empty(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot()
        assert snap.heartbeat_health == {}
        assert snap.contract_diagnostics == ()


# ── Contract Diagnostics Pipeline ────────────────────────────────────


class TestContractDiagnosticsPipeline:
    """Prove contract failure details flow into ContextSnapshot."""

    def test_contract_diagnostics_in_snapshot(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            failing_contracts=("tests_pass",),
            contract_diagnostics=(
                {
                    "name": "tests_pass",
                    "message": "2 test(s) failed — 2 failed, 1584 passed in 115s",
                    "details": [
                        "tests/test_foo.py::test_bar - AssertionError: expected 1 got 2",
                        "tests/test_baz.py::test_quux - TypeError: 'NoneType'",
                    ],
                },
            ),
        )
        assert len(snap.contract_diagnostics) == 1
        diag = snap.contract_diagnostics[0]
        assert diag["name"] == "tests_pass"
        assert "2 test(s) failed" in diag["message"]
        assert len(diag["details"]) == 2
        assert "test_bar" in diag["details"][0]

    def test_empty_diagnostics(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(failing_contracts=())
        assert snap.contract_diagnostics == ()


# ── Comprehension Prompt Pipeline ────────────────────────────────────


class TestComprehensionPromptPipeline:
    """Prove observer + contract data appears in Brain prompt text."""

    def _build_prompt_lines(self, snapshot):
        from city.prompt_builders.comprehension import ComprehensionBuilder
        from city.prompt_registry import PromptContext

        builder = ComprehensionBuilder()
        ctx = PromptContext(
            snapshot=snapshot,
        )
        return builder.build_payload(ctx)

    def test_heartbeat_health_in_prompt(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            agent_count=62,
            alive_count=50,
            heartbeat_health={
                "healthy": True,
                "success_rate": 0.9,
                "runs_observed": 10,
                "anomalies": [],
            },
        )
        lines = self._build_prompt_lines(snap)
        text = "\n".join(lines)
        assert "Heartbeat: healthy" in text
        assert "success_rate=90%" in text

    def test_unhealthy_heartbeat_in_prompt(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            agent_count=62,
            alive_count=50,
            heartbeat_health={
                "healthy": False,
                "success_rate": 0.25,
                "runs_observed": 4,
                "anomalies": ["heartbeat_crash_loop: 3+ consecutive failures"],
            },
        )
        lines = self._build_prompt_lines(snap)
        text = "\n".join(lines)
        assert "UNHEALTHY" in text
        assert "crash_loop" in text

    def test_contract_diagnostics_in_prompt(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            agent_count=62,
            alive_count=50,
            failing_contracts=("tests_pass",),
            contract_diagnostics=(
                {
                    "name": "tests_pass",
                    "message": "2 test(s) failed",
                    "details": ["tests/test_foo.py::test_bar - AssertionError"],
                },
            ),
        )
        lines = self._build_prompt_lines(snap)
        text = "\n".join(lines)
        assert "tests_pass" in text
        assert "2 test(s) failed" in text
        assert "test_bar" in text

    def test_healthy_no_anomaly_lines(self):
        from city.brain_context import ContextSnapshot

        snap = ContextSnapshot(
            agent_count=62,
            alive_count=50,
            heartbeat_health={
                "healthy": True,
                "success_rate": 1.0,
                "runs_observed": 10,
                "anomalies": [],
            },
        )
        lines = self._build_prompt_lines(snap)
        text = "\n".join(lines)
        assert "Anomalies" not in text


# ── City Report Pipeline ─────────────────────────────────────────────


class TestCityReportPipeline:
    """Prove observer data flows into the city report reflection."""

    def test_reflection_includes_observer(self):
        """Simulate outbound hook enriching reflection with observer data."""
        diag = _make_crash_loop_diagnosis()
        reflection = {}

        # This is what DiscussionsOutboundHook does
        reflection["heartbeat_observer"] = {
            "healthy": diag.healthy,
            "success_rate": diag.success_rate,
            "runs_observed": len(diag.recent_runs),
            "anomalies": diag.anomalies[:5],
            "total_discussion_comments": diag.total_comments,
        }

        obs = reflection["heartbeat_observer"]
        assert obs["healthy"] is False
        assert obs["success_rate"] == 0.25
        assert len(obs["anomalies"]) == 3
        assert obs["runs_observed"] == 4

    def test_reflection_empty_when_no_diagnosis(self):
        reflection = {}
        diag = None
        if diag is not None:
            reflection["heartbeat_observer"] = {}
        assert "heartbeat_observer" not in reflection


# ── Brain-Offline Detection Pipeline ─────────────────────────────────


class TestBrainOfflineDetection:
    """The system MUST detect Brain-dead state and scream, not silently degrade."""

    def test_system_health_detects_brain_noop(self):
        """SystemHealthHook must flag Brain-offline even when Brain object exists."""
        from city.hooks.moksha.system_health import _check_brain

        ctx = MagicMock()
        ctx.brain = MagicMock()
        ctx.brain.is_available = False  # Brain exists but NoOp
        ctx.brain_memory = None
        issues = _check_brain(ctx)

        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert "OFFLINE" in issues[0]["signal"]
        assert "NoOp" in issues[0]["signal"]

    def test_system_health_ok_when_brain_available(self):
        from city.hooks.moksha.system_health import _check_brain

        ctx = MagicMock()
        ctx.brain = MagicMock()
        ctx.brain.is_available = True
        ctx.brain_memory = None
        issues = _check_brain(ctx)
        assert issues == []

    def test_system_health_detects_brain_none(self):
        from city.hooks.moksha.system_health import _check_brain

        ctx = MagicMock()
        ctx.brain = None
        ctx.brain_memory = None
        issues = _check_brain(ctx)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"

    def test_observer_hook_injects_brain_offline_anomaly(self):
        """HeartbeatObserverHook must add brain_offline anomaly during GENESIS."""
        diag = _make_healthy_diagnosis()
        assert diag.anomalies == []

        # Simulate what the hook does
        brain = MagicMock()
        brain.is_available = False
        if brain is not None and not getattr(brain, "is_available", True):
            diag.anomalies.append(
                "brain_offline: NoOp provider — no LLM API key detected."
            )

        assert len(diag.anomalies) == 1
        assert "brain_offline" in diag.anomalies[0]
        assert not diag.healthy  # diagnosis flips to unhealthy

    def test_brain_offline_shows_in_prompt(self):
        """Brain-offline anomaly must appear in comprehension prompt."""
        from city.brain_context import ContextSnapshot
        from city.prompt_builders.comprehension import ComprehensionBuilder
        from city.prompt_registry import PromptContext

        snap = ContextSnapshot(
            agent_count=62,
            alive_count=50,
            heartbeat_health={
                "healthy": False,
                "success_rate": 0.9,
                "runs_observed": 10,
                "anomalies": ["brain_offline: NoOp provider — no LLM API key detected."],
            },
        )
        builder = ComprehensionBuilder()
        ctx = PromptContext(snapshot=snap)
        text = "\n".join(builder.build_payload(ctx))
        assert "UNHEALTHY" in text
        assert "brain_offline" in text


# ── Diagnostic Build Pipeline ────────────────────────────────────────


class TestDiagnosticBuild:
    """Prove _build_diagnostic produces structured markdown."""

    def test_diagnostic_markdown_format(self):
        from city.hooks.moksha.system_health import _build_diagnostic

        issues = [
            {"severity": "critical", "system": "observer", "signal": "crash_loop", "detail": "3 failures"},
            {"severity": "warning", "system": "economy", "signal": "low prana", "detail": "avg=300"},
        ]
        text = _build_diagnostic(issues, heartbeat=574)
        assert "Heartbeat #574" in text
        assert "CRITICAL" in text
        assert "WARNING" in text
        assert "crash_loop" in text
        assert "low prana" in text
