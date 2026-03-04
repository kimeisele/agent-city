"""
Tests for CityBrain — LLM Cognition Organ.

All LLM calls are mocked — zero network, zero cost.
Tests verify: typing, serialization, key normalization, intent normalization,
budget enforcement, feedback loop formatting, backward compat.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from city.brain import (
    BrainIntent,
    BrainProtocol,
    CityBrain,
    Thought,
    ThoughtKind,
    _BRAIN_TIMEOUT,
    _MAX_TOKENS,
    _normalize_intent,
    _normalize_keys,
    _parse_json_thought,
)


# ── BrainIntent Tests ────────────────────────────────────────────────


class TestBrainIntent:
    def test_all_intents_are_strings(self):
        for intent in BrainIntent:
            assert isinstance(intent.value, str)

    def test_intent_values(self):
        assert BrainIntent.PROPOSE == "propose"
        assert BrainIntent.INQUIRY == "inquiry"
        assert BrainIntent.GOVERN == "govern"
        assert BrainIntent.OBSERVE == "observe"
        assert BrainIntent.CONNECT == "connect"

    def test_intent_from_string(self):
        assert BrainIntent("propose") is BrainIntent.PROPOSE
        with pytest.raises(ValueError):
            BrainIntent("nonexistent")


class TestNormalizeIntent:
    def test_exact_match(self):
        assert _normalize_intent("propose") is BrainIntent.PROPOSE
        assert _normalize_intent("inquiry") is BrainIntent.INQUIRY
        assert _normalize_intent("govern") is BrainIntent.GOVERN
        assert _normalize_intent("observe") is BrainIntent.OBSERVE
        assert _normalize_intent("connect") is BrainIntent.CONNECT

    def test_case_insensitive(self):
        assert _normalize_intent("PROPOSE") is BrainIntent.PROPOSE
        assert _normalize_intent("Inquiry") is BrainIntent.INQUIRY

    def test_fuzzy_match(self):
        assert _normalize_intent("question") is BrainIntent.INQUIRY
        assert _normalize_intent("create") is BrainIntent.PROPOSE
        assert _normalize_intent("review") is BrainIntent.GOVERN
        assert _normalize_intent("monitor") is BrainIntent.OBSERVE
        assert _normalize_intent("introduce") is BrainIntent.CONNECT

    def test_unknown_defaults_observe(self):
        assert _normalize_intent("xyzzy") is BrainIntent.OBSERVE
        assert _normalize_intent("") is BrainIntent.OBSERVE


# ── Key Normalization Tests ───────────────────────────────────────────


class TestNormalizeKeys:
    def test_canonical_keys_pass_through(self):
        data = {"comprehension": "x", "intent": "y", "confidence": 0.5}
        result = _normalize_keys(data)
        assert result["comprehension"] == "x"
        assert result["intent"] == "y"
        assert result["confidence"] == 0.5

    def test_aliases_normalize(self):
        data = {
            "understanding": "I see the point",
            "action": "propose",
            "concepts": ["a", "b"],
            "certainty": 0.9,
            "area": "governance",
        }
        result = _normalize_keys(data)
        assert result["comprehension"] == "I see the point"
        assert result["intent"] == "propose"
        assert result["key_concepts"] == ["a", "b"]
        assert result["confidence"] == 0.9
        assert result["domain_relevance"] == "governance"

    def test_first_canonical_wins(self):
        """If model provides both 'comprehension' and 'understanding', canonical wins."""
        data = {"comprehension": "canonical", "understanding": "alias"}
        result = _normalize_keys(data)
        assert result["comprehension"] == "canonical"


# ── Thought Tests ─────────────────────────────────────────────────────


class TestThought:
    def test_thought_frozen(self):
        t = Thought(
            comprehension="test",
            intent=BrainIntent.OBSERVE,
            domain_relevance="general",
            key_concepts=("a",),
            confidence=0.5,
        )
        with pytest.raises(AttributeError):
            t.comprehension = "changed"  # type: ignore[misc]

    def test_key_concepts_is_tuple(self):
        t = Thought(
            comprehension="",
            intent=BrainIntent.OBSERVE,
            domain_relevance="",
            key_concepts=("a", "b"),
            confidence=0.0,
        )
        assert isinstance(t.key_concepts, tuple)

    def test_to_dict(self):
        t = Thought(
            comprehension="test comprehension",
            intent=BrainIntent.PROPOSE,
            domain_relevance="governance",
            key_concepts=("voting", "council"),
            confidence=0.85,
        )
        d = t.to_dict()
        assert d["comprehension"] == "test comprehension"
        assert d["intent"] == "propose"
        assert d["domain_relevance"] == "governance"
        assert d["key_concepts"] == ["voting", "council"]
        assert d["confidence"] == 0.85
        # Must be JSON-serializable
        json.dumps(d)

    def test_format_for_post(self):
        t = Thought(
            comprehension="Agent routing needs reform.",
            intent=BrainIntent.PROPOSE,
            domain_relevance="governance",
            key_concepts=("routing", "reform"),
            confidence=0.9,
        )
        post = t.format_for_post()
        assert "**Comprehension**:" in post
        assert "Agent routing needs reform" in post
        assert "**Concepts**:" in post
        assert "routing" in post
        assert "**Intent**: propose" in post
        assert "90%" in post
        assert "**Domain**: governance" in post

    def test_format_for_post_empty_concepts(self):
        t = Thought(
            comprehension="minimal",
            intent=BrainIntent.OBSERVE,
            domain_relevance="",
            key_concepts=(),
            confidence=0.5,
        )
        post = t.format_for_post()
        assert "**Concepts**" not in post
        assert "**Domain**" not in post


# ── Protocol Tests ────────────────────────────────────────────────────


class TestBrainProtocol:
    def test_city_brain_satisfies_protocol(self):
        brain = CityBrain()
        assert isinstance(brain, BrainProtocol)


# ── Provider Init Tests ───────────────────────────────────────────────


class TestCityBrain:
    def test_ensure_provider_cached(self):
        brain = CityBrain()
        brain._available = True
        brain._provider = MagicMock()
        assert brain._ensure_provider() is True

    def test_comprehend_discussion_offline(self):
        brain = CityBrain()
        brain._available = False
        result = brain.comprehend_discussion(
            discussion_text="hello",
            agent_spec={"name": "test"},
            gateway_result={},
        )
        assert result is None

    def test_comprehend_signal_offline(self):
        brain = CityBrain()
        brain._available = False
        result = brain.comprehend_signal(
            decoded_signal=MagicMock(affinity=0.5),
            receiver_spec={"domain": "test"},
        )
        assert result is None


# ── JSON Parsing Tests ────────────────────────────────────────────────


class TestJsonParsing:
    def test_parse_valid_json(self):
        raw = json.dumps({
            "comprehension": "The discussion is about agent routing.",
            "intent": "propose",
            "domain_relevance": "governance",
            "key_concepts": ["routing", "signals"],
            "confidence": 0.85,
        })
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert thought.comprehension == "The discussion is about agent routing."
        assert thought.intent is BrainIntent.PROPOSE
        assert thought.domain_relevance == "governance"
        assert thought.key_concepts == ("routing", "signals")
        assert thought.confidence == 0.85

    def test_parse_malformed_json(self):
        thought = _parse_json_thought("not json at all {{{")
        assert thought is None

    def test_parse_missing_fields_defaults(self):
        raw = json.dumps({"comprehension": "partial"})
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert thought.comprehension == "partial"
        assert thought.intent is BrainIntent.OBSERVE  # default
        assert thought.confidence == 0.5               # default
        assert thought.key_concepts == ()               # empty tuple

    def test_parse_clamped_confidence(self):
        thought_high = _parse_json_thought(json.dumps({"confidence": 5.0}))
        assert thought_high is not None
        assert thought_high.confidence == 1.0

        thought_neg = _parse_json_thought(json.dumps({"confidence": -2.0}))
        assert thought_neg is not None
        assert thought_neg.confidence == 0.0

    def test_parse_truncates_long_comprehension(self):
        raw = json.dumps({"comprehension": "x" * 500})
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert len(thought.comprehension) <= 300

    def test_parse_limits_key_concepts(self):
        raw = json.dumps({"key_concepts": ["a", "b", "c", "d", "e", "f", "g"]})
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert len(thought.key_concepts) <= 5

    def test_parse_aliased_keys(self):
        """Model uses 'understanding' instead of 'comprehension' — still parses."""
        raw = json.dumps({
            "understanding": "Agent governance",
            "action": "propose",
            "concepts": ["voting"],
            "certainty": 0.8,
            "area": "governance",
        })
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert thought.comprehension == "Agent governance"
        assert thought.intent is BrainIntent.PROPOSE
        assert thought.key_concepts == ("voting",)
        assert thought.confidence == 0.8
        assert thought.domain_relevance == "governance"

    def test_parse_fuzzy_intent(self):
        """Model says 'question' instead of 'inquiry' — normalized."""
        raw = json.dumps({"intent": "question"})
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert thought.intent is BrainIntent.INQUIRY

    def test_parse_key_concepts_not_list(self):
        """key_concepts is a string — falls back to empty tuple."""
        raw = json.dumps({"key_concepts": "just a string"})
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert thought.key_concepts == ()


# ── Integration Tests (Mock LLM) ─────────────────────────────────────


class TestIntegration:
    def _make_brain_with_mock(self, response_content: str) -> CityBrain:
        brain = CityBrain()
        brain._available = True
        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_provider.invoke.return_value = mock_response
        brain._provider = mock_provider
        return brain

    def test_discussion_with_mock_llm(self):
        """Full flow: context -> messages -> JSON -> Thought."""
        json_response = json.dumps({
            "comprehension": "Agent governance proposal",
            "intent": "propose",
            "domain_relevance": "governance",
            "key_concepts": ["voting", "council"],
            "confidence": 0.9,
        })
        brain = self._make_brain_with_mock(json_response)

        thought = brain.comprehend_discussion(
            discussion_text="We should create a voting mechanism for agents.",
            agent_spec={
                "name": "sys_council",
                "domain": "governance",
                "role": "validator",
                "guna": "SATTVA",
                "capabilities": ["validate", "propose"],
            },
            gateway_result={
                "buddhi_function": "BRAHMA",
                "buddhi_approach": "GENESIS",
            },
            kg_context="City governance protocols",
            signal_reading="manifesting governance",
        )

        assert thought is not None
        assert thought.intent is BrainIntent.PROPOSE
        assert thought.confidence == 0.9

        # Verify provider.invoke was called with correct params
        call_kwargs = brain._provider.invoke.call_args  # type: ignore[union-attr]
        assert call_kwargs.kwargs["model"] == "deepseek/deepseek-v3.2"
        assert call_kwargs.kwargs["max_tokens"] == _MAX_TOKENS
        assert call_kwargs.kwargs["timeout"] == _BRAIN_TIMEOUT
        assert call_kwargs.kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs.kwargs["max_retries"] == 2

    def test_discussion_timeout(self):
        """Provider raises timeout -> returns None (logged, not silent)."""
        brain = CityBrain()
        brain._available = True
        mock_provider = MagicMock()
        mock_provider.invoke.side_effect = TimeoutError("12s exceeded")
        brain._provider = mock_provider

        thought = brain.comprehend_discussion(
            discussion_text="test",
            agent_spec={"name": "test"},
            gateway_result={},
        )
        assert thought is None

    def test_discussion_api_error(self):
        """Non-timeout API error -> returns None (logged)."""
        brain = CityBrain()
        brain._available = True
        mock_provider = MagicMock()
        mock_provider.invoke.side_effect = ConnectionError("network down")
        brain._provider = mock_provider

        thought = brain.comprehend_discussion(
            discussion_text="test",
            agent_spec={"name": "test"},
            gateway_result={},
        )
        assert thought is None

    def test_signal_with_mock_llm(self):
        """Signal comprehension full flow."""
        json_response = json.dumps({
            "comprehension": "Infrastructure monitoring signal",
            "intent": "observe",
            "domain_relevance": "infrastructure",
            "key_concepts": ["health", "metrics"],
            "confidence": 0.7,
        })
        brain = self._make_brain_with_mock(json_response)

        @dataclass
        class MockSignal:
            sender_name: str = "sys_herald"
            hop_count: int = 0

        @dataclass
        class MockDecoded:
            signal: MockSignal | None = None
            affinity: float = 0.5
            resonant_concepts: tuple = ("health", "uptime")
            element_transitions: tuple = ("foundation supports integration",)

        thought = brain.comprehend_signal(
            decoded_signal=MockDecoded(signal=MockSignal()),
            receiver_spec={"domain": "infrastructure", "role": "monitor"},
        )
        assert thought is not None
        assert thought.intent is BrainIntent.OBSERVE

    def test_budget_enforcement(self):
        """Budget gate blocks calls after limit reached."""
        from city.karma_handlers.brain_health import (
            brain_budget_ok as _brain_budget_ok,
            _MAX_BRAIN_CALLS_PER_CYCLE,
        )

        ctx = MagicMock()
        ctx._brain_calls = 0
        type(ctx)._brain_calls = 0
        assert _brain_budget_ok(ctx) is True

        ctx._brain_calls = _MAX_BRAIN_CALLS_PER_CYCLE
        assert _brain_budget_ok(ctx) is False

    def test_backward_compat_no_brain(self):
        """Discussion pipeline works without brain service."""
        from city.discussions_inbox import (
            DiscussionSignal,
            dispatch_discussion,
        )

        signal = DiscussionSignal(
            discussion_number=1,
            title="Test",
            body="Test body",
            author="alice",
            mentioned_agents=[],
        )
        spec = {
            "name": "sys_test",
            "domain": "test",
            "role": "observer",
            "guna": "SATTVA",
            "element": "fire",
            "guardian": "narada",
            "capability_tier": "observer",
            "capability_protocol": "base",
        }
        result = {"buddhi_function": "VISHNU", "buddhi_approach": "DHARMA"}
        stats = {"active": 5, "citizen": 3, "total": 10}

        response = dispatch_discussion(
            signal, result, spec, stats,
            semantic_signal=None,
            brain_thought=None,
        )
        # 9A: Fail Closed — no Brain means no post (returns None)
        assert response is None

    def test_brain_thought_in_response(self):
        """Brain thought appears in discussion response via format_for_post()."""
        from city.discussions_inbox import (
            DiscussionSignal,
            dispatch_discussion,
        )

        signal = DiscussionSignal(
            discussion_number=1,
            title="Test",
            body="Test body",
            author="alice",
            mentioned_agents=[],
        )
        spec = {
            "name": "sys_test",
            "domain": "test",
            "role": "observer",
            "guna": "SATTVA",
            "element": "fire",
            "guardian": "narada",
            "capability_tier": "observer",
            "capability_protocol": "base",
        }
        result = {"buddhi_function": "VISHNU"}
        stats = {"active": 5, "citizen": 3, "total": 10}

        thought = Thought(
            comprehension="This is about agent coordination.",
            intent=BrainIntent.PROPOSE,
            domain_relevance="governance",
            key_concepts=("coordination", "agents"),
            confidence=0.8,
        )

        response = dispatch_discussion(
            signal, result, spec, stats,
            brain_thought=thought,
        )
        assert "Comprehension" in response.body
        assert "agent coordination" in response.body
        assert "**Intent**: propose" in response.body
        assert "80%" in response.body

    def test_thought_roundtrip_serialization(self):
        """Thought -> to_dict() -> JSON -> parse back."""
        original = Thought(
            comprehension="Test roundtrip",
            intent=BrainIntent.GOVERN,
            domain_relevance="security",
            key_concepts=("auth", "policy"),
            confidence=0.75,
        )
        d = original.to_dict()
        raw = json.dumps(d)
        restored = _parse_json_thought(raw)
        assert restored is not None
        assert restored.comprehension == original.comprehension
        assert restored.intent is original.intent
        assert restored.confidence == original.confidence
        assert restored.key_concepts == original.key_concepts


# ── Phase 4: ThoughtKind + Expanded Thought Tests ───────────────────


class TestThoughtKind:
    def test_all_kinds_are_strings(self):
        for kind in ThoughtKind:
            assert isinstance(kind.value, str)

    def test_kind_values(self):
        assert ThoughtKind.COMPREHENSION == "comprehension"
        assert ThoughtKind.HEALTH_CHECK == "health_check"
        assert ThoughtKind.REFLECTION == "reflection"

    def test_thought_kind_default(self):
        """kind defaults to COMPREHENSION — backward compat."""
        t = Thought(
            comprehension="test",
            intent=BrainIntent.OBSERVE,
            domain_relevance="general",
            key_concepts=("a",),
            confidence=0.5,
        )
        assert t.kind is ThoughtKind.COMPREHENSION

    def test_thought_action_hint_and_evidence(self):
        t = Thought(
            comprehension="bottleneck detected",
            intent=BrainIntent.GOVERN,
            domain_relevance="immune",
            key_concepts=("breaker",),
            confidence=0.9,
            kind=ThoughtKind.HEALTH_CHECK,
            action_hint="flag_bottleneck:immune",
            evidence=("breaker tripped", "3 failed heals"),
        )
        assert t.kind is ThoughtKind.HEALTH_CHECK
        assert t.action_hint == "flag_bottleneck:immune"
        assert len(t.evidence) == 2

    def test_to_dict_includes_new_fields(self):
        t = Thought(
            comprehension="test",
            intent=BrainIntent.OBSERVE,
            kind=ThoughtKind.HEALTH_CHECK,
            action_hint="investigate:learning",
            evidence=("low avg weight",),
            confidence=0.8,
        )
        d = t.to_dict()
        assert d["kind"] == "health_check"
        assert d["action_hint"] == "investigate:learning"
        assert d["evidence"] == ["low avg weight"]

    def test_to_dict_omits_empty_hint_evidence(self):
        t = Thought(comprehension="x", intent=BrainIntent.OBSERVE, confidence=0.5)
        d = t.to_dict()
        assert "action_hint" not in d
        assert "evidence" not in d

    def test_format_for_post_expanded(self):
        t = Thought(
            comprehension="System healthy",
            intent=BrainIntent.OBSERVE,
            domain_relevance="infrastructure",
            key_concepts=("health",),
            confidence=0.8,
            kind=ThoughtKind.HEALTH_CHECK,
            action_hint="flag_bottleneck:immune",
            evidence=("3 agents dead", "breaker tripped"),
        )
        post = t.format_for_post()
        assert "**Kind**: health_check" in post
        assert "**Action**: flag_bottleneck:immune" in post
        assert "**Evidence**:" in post
        assert "3 agents dead" in post

    def test_format_for_post_comprehension_no_kind_line(self):
        """COMPREHENSION kind should not show Kind line (backward compat)."""
        t = Thought(
            comprehension="test",
            intent=BrainIntent.OBSERVE,
            confidence=0.5,
        )
        post = t.format_for_post()
        assert "**Kind**" not in post


class TestExpandedJsonParsing:
    def test_parse_action_hint_from_json(self):
        raw = json.dumps({
            "comprehension": "something stuck",
            "intent": "govern",
            "confidence": 0.85,
            "action_hint": "flag_bottleneck:immune",
            "evidence": ["breaker tripped", "3 heals failed"],
        })
        thought = _parse_json_thought(raw, kind=ThoughtKind.HEALTH_CHECK)
        assert thought is not None
        assert thought.action_hint == "flag_bottleneck:immune"
        assert thought.evidence == ("breaker tripped", "3 heals failed")
        assert thought.kind is ThoughtKind.HEALTH_CHECK

    def test_parse_aliased_hint_keys(self):
        """Model says 'suggestion' instead of 'action_hint'."""
        raw = json.dumps({
            "comprehension": "test",
            "suggestion": "investigate:learning",
            "reasoning": ["low weights"],
        })
        thought = _parse_json_thought(raw)
        assert thought is not None
        assert thought.action_hint == "investigate:learning"
        assert thought.evidence == ("low weights",)

    def test_roundtrip_with_new_fields(self):
        original = Thought(
            comprehension="Full roundtrip",
            intent=BrainIntent.PROPOSE,
            domain_relevance="governance",
            key_concepts=("a", "b"),
            confidence=0.9,
            kind=ThoughtKind.REFLECTION,
            action_hint="create_mission:improve routing",
            evidence=("2 routes failed", "low confidence"),
        )
        d = original.to_dict()
        raw = json.dumps(d)
        restored = _parse_json_thought(raw)
        assert restored is not None
        assert restored.kind is ThoughtKind.REFLECTION
        assert restored.action_hint == original.action_hint
        assert restored.evidence == original.evidence


class TestEvaluateHealth:
    def _make_brain_with_mock(self, response_content: str) -> CityBrain:
        brain = CityBrain()
        brain._available = True
        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = response_content
        mock_provider.invoke.return_value = mock_response
        brain._provider = mock_provider
        return brain

    def test_evaluate_health_mock(self):
        from city.brain_context import ContextSnapshot

        json_response = json.dumps({
            "comprehension": "System running smoothly, all agents alive.",
            "intent": "observe",
            "domain_relevance": "infrastructure",
            "key_concepts": ["health", "stability"],
            "confidence": 0.85,
            "action_hint": "",
            "evidence": ["48/51 alive", "chain valid"],
        })
        brain = self._make_brain_with_mock(json_response)
        snap = ContextSnapshot(agent_count=51, alive_count=48, dead_count=3)

        thought = brain.evaluate_health(snap)
        assert thought is not None
        assert thought.kind is ThoughtKind.HEALTH_CHECK
        assert thought.confidence == 0.85
        assert "stability" in thought.key_concepts

    def test_evaluate_health_offline(self):
        from city.brain_context import ContextSnapshot

        brain = CityBrain()
        brain._available = False
        snap = ContextSnapshot()
        assert brain.evaluate_health(snap) is None

    def test_reflect_on_cycle_mock(self):
        from city.brain_context import ContextSnapshot

        json_response = json.dumps({
            "comprehension": "Good rotation. Learning improving.",
            "intent": "observe",
            "domain_relevance": "system",
            "key_concepts": ["learning", "improvement"],
            "confidence": 0.7,
            "action_hint": "create_mission:optimize decay factor",
            "evidence": ["avg weight rising", "0 breaker trips"],
        })
        brain = self._make_brain_with_mock(json_response)
        snap = ContextSnapshot(agent_count=51, alive_count=48)
        reflection = {"learning_stats": {"synapses": 50}, "events_since_last": 5}

        thought = brain.reflect_on_cycle(snap, reflection)
        assert thought is not None
        assert thought.kind is ThoughtKind.REFLECTION
        assert thought.action_hint.startswith("create_mission:")

    def test_protocol_expanded(self):
        """CityBrain still satisfies BrainProtocol with new methods."""
        brain = CityBrain()
        assert isinstance(brain, BrainProtocol)

    def test_evaluate_health_with_memory(self):
        """evaluate_health accepts memory kwarg without error."""
        from city.brain_context import ContextSnapshot

        json_response = json.dumps({
            "comprehension": "System stable.",
            "intent": "observe",
            "confidence": 0.8,
        })
        brain = self._make_brain_with_mock(json_response)
        snap = ContextSnapshot(agent_count=51, alive_count=48)
        mem = MagicMock()
        mem.recent.return_value = [
            {"thought": {"intent": "observe", "comprehension": "ok", "confidence": 0.5}, "heartbeat": 1},
        ]
        mem.pattern_summary.return_value = "1/1 high confidence"
        thought = brain.evaluate_health(snap, memory=mem)
        assert thought is not None

    def test_reflect_on_cycle_with_memory(self):
        """reflect_on_cycle accepts memory kwarg without error."""
        from city.brain_context import ContextSnapshot

        json_response = json.dumps({
            "comprehension": "Good rotation.",
            "intent": "observe",
            "confidence": 0.7,
        })
        brain = self._make_brain_with_mock(json_response)
        snap = ContextSnapshot(agent_count=51, alive_count=48)
        mem = MagicMock()
        mem.recent.return_value = []
        mem.pattern_summary.return_value = "No brain thoughts recorded yet."
        reflection = {"learning_stats": {"synapses": 50}}
        thought = brain.reflect_on_cycle(snap, reflection, memory=mem)
        assert thought is not None


# ── Phase 5: Buddhi Validation Tests ─────────────────────────────────


class TestBuddhiValidate:
    def test_observe_passthrough(self):
        """OBSERVE intent always passes — no alignment check."""
        from city.brain import _buddhi_validate

        t = Thought(
            comprehension="watching",
            intent=BrainIntent.OBSERVE,
            confidence=0.9,
        )
        result = _buddhi_validate(t)
        assert result.confidence == 0.9  # unchanged

    def test_buddhi_graceful_handling(self):
        """Buddhi validation always returns a valid Thought (never None)."""
        from city.brain import _buddhi_validate

        t = Thought(
            comprehension="proposing changes",
            intent=BrainIntent.PROPOSE,
            confidence=0.85,
        )
        result = _buddhi_validate(t)
        # Either passthrough (buddhi unavailable) or penalized (dissonance)
        assert result is not None
        assert 0 < result.confidence <= 0.85

    def test_intent_buddhi_map_exists(self):
        from city.brain import _INTENT_BUDDHI_MAP

        assert "propose" in _INTENT_BUDDHI_MAP
        assert "inquiry" in _INTENT_BUDDHI_MAP
        assert "govern" in _INTENT_BUDDHI_MAP
        assert "observe" in _INTENT_BUDDHI_MAP

    def test_buddhi_penalty_constant(self):
        from city.brain import _BUDDHI_PENALTY

        assert 0 < _BUDDHI_PENALTY < 1

    def test_cognitive_dissonance_in_evidence(self):
        """When dissonance occurs, evidence should contain the flag."""
        from city.brain import _buddhi_validate

        t = Thought(
            comprehension="proposing changes",
            intent=BrainIntent.PROPOSE,
            confidence=0.9,
            evidence=("data point 1",),
        )
        result = _buddhi_validate(t)
        # Either passthrough (buddhi unavailable) or penalized with flag
        assert result is not None
        if result.confidence < 0.9:
            # Dissonance was detected — verify evidence flag
            assert any(
                "cognitive_dissonance" in e for e in result.evidence
            )
