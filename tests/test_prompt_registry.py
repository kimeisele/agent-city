"""
Tests for PromptRegistry + PromptBuilders (8I: Prompt Infrastructure).

Covers:
- PromptRegistry: register, get, dispatch, fallback
- PromptContext: all fields, safe defaults
- All 6 builders: payload content, schema content, user_message
- Echo chamber guard via render_past_thoughts
- Singleton get_prompt_registry()
- Builder protocol compliance

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from city.brain_context import ContextSnapshot
from city.prompt_registry import (
    PromptBuilder,
    PromptContext,
    PromptRegistry,
    render_past_thoughts,
)


# ── PromptContext Tests ───────────────────────────────────────────────


class TestPromptContext:
    def test_defaults_safe(self):
        ctx = PromptContext()
        assert ctx.snapshot is None
        assert ctx.agent_spec is None
        assert ctx.gateway_result is None
        assert ctx.kg_context == ""
        assert ctx.signal_reading == ""
        assert ctx.decoded_signal is None
        assert ctx.receiver_spec is None
        assert ctx.reflection is None
        assert ctx.outcome_diff is None
        assert ctx.field_summary == ""
        assert ctx.past_thoughts is None

    def test_all_fields_settable(self):
        snap = ContextSnapshot(agent_count=10, alive_count=8)
        ctx = PromptContext(
            snapshot=snap,
            agent_spec={"name": "test"},
            gateway_result={"buddhi_function": "BRAHMA"},
            kg_context="domain knowledge",
            signal_reading="semantic reading",
            reflection={"learning_stats": {}},
            outcome_diff={"agent_delta": 1},
            field_summary="field digest here",
            past_thoughts=[{"thought": {}, "heartbeat": 1}],
        )
        assert ctx.snapshot is snap
        assert ctx.agent_spec["name"] == "test"
        assert ctx.kg_context == "domain knowledge"
        assert ctx.field_summary == "field digest here"


# ── PromptRegistry Tests ─────────────────────────────────────────────


class _MockBuilder:
    """Minimal builder for registry tests."""

    def __init__(self, kind_name: str):
        self._kind = kind_name

    @property
    def kind(self) -> str:
        return self._kind

    def build_payload(self, ctx: PromptContext) -> list[str]:
        return [f"payload for {self._kind}"]

    def build_schema(self) -> str:
        return f"schema for {self._kind}"

    def build_user_message(self, ctx: PromptContext) -> str:
        return f"user message for {self._kind}"


class TestPromptRegistry:
    def test_register_and_get(self):
        reg = PromptRegistry()
        builder = _MockBuilder("test_kind")
        reg.register(builder)
        assert reg.get("test_kind") is builder
        assert reg.get("nonexistent") is None

    def test_kinds_list(self):
        reg = PromptRegistry()
        reg.register(_MockBuilder("alpha"))
        reg.register(_MockBuilder("beta"))
        assert sorted(reg.kinds) == ["alpha", "beta"]

    def test_len(self):
        reg = PromptRegistry()
        assert len(reg) == 0
        reg.register(_MockBuilder("x"))
        assert len(reg) == 1

    def test_build_payload_dispatch(self):
        reg = PromptRegistry()
        reg.register(_MockBuilder("health_check"))
        ctx = PromptContext()
        lines = reg.build_payload("health_check", ctx)
        assert lines == ["payload for health_check"]

    def test_build_payload_unknown_kind(self):
        reg = PromptRegistry()
        ctx = PromptContext()
        lines = reg.build_payload("nonexistent", ctx)
        assert lines == []

    def test_build_schema_dispatch(self):
        reg = PromptRegistry()
        reg.register(_MockBuilder("reflection"))
        schema = reg.build_schema("reflection")
        assert schema == "schema for reflection"

    def test_build_schema_fallback_to_comprehension(self):
        reg = PromptRegistry()
        reg.register(_MockBuilder("comprehension"))
        schema = reg.build_schema("nonexistent")
        assert schema == "schema for comprehension"

    def test_build_user_message(self):
        reg = PromptRegistry()
        reg.register(_MockBuilder("insight"))
        ctx = PromptContext()
        msg = reg.build_user_message("insight", ctx)
        assert msg == "user message for insight"

    def test_overwrite_builder(self):
        reg = PromptRegistry()
        reg.register(_MockBuilder("x"))
        reg.register(_MockBuilder("x"))  # overwrite
        assert len(reg) == 1

    def test_protocol_compliance(self):
        """_MockBuilder satisfies PromptBuilder protocol."""
        builder = _MockBuilder("test")
        assert isinstance(builder, PromptBuilder)


# ── Echo Chamber Guard ────────────────────────────────────────────────


class TestRenderPastThoughts:
    def test_none_returns_empty(self):
        assert render_past_thoughts(None) == []

    def test_empty_list_returns_empty(self):
        assert render_past_thoughts([]) == []

    def test_renders_past_thoughts(self):
        past = [
            {"thought": {"intent": "observe", "comprehension": "All good", "confidence": 0.8}, "heartbeat": 5},
        ]
        lines = render_past_thoughts(past)
        text = "\n".join(lines)
        assert "PAST THOUGHTS" in text
        assert "do NOT repeat" in text
        assert "hb#5" in text
        assert "[observe]" in text

    def test_capped_at_3(self):
        past = [
            {"thought": {"intent": "observe", "comprehension": f"t{i}", "confidence": 0.5}, "heartbeat": i}
            for i in range(10)
        ]
        lines = render_past_thoughts(past)
        text = "\n".join(lines)
        assert "hb#7" in text
        assert "hb#8" in text
        assert "hb#9" in text
        assert "hb#0" not in text


# ── Individual Builder Tests ──────────────────────────────────────────


class TestComprehensionBuilder:
    def test_payload_with_agent_spec(self):
        from city.prompt_builders.comprehension import ComprehensionBuilder

        builder = ComprehensionBuilder()
        ctx = PromptContext(
            agent_spec={"name": "sys_test", "domain": "governance", "role": "validator"},
            gateway_result={"buddhi_function": "BRAHMA", "buddhi_approach": "GENESIS"},
            kg_context="Some knowledge",
        )
        lines = builder.build_payload(ctx)
        text = "\n".join(lines)
        assert "sys_test" in text
        assert "validator" in text
        assert "BRAHMA" in text
        assert "knowledge" in text

    def test_payload_with_snapshot(self):
        from city.prompt_builders.comprehension import ComprehensionBuilder

        builder = ComprehensionBuilder()
        snap = ContextSnapshot(agent_count=51, alive_count=48, chain_valid=True)
        ctx = PromptContext(snapshot=snap)
        lines = builder.build_payload(ctx)
        text = "\n".join(lines)
        assert "SYSTEM STATE" in text
        assert "48/51" in text

    def test_schema_is_cognitive_instruction(self):
        from city.prompt_builders.comprehension import ComprehensionBuilder

        schema = ComprehensionBuilder().build_schema()
        assert "Respond with JSON" not in schema
        assert "understand" in schema.lower()  # Kshetrajna: comprehension, not decision
        assert "concepts" in schema.lower()

    def test_kind(self):
        from city.prompt_builders.comprehension import ComprehensionBuilder

        assert ComprehensionBuilder().kind == "comprehension"

    def test_protocol_compliance(self):
        from city.prompt_builders.comprehension import ComprehensionBuilder

        assert isinstance(ComprehensionBuilder(), PromptBuilder)


class TestHealthCheckBuilder:
    def test_payload_with_snapshot(self):
        from city.prompt_builders.health import HealthCheckBuilder

        snap = ContextSnapshot(
            agent_count=51, alive_count=48, dead_count=3,
            chain_valid=True,
            failing_contracts=("ruff_clean",),
            immune_stats={"heals_attempted": 5, "breaker_tripped": False},
            learning_stats={"synapses": 120, "avg_weight": 0.65},
        )
        ctx = PromptContext(snapshot=snap)
        lines = HealthCheckBuilder().build_payload(ctx)
        text = "\n".join(lines)
        assert "48/51" in text
        assert "3 dead" in text
        assert "ruff_clean" in text
        assert "5 heal attempts" in text
        assert "120 synapses" in text

    def test_payload_no_snapshot(self):
        from city.prompt_builders.health import HealthCheckBuilder

        lines = HealthCheckBuilder().build_payload(PromptContext())
        assert "No system snapshot" in "\n".join(lines)

    def test_kind(self):
        from city.prompt_builders.health import HealthCheckBuilder

        assert HealthCheckBuilder().kind == "health_check"


class TestReflectionBuilder:
    def test_payload_with_outcome_diff(self):
        from city.prompt_builders.reflection import ReflectionBuilder

        snap = ContextSnapshot(agent_count=51, alive_count=48)
        ctx = PromptContext(
            snapshot=snap,
            outcome_diff={
                "agent_delta": -2,
                "chain_changed": False,
                "new_failing": ("test_contract",),
                "resolved": (),
                "learning_delta": {"synapse_delta": 5},
            },
        )
        lines = ReflectionBuilder().build_payload(ctx)
        text = "\n".join(lines)
        assert "OUTCOME DIFF" in text
        assert "Agent delta: -2" in text
        assert "test_contract" in text

    def test_user_message_with_reflection(self):
        from city.prompt_builders.reflection import ReflectionBuilder

        ctx = PromptContext(
            reflection={
                "learning_stats": {"synapses": 10, "decayed": 2, "trimmed": 1},
                "mission_results_terminal": [{"id": "m1"}],
            },
        )
        msg = ReflectionBuilder().build_user_message(ctx)
        assert "MURALI rotation" in msg
        assert "Missions completed: 1" in msg

    def test_kind(self):
        from city.prompt_builders.reflection import ReflectionBuilder

        assert ReflectionBuilder().kind == "reflection"


class TestInsightBuilder:
    def test_payload_with_missions(self):
        from city.prompt_builders.insight import InsightBuilder

        ctx = PromptContext(
            snapshot=ContextSnapshot(agent_count=10, alive_count=8),
            reflection={"mission_results_terminal": [
                {"name": "fix_tests", "status": "completed", "owner": "sys_engineer"},
            ]},
        )
        lines = InsightBuilder().build_payload(ctx)
        text = "\n".join(lines)
        assert "synthesizer" in text.lower()
        assert "fix_tests" in text
        assert "sys_engineer" in text

    def test_schema_no_respond_with_json(self):
        from city.prompt_builders.insight import InsightBuilder

        schema = InsightBuilder().build_schema()
        assert "Respond with JSON" not in schema
        assert "insight" in schema.lower()

    def test_kind(self):
        from city.prompt_builders.insight import InsightBuilder

        assert InsightBuilder().kind == "insight"


class TestCritiqueBuilder:
    def test_payload_with_field_summary(self):
        from city.prompt_builders.critique import CritiqueBuilder

        ctx = PromptContext(
            snapshot=ContextSnapshot(agent_count=10, alive_count=8, chain_valid=True),
            field_summary="[ANOMALY] Agent spam detected",
        )
        lines = CritiqueBuilder().build_payload(ctx)
        text = "\n".join(lines)
        assert "Kshetrajna" in text
        assert "FIELD DIGEST" in text
        assert "Agent spam detected" in text

    def test_schema_is_cognitive_instruction(self):
        from city.prompt_builders.critique import CritiqueBuilder

        schema = CritiqueBuilder().build_schema()
        assert "Respond with JSON" not in schema
        assert "anomalies" in schema.lower()
        assert "fix" in schema

    def test_user_message_includes_field_summary(self):
        from city.prompt_builders.critique import CritiqueBuilder

        ctx = PromptContext(field_summary="test summary")
        msg = CritiqueBuilder().build_user_message(ctx)
        assert "test summary" in msg

    def test_kind(self):
        from city.prompt_builders.critique import CritiqueBuilder

        assert CritiqueBuilder().kind == "critique"


class TestSignalBuilder:
    def test_payload_with_signal(self):
        from city.prompt_builders.signal import SignalBuilder

        decoded = MagicMock()
        decoded.resonant_concepts = ("health", "uptime")
        decoded.element_transitions = ("foundation supports integration",)
        decoded.affinity = 0.75
        decoded.signal = MagicMock()
        decoded.signal.sender_name = "sys_herald"

        ctx = PromptContext(
            decoded_signal=decoded,
            receiver_spec={"domain": "infrastructure", "role": "monitor"},
        )
        lines = SignalBuilder().build_payload(ctx)
        text = "\n".join(lines)
        assert "sys_herald" in text
        assert "0.75" in text
        assert "monitor" in text

    def test_kind(self):
        from city.prompt_builders.signal import SignalBuilder

        assert SignalBuilder().kind == "signal"


# ── Singleton Registry Tests ─────────────────────────────────────────


class TestGetPromptRegistry:
    def test_singleton_has_all_6_builders(self):
        from city.brain_prompt import get_prompt_registry

        reg = get_prompt_registry()
        assert len(reg) == 6
        expected = {"comprehension", "health_check", "reflection", "insight", "critique", "signal"}
        assert set(reg.kinds) == expected

    def test_singleton_returns_same_instance(self):
        from city.brain_prompt import get_prompt_registry

        reg1 = get_prompt_registry()
        reg2 = get_prompt_registry()
        assert reg1 is reg2


# ── Cognitive Schema Tests ───────────────────────────────────────────


class TestAllBuildersNoCognitiveSchemaInSchema:
    """All builders must produce cognitive instructions, not JSON templates."""

    def test_no_builder_uses_respond_with_json(self):
        from city.brain_prompt import get_prompt_registry

        reg = get_prompt_registry()
        for kind in reg.kinds:
            builder = reg.get(kind)
            schema = builder.build_schema()
            assert "Respond with JSON" not in schema, (
                f"Builder '{kind}' still uses 'Respond with JSON' — "
                f"JSON mode is API-level, not prompt-level"
            )
