"""
Tests for Brain Gates — deterministic Python harness around Brain outputs.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from city.brain_context import ContextSnapshot
from city.brain_digest import digest_thread_state, render_field_summary
from city.brain_gates import (
    RepetitionVerdict,
    _extract_hint_verb,
    check_grounding,
    check_repetition,
    pending_brain_missions,
    terminal_brain_missions,
)


# ── Helper: fake BrainMemory ────────────────────────────────────────


class FakeMemory:
    """Minimal BrainMemory stub for gate tests."""

    def __init__(self, entries: list[dict] | None = None):
        self._entries = entries or []

    def recent(self, n: int = 6) -> list[dict]:
        return self._entries[-n:]


def _entry(action_hint: str = "", confidence: float = 0.5) -> dict:
    """Build a minimal BrainMemory entry dict."""
    thought: dict = {"confidence": confidence}
    if action_hint:
        thought["action_hint"] = action_hint
    return {"thought": thought, "heartbeat": 1, "posted": True}


# ── _extract_hint_verb ──────────────────────────────────────────────


class TestExtractHintVerb:
    def test_empty(self):
        assert _extract_hint_verb("") == ""

    def test_bare_verb(self):
        assert _extract_hint_verb("escalate") == "escalate"

    def test_verb_with_target(self):
        assert _extract_hint_verb("flag_bottleneck:engineering") == "flag_bottleneck"

    def test_verb_with_multi_colon(self):
        assert _extract_hint_verb("assign_agent:bot:task") == "assign_agent"


# ── check_repetition ───────────────────────────────────────────────


class TestRepetitionGate:
    def test_no_memory_passes(self):
        verdict = check_repetition("flag_bottleneck:x", None)
        assert verdict.should_post is True
        assert verdict.repeat_count == 0

    def test_empty_hint_passes(self):
        verdict = check_repetition("", FakeMemory())
        assert verdict.should_post is True

    def test_below_threshold_passes(self):
        mem = FakeMemory([
            _entry("flag_bottleneck:eng"),
            _entry("flag_bottleneck:eng"),
            _entry("investigate:api"),
        ])
        verdict = check_repetition("flag_bottleneck:eng", mem)
        assert verdict.should_post is True
        assert verdict.repeat_count == 2

    def test_at_threshold_escalates(self):
        mem = FakeMemory([
            _entry("flag_bottleneck:eng"),
            _entry("flag_bottleneck:eng"),
            _entry("flag_bottleneck:eng"),
        ])
        verdict = check_repetition("flag_bottleneck:eng", mem)
        assert verdict.should_post is True
        assert verdict.escalated_hint == "escalate:eng"
        assert verdict.repeat_count == 3
        assert "auto-escalated" in verdict.reason

    def test_non_escalatable_suppresses(self):
        mem = FakeMemory([
            _entry("escalate:eng"),
            _entry("escalate:eng"),
            _entry("escalate:eng"),
        ])
        verdict = check_repetition("escalate:eng", mem)
        assert verdict.should_post is False
        assert verdict.repeat_count == 3
        assert "suppressed" in verdict.reason

    def test_custom_threshold(self):
        mem = FakeMemory([_entry("flag_bottleneck:x")])
        verdict = check_repetition("flag_bottleneck:x", mem, threshold=1)
        assert verdict.should_post is True  # escalation
        assert verdict.escalated_hint == "escalate:x"

    def test_investigate_escalates(self):
        mem = FakeMemory([
            _entry("investigate:api"),
            _entry("investigate:api"),
            _entry("investigate:api"),
        ])
        verdict = check_repetition("investigate:api", mem)
        assert verdict.should_post is True
        assert verdict.escalated_hint == "escalate:api"

    def test_mixed_verbs_no_false_positive(self):
        mem = FakeMemory([
            _entry("flag_bottleneck:eng"),
            _entry("investigate:api"),
            _entry("check_health:sys"),
            _entry("flag_bottleneck:eng"),
        ])
        verdict = check_repetition("flag_bottleneck:eng", mem)
        assert verdict.should_post is True
        assert verdict.repeat_count == 2

    def test_bare_verb_escalation(self):
        """Bare verb without target should escalate to bare verb."""
        mem = FakeMemory([
            _entry("check_health"),
            _entry("check_health"),
            _entry("check_health"),
        ])
        verdict = check_repetition("check_health", mem)
        assert verdict.should_post is True
        assert verdict.escalated_hint == "escalate"


# ── pending_brain_missions ──────────────────────────────────────────


class TestPendingBrainMissions:
    def test_no_sankalpa(self):
        ctx = MagicMock()
        ctx.sankalpa = None
        assert pending_brain_missions(ctx) == []

    def test_filters_brain_prefix(self):
        m1 = MagicMock()
        m1.id = "brain_fix_api"
        m1.name = "Fix API"
        m1.status.value = "active"
        m1.owner = "sys_vyasa"
        m1.source = ""

        m2 = MagicMock()
        m2.id = "manual_deploy"
        m2.name = "Deploy"
        m2.status.value = "active"
        m2.owner = "human"
        m2.source = ""

        ctx = MagicMock()
        ctx.sankalpa.registry.get_active_missions.return_value = [m1, m2]
        result = pending_brain_missions(ctx)
        assert len(result) == 1
        assert result[0]["id"] == "brain_fix_api"

    def test_filters_brain_source(self):
        m1 = MagicMock()
        m1.id = "mission_42"
        m1.name = "Check latency"
        m1.status.value = "active"
        m1.owner = "sys_vyasa"
        m1.source = "brain"

        ctx = MagicMock()
        ctx.sankalpa.registry.get_active_missions.return_value = [m1]
        result = pending_brain_missions(ctx)
        assert len(result) == 1
        assert result[0]["id"] == "mission_42"


# ── terminal_brain_missions ─────────────────────────────────────────


class TestTerminalBrainMissions:
    def test_no_sankalpa(self):
        ctx = MagicMock()
        ctx.sankalpa = None
        assert terminal_brain_missions(ctx) == []

    def test_collects_terminal_brain_missions(self):
        m1 = MagicMock()
        m1.id = "brain_fix_api"
        m1.name = "Fix API"
        m1.status.value = "completed"
        m1.owner = "sys_vyasa"
        m1.source = "brain"
        m1.result = {"pr_number": 42}

        m2 = MagicMock()
        m2.id = "manual_deploy"
        m2.name = "Deploy"
        m2.status.value = "completed"
        m2.owner = "human"
        m2.source = ""

        ctx = MagicMock()
        ctx.sankalpa.registry.get_terminal_missions.return_value = [m1, m2]
        result = terminal_brain_missions(ctx)
        assert len(result) == 1
        assert result[0]["id"] == "brain_fix_api"
        assert result[0]["result"] == {"pr_number": 42}

    def test_fallback_to_get_all_missions(self):
        m1 = MagicMock()
        m1.id = "brain_scan"
        m1.name = "Scan"
        m1.status = "completed"
        m1.owner = "bot"
        m1.source = "brain"
        m1.result = None

        ctx = MagicMock()
        ctx.sankalpa.registry.get_active_missions.return_value = []
        # No get_terminal_missions, but has get_all_missions
        del ctx.sankalpa.registry.get_terminal_missions
        ctx.sankalpa.registry.get_all_missions.return_value = [m1]
        result = terminal_brain_missions(ctx)
        assert len(result) == 1
        assert result[0]["status"] == "completed"


# ── check_grounding ─────────────────────────────────────────────────


class TestGroundingGate:
    """Grounding Gate: event claims must trace to generation-time evidence."""

    def _unresponsive_cell(self):
        # Reproduces the #137 scenario: thread #26, 5 human / 0 agent / unresolved
        return digest_thread_state(26, "open", 0.5, 5, 0, True)

    def test_traceable_digest_echo_passes(self):
        cell = self._unresponsive_cell()
        text = (
            "Thread 26 shows unresponsive_thread: human_comments=5, "
            "agent_responses=0, energy=0.5, unresolved=True. It needs attention."
        )
        verdict = check_grounding(text, cells=[cell], heartbeat=726)
        assert verdict.grounded

    def test_fabricated_crisis_claim_suppressed(self):
        # economy_collapsed is not in the generation-time evidence
        cell = self._unresponsive_cell()
        text = "A severe crisis: economy_collapsed with total_prana=0."
        verdict = check_grounding(text, cells=[cell], heartbeat=726)
        assert not verdict.grounded
        assert "economy_collapsed" in verdict.untraceable_claims

    def test_fabricated_metric_values_suppressed(self):
        cell = self._unresponsive_cell()
        text = "Thread 26 shows human_comments=99, agent_responses=42."
        verdict = check_grounding(text, cells=[cell], heartbeat=726)
        assert not verdict.grounded
        assert "human_comments=99" in verdict.untraceable_claims

    def test_natural_language_phrases_pass(self):
        cell = self._unresponsive_cell()
        text = "Thread 26 has 5 human comments with 0 agent responses and remains unresolved."
        verdict = check_grounding(text, cells=[cell], heartbeat=726)
        assert verdict.grounded

    def test_vague_prose_without_claims_passes(self):
        cell = self._unresponsive_cell()
        text = "The city continues its steady rotation. Governance remains calm."
        verdict = check_grounding(text, cells=[cell], heartbeat=726)
        assert verdict.grounded

    def test_snapshot_evidence_passes(self):
        snapshot = ContextSnapshot(agent_count=51, alive_count=48, dead_count=3, chain_valid=True)
        text = "The city is healthy: 48 agents alive, chain_valid=True."
        verdict = check_grounding(text, snapshot=snapshot, heartbeat=726)
        assert verdict.grounded

    def test_snapshot_contradiction_suppressed(self):
        snapshot = ContextSnapshot(agent_count=51, alive_count=48, dead_count=3, chain_valid=True)
        text = "chain_valid=False, the ledger is corrupt and only 5 agents alive."
        verdict = check_grounding(text, snapshot=snapshot, heartbeat=726)
        assert not verdict.grounded
        assert "chain_valid=False" in verdict.untraceable_claims

    def test_field_digest_evidence_passes(self):
        # Critique path: the FIELD DIGEST rendered for the LLM is the evidence
        cell = self._unresponsive_cell()
        summary = render_field_summary([cell], max_chars=2000)
        text = "Found unresponsive_thread(5 human, 0 agent) in thread 26."
        verdict = check_grounding(text, field_summary=summary, heartbeat=726)
        assert verdict.grounded

    def test_city_stats_evidence_passes(self):
        stats = {"total": 51, "active": 20, "citizen": 28, "new_citizens": 5}
        events = ["5 new citizens joined through immigration"]
        extra = {
            "events": events,
            "agent_count": stats.get("total", 0),
            "alive_count": stats.get("active", 0) + stats.get("citizen", 0),
        }
        text = "5 new citizens joined. Population: 51. 48 agents alive."
        verdict = check_grounding(text, city_stats=stats, heartbeat=100, extra=extra)
        assert verdict.grounded

    def test_city_stats_fabrication_suppressed(self):
        stats = {"total": 51, "active": 20, "citizen": 28}
        text = "The economy collapsed and 900 agents died this cycle."
        verdict = check_grounding(text, city_stats=stats, heartbeat=100)
        assert not verdict.grounded
        assert "economy_collapsed" in verdict.untraceable_claims

    def test_population_alias_traces_to_agent_count(self):
        snapshot = ContextSnapshot(agent_count=51, alive_count=48)
        verdict = check_grounding("Population: 51.", snapshot=snapshot, heartbeat=1)
        assert verdict.grounded

    def test_untraceable_reason_reports_claims(self):
        cell = self._unresponsive_cell()
        verdict = check_grounding("economy_collapsed here.", cells=[cell], heartbeat=726)
        assert not verdict.grounded
        assert "economy_collapsed" in verdict.reason
