"""
Tests for BrainPrompt — Versioned Structured System Prompt Builder.

Covers: header, payload (all kinds), schema, assembly, echo chamber guard,
past thoughts framing, version string.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from city.brain_context import ContextSnapshot
from city.brain_prompt import (
    _BRAIN_PROTOCOL_VERSION,
    BrainPromptHeader,
    build_header,
    build_payload,
    build_schema,
    build_system_prompt,
)


# ── Header Tests ──────────────────────────────────────────────────────


class TestBuildHeader:
    def test_header_from_snapshot(self):
        snap = ContextSnapshot(agent_count=51, alive_count=48, murali_phase="KARMA")
        header = build_header(42, snapshot=snap, murali_phase="KARMA")
        assert header.version == _BRAIN_PROTOCOL_VERSION
        assert header.heartbeat == 42
        assert header.agent_count == 51
        assert header.alive_count == 48
        assert header.murali_phase == "KARMA"

    def test_header_none_snapshot(self):
        header = build_header(0)
        assert header.agent_count == 0
        assert header.alive_count == 0
        assert header.murali_phase == "UNKNOWN"

    def test_header_with_memory(self):
        mem = MagicMock()
        mem.pattern_summary.return_value = "2/3 high confidence, avg 0.67"
        header = build_header(5, memory=mem)
        assert "2/3" in header.memory_summary

    def test_header_render_contains_version(self):
        header = BrainPromptHeader(
            version="5.0",
            model="test-model",
            heartbeat=10,
            murali_phase="MOKSHA",
            agent_count=20,
            alive_count=18,
            memory_summary="test summary",
        )
        rendered = header.render()
        assert "[HEADER v5.0]" in rendered
        assert "test-model" in rendered
        assert "#10" in rendered
        assert "MOKSHA" in rendered
        assert "18/20" in rendered


# ── Payload Tests ─────────────────────────────────────────────────────


class TestBuildPayload:
    def test_health_check_payload(self):
        snap = ContextSnapshot(
            agent_count=51,
            alive_count=48,
            dead_count=3,
            chain_valid=True,
            failing_contracts=("ruff_clean",),
            immune_stats={"heals_attempted": 5, "breaker_tripped": False},
            learning_stats={"synapses": 120, "avg_weight": 0.65},
        )
        lines = build_payload("health_check", snapshot=snap)
        joined = "\n".join(lines)
        assert "48/51" in joined
        assert "3 dead" in joined
        assert "ruff_clean" in joined
        assert "5 heal attempts" in joined
        assert "120 synapses" in joined

    def test_reflection_payload_with_outcome_diff(self):
        snap = ContextSnapshot(agent_count=51, alive_count=48)
        outcome_diff = {
            "agent_delta": -2,
            "chain_changed": False,
            "new_failing": ("test_contract",),
            "resolved": (),
            "learning_delta": {"synapse_delta": 5},
        }
        lines = build_payload(
            "reflection",
            snapshot=snap,
            outcome_diff=outcome_diff,
        )
        joined = "\n".join(lines)
        assert "OUTCOME DIFF" in joined
        assert "Agent delta: -2" in joined
        assert "test_contract" in joined

    def test_comprehension_payload(self):
        lines = build_payload(
            "comprehension",
            agent_spec={"name": "sys_test", "domain": "governance", "role": "validator"},
            gateway_result={"buddhi_function": "BRAHMA", "buddhi_approach": "GENESIS"},
            kg_context="Some domain knowledge",
        )
        joined = "\n".join(lines)
        assert "sys_test" in joined
        assert "validator" in joined
        assert "BRAHMA" in joined
        assert "domain knowledge" in joined

    def test_signal_payload(self):
        decoded = MagicMock()
        decoded.resonant_concepts = ("health", "uptime")
        decoded.element_transitions = ("foundation supports integration",)
        decoded.affinity = 0.75
        decoded.signal = MagicMock()
        decoded.signal.sender_name = "sys_herald"

        lines = build_payload(
            "signal",
            decoded_signal=decoded,
            receiver_spec={"domain": "infrastructure", "role": "monitor"},
        )
        joined = "\n".join(lines)
        assert "sys_herald" in joined
        assert "0.75" in joined
        assert "monitor" in joined

    def test_no_snapshot_health(self):
        lines = build_payload("health_check")
        assert "No system snapshot" in "\n".join(lines)


# ── Echo Chamber Guard (Fix #3) ──────────────────────────────────────


class TestEchoChamberGuard:
    def test_past_thoughts_framed(self):
        past = [
            {
                "thought": {"intent": "observe", "comprehension": "System stable", "confidence": 0.8},
                "heartbeat": 5,
            },
            {
                "thought": {"intent": "propose", "comprehension": "Need reform", "confidence": 0.9},
                "heartbeat": 6,
            },
        ]
        lines = build_payload("health_check", past_thoughts=past)
        joined = "\n".join(lines)
        assert "PAST THOUGHTS" in joined
        assert "do NOT repeat" in joined
        assert "hb#5" in joined
        assert "hb#6" in joined

    def test_no_past_thoughts_no_section(self):
        lines = build_payload("health_check")
        joined = "\n".join(lines)
        assert "PAST THOUGHTS" not in joined

    def test_past_thoughts_capped_at_3(self):
        past = [
            {"thought": {"intent": "observe", "comprehension": f"t{i}", "confidence": 0.5}, "heartbeat": i}
            for i in range(10)
        ]
        lines = build_payload("health_check", past_thoughts=past)
        joined = "\n".join(lines)
        # Only last 3 should appear
        assert "hb#7" in joined
        assert "hb#8" in joined
        assert "hb#9" in joined
        assert "hb#0" not in joined


# ── Schema Tests ──────────────────────────────────────────────────────


class TestBuildSchema:
    def test_health_check_schema_is_cognitive(self):
        schema = build_schema("health_check")
        assert "Respond with JSON" not in schema
        assert "health" in schema.lower()
        assert "action" in schema

    def test_reflection_schema_is_cognitive(self):
        schema = build_schema("reflection")
        assert "Respond with JSON" not in schema
        assert "reflect" in schema.lower()

    def test_comprehension_schema_is_cognitive(self):
        schema = build_schema("comprehension")
        assert "Respond with JSON" not in schema
        assert "understand" in schema.lower()  # Kshetrajna: understanding, not deciding
        assert "concepts" in schema.lower()

    def test_unknown_kind_falls_back(self):
        schema = build_schema("nonexistent_kind")
        assert "understand" in schema.lower()  # falls back to comprehension


# ── Assembly Tests ────────────────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_assembly_structure(self):
        header = BrainPromptHeader(
            version="5.0",
            model="test-model",
            heartbeat=1,
            murali_phase="KARMA",
            agent_count=10,
            alive_count=8,
            memory_summary="test",
        )
        payload = ["Line 1", "Line 2"]
        schema = "Respond with JSON: {}"
        prompt = build_system_prompt(header, payload, schema)
        assert "[HEADER v5.0]" in prompt
        assert "[PAYLOAD v5.0]" in prompt
        assert "[SCHEMA v5.0]" in prompt
        assert "Line 1\nLine 2" in prompt
        assert "Respond with JSON" in prompt

    def test_version_consistency(self):
        header = build_header(0)
        assert header.version == _BRAIN_PROTOCOL_VERSION
