"""
Tests for BrainAction — typed action_hint vocabulary (Schritt 2).

Covers:
- ActionVerb enum completeness
- BrainAction properties (auth_tier, read_only, enforcement, confidence)
- parse_action_hint: all verbs, special formats, unknown verbs, edge cases
- CityAttention signal generation
- BRAIN_INTENT_SIGNALS completeness

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.brain_action import (
    ActionVerb,
    AuthTier,
    BrainAction,
    BRAIN_INTENT_SIGNALS,
    READ_ONLY_VERBS,
    parse_action_hint,
)


# ── ActionVerb Tests ─────────────────────────────────────────────────


class TestActionVerb:
    def test_all_9_verbs(self):
        assert len(ActionVerb) == 9

    def test_string_values_match(self):
        assert ActionVerb.FLAG_BOTTLENECK == "flag_bottleneck"
        assert ActionVerb.RETRACT == "retract"
        assert ActionVerb.QUARANTINE == "quarantine"
        assert ActionVerb.ASSIGN_AGENT == "assign_agent"

    def test_verb_from_string(self):
        assert ActionVerb("investigate") == ActionVerb.INVESTIGATE
        assert ActionVerb("run_status") == ActionVerb.RUN_STATUS

    def test_unknown_verb_raises(self):
        with pytest.raises(ValueError):
            ActionVerb("nonexistent")


# ── BrainAction Tests ────────────────────────────────────────────────


class TestBrainAction:
    def test_auth_tier_public(self):
        action = BrainAction(verb=ActionVerb.RUN_STATUS)
        assert action.auth_tier == AuthTier.PUBLIC

    def test_auth_tier_citizen(self):
        action = BrainAction(verb=ActionVerb.CREATE_MISSION, target="fix tests")
        assert action.auth_tier == AuthTier.CITIZEN

    def test_auth_tier_operator(self):
        action = BrainAction(verb=ActionVerb.RETRACT, target="comment_123")
        assert action.auth_tier == AuthTier.OPERATOR

    def test_is_read_only(self):
        assert BrainAction(verb=ActionVerb.RUN_STATUS).is_read_only
        assert BrainAction(verb=ActionVerb.CHECK_HEALTH, target="infra").is_read_only
        assert not BrainAction(verb=ActionVerb.RETRACT, target="x").is_read_only

    def test_is_enforcement(self):
        assert BrainAction(verb=ActionVerb.RETRACT, target="x").is_enforcement
        assert BrainAction(verb=ActionVerb.QUARANTINE, target="x").is_enforcement
        assert not BrainAction(verb=ActionVerb.ESCALATE, target="x").is_enforcement

    def test_confidence_sufficient_for_enforcement(self):
        low = BrainAction(verb=ActionVerb.RETRACT, target="x", source_confidence=0.5)
        assert not low.confidence_sufficient

        high = BrainAction(verb=ActionVerb.RETRACT, target="x", source_confidence=0.8)
        assert high.confidence_sufficient

    def test_confidence_always_sufficient_for_non_enforcement(self):
        action = BrainAction(verb=ActionVerb.INVESTIGATE, target="topic", source_confidence=0.1)
        assert action.confidence_sufficient

    def test_to_city_intent_signal(self):
        action = BrainAction(verb=ActionVerb.FLAG_BOTTLENECK, target="engineering")
        assert action.to_city_intent_signal() == "brain:flag_bottleneck"

    def test_to_ops_string(self):
        action = BrainAction(verb=ActionVerb.ESCALATE, target="prana drain")
        assert action.to_ops_string("#42") == "brain_action:escalate:prana drain:#42"

    def test_to_ops_string_no_target(self):
        action = BrainAction(verb=ActionVerb.RUN_STATUS)
        assert action.to_ops_string() == "brain_action:run_status"

    def test_frozen(self):
        action = BrainAction(verb=ActionVerb.INVESTIGATE, target="x")
        with pytest.raises(AttributeError):
            action.target = "y"  # type: ignore[misc]


# ── parse_action_hint Tests ──────────────────────────────────────────


class TestParseActionHint:
    def test_empty_returns_none(self):
        assert parse_action_hint("") is None
        assert parse_action_hint("   ") is None
        assert parse_action_hint(None) is None  # type: ignore[arg-type]

    def test_bare_run_status(self):
        action = parse_action_hint("run_status")
        assert action is not None
        assert action.verb == ActionVerb.RUN_STATUS
        assert action.target == ""

    def test_flag_bottleneck(self):
        action = parse_action_hint("flag_bottleneck:engineering")
        assert action is not None
        assert action.verb == ActionVerb.FLAG_BOTTLENECK
        assert action.target == "engineering"

    def test_investigate(self):
        action = parse_action_hint("investigate:prana drain pattern")
        assert action is not None
        assert action.verb == ActionVerb.INVESTIGATE
        assert action.target == "prana drain pattern"

    def test_create_mission(self):
        action = parse_action_hint("create_mission:fix the ruff contract")
        assert action is not None
        assert action.verb == ActionVerb.CREATE_MISSION
        assert action.target == "fix the ruff contract"

    def test_check_health(self):
        action = parse_action_hint("check_health:governance")
        assert action is not None
        assert action.verb == ActionVerb.CHECK_HEALTH
        assert action.target == "governance"

    def test_assign_agent_with_task(self):
        action = parse_action_hint("assign_agent:sys_engineer:fix the tests")
        assert action is not None
        assert action.verb == ActionVerb.ASSIGN_AGENT
        assert action.target == "sys_engineer"
        assert action.detail == "fix the tests"

    def test_assign_agent_no_task(self):
        action = parse_action_hint("assign_agent:sys_engineer")
        assert action is not None
        assert action.verb == ActionVerb.ASSIGN_AGENT
        assert action.target == "sys_engineer"
        assert action.detail == ""

    def test_escalate(self):
        action = parse_action_hint("escalate:critical prana depletion")
        assert action is not None
        assert action.verb == ActionVerb.ESCALATE
        assert action.target == "critical prana depletion"

    def test_retract(self):
        action = parse_action_hint("retract:DC_kwDONs123", confidence=0.85)
        assert action is not None
        assert action.verb == ActionVerb.RETRACT
        assert action.target == "DC_kwDONs123"
        assert action.source_confidence == 0.85

    def test_quarantine(self):
        action = parse_action_hint("quarantine:bad_agent", confidence=0.9)
        assert action is not None
        assert action.verb == ActionVerb.QUARANTINE
        assert action.target == "bad_agent"

    def test_unknown_verb_returns_none(self):
        assert parse_action_hint("destroy:everything") is None
        assert parse_action_hint("sql_inject:DROP TABLE") is None

    def test_confidence_passthrough(self):
        action = parse_action_hint("investigate:topic", confidence=0.73)
        assert action is not None
        assert action.source_confidence == 0.73

    def test_whitespace_handling(self):
        action = parse_action_hint("  flag_bottleneck: engineering  ")
        assert action is not None
        assert action.target == "engineering"


# ── BRAIN_INTENT_SIGNALS Tests ───────────────────────────────────────


class TestBrainIntentSignals:
    def test_all_verbs_have_signals(self):
        for verb in ActionVerb:
            key = f"brain:{verb.value}"
            assert key in BRAIN_INTENT_SIGNALS

    def test_signal_count_matches_verb_count(self):
        assert len(BRAIN_INTENT_SIGNALS) == len(ActionVerb)

    def test_handler_naming_convention(self):
        for signal, handler in BRAIN_INTENT_SIGNALS.items():
            assert handler.startswith("handle_brain_")


# ── READ_ONLY_VERBS Tests ───────────────────────────────────────────


class TestReadOnlyVerbs:
    def test_contains_expected(self):
        assert ActionVerb.RUN_STATUS in READ_ONLY_VERBS
        assert ActionVerb.CHECK_HEALTH in READ_ONLY_VERBS

    def test_does_not_contain_mutating(self):
        assert ActionVerb.RETRACT not in READ_ONLY_VERBS
        assert ActionVerb.QUARANTINE not in READ_ONLY_VERBS
        assert ActionVerb.CREATE_MISSION not in READ_ONLY_VERBS


# ── ActionVerb Completeness Tests ─────────────────────────────────────


class TestActionVerbCompleteness:
    """ActionVerb enum must cover all verbs used in the action system."""

    def test_all_verbs_have_auth_tier(self):
        """Every ActionVerb must have a defined auth tier."""
        from city.brain_action import _VERB_AUTH

        for verb in ActionVerb:
            assert verb in _VERB_AUTH, (
                f"ActionVerb.{verb.name} has no auth tier in _VERB_AUTH"
            )

    def test_parse_roundtrip(self):
        """Every ActionVerb can be parsed from a hint string."""
        from city.brain_action import parse_action_hint

        for verb in ActionVerb:
            hint = f"{verb.value}:test_target"
            action = parse_action_hint(hint)
            assert action is not None, f"parse_action_hint failed for '{hint}'"
            assert action.verb == verb


# ── Rejected Actions Feedback Loop Tests (Fix 2) ────────────────────


class TestRejectedActionsFeedback:
    """Rejected BrainActions must surface in Field Digest."""

    def test_low_confidence_enforcement_tracked(self):
        """Enforcement verb with low confidence is tracked on ctx."""
        from unittest.mock import MagicMock
        from city.karma_handlers.brain_health import _execute_critique_hint

        ctx = MagicMock()
        ctx._rejected_actions = []
        critique = MagicMock()
        critique.action_hint = "retract:DC_kwDOTest123"
        critique.confidence = 0.3  # Below 0.7 threshold
        critique.evidence = ""

        ops = []
        _execute_critique_hint(ctx, critique, ops)

        assert len(ctx._rejected_actions) == 1
        assert ctx._rejected_actions[0]["verb"] == "retract"
        assert "confidence" in ctx._rejected_actions[0]["reason"]
        assert any("low_confidence" in op for op in ops)

    def test_high_confidence_enforcement_not_tracked(self):
        """Enforcement verb with high confidence is NOT tracked as rejected."""
        from unittest.mock import MagicMock
        from city.karma_handlers.brain_health import _execute_critique_hint

        ctx = MagicMock()
        ctx._rejected_actions = []
        ctx.offline_mode = False
        ctx.discussions.retract_post.return_value = True
        critique = MagicMock()
        critique.action_hint = "retract:DC_kwDOTest123"
        critique.confidence = 0.85  # Above threshold
        critique.evidence = "bad quality"

        ops = []
        _execute_critique_hint(ctx, critique, ops)

        assert len(ctx._rejected_actions) == 0


# ── SCOPE_REJECT → NADI Escalation Tests (Campaign C) ────────────────


class TestScopeRejectNadiEscalation:
    """When Scope Gate rejects a code-fix mission, NADI must escalate to Steward."""

    def test_health_hint_scope_reject_emits_nadi(self):
        """Health hint with ruff target → SCOPE_REJECT + NADI emit."""
        from unittest.mock import MagicMock, call
        from city.karma_handlers.brain_health import _execute_health_hint

        ctx = MagicMock()
        ctx.heartbeat_count = 42
        nadi_mock = MagicMock()
        ctx.federation_nadi = nadi_mock

        health_thought = MagicMock()
        health_thought.action_hint = "create_mission:fix ruff_clean contract"
        health_thought.confidence = 0.9

        ops: list[str] = []
        _execute_health_hint(ctx, health_thought, ops)

        # Should have SCOPE_REJECT in operations
        assert any("SCOPE_REJECT" in op for op in ops), f"Expected SCOPE_REJECT in {ops}"

        # Should have emitted NADI message
        nadi_mock.emit.assert_called_once()
        call_kwargs = nadi_mock.emit.call_args
        assert call_kwargs.kwargs.get("operation") or call_kwargs[1].get("operation", "") == "bottleneck_escalation"

    def test_critique_hint_scope_reject_emits_nadi(self):
        """Critique hint with tests_pass target → SCOPE_REJECT + NADI emit."""
        from unittest.mock import MagicMock
        from city.karma_handlers.brain_health import _execute_critique_hint

        ctx = MagicMock()
        ctx._rejected_actions = []
        ctx.heartbeat_count = 7
        nadi_mock = MagicMock()
        ctx.federation_nadi = nadi_mock

        critique = MagicMock()
        critique.action_hint = "create_mission:tests_pass failing"
        critique.confidence = 0.9
        critique.evidence = "tests broken"

        ops: list[str] = []
        _execute_critique_hint(ctx, critique, ops)

        assert any("SCOPE_REJECT" in op for op in ops)
        nadi_mock.emit.assert_called_once()
        kw = nadi_mock.emit.call_args[1]
        assert kw["operation"] == "bottleneck_escalation"
        assert kw["payload"]["source"] == "brain_critique"
        assert kw["payload"]["requested_action"] == "fix"

    def test_scope_reject_graceful_without_nadi(self):
        """SCOPE_REJECT still works if federation_nadi is None."""
        from unittest.mock import MagicMock
        from city.karma_handlers.brain_health import _execute_health_hint

        ctx = MagicMock()
        ctx.federation_nadi = None

        health_thought = MagicMock()
        health_thought.action_hint = "create_mission:fix ruff contract"
        health_thought.confidence = 0.9

        ops: list[str] = []
        # Should not raise
        _execute_health_hint(ctx, health_thought, ops)
        assert any("SCOPE_REJECT" in op for op in ops)

    def test_non_code_mission_no_nadi_emit(self):
        """Non-code missions should NOT trigger NADI escalation."""
        from unittest.mock import MagicMock
        from city.karma_handlers.brain_health import _execute_health_hint

        ctx = MagicMock()
        nadi_mock = MagicMock()
        ctx.federation_nadi = nadi_mock
        ctx.registry = MagicMock()
        ctx.registry.get.return_value = None  # no executor
        ctx.sankalpa = None

        health_thought = MagicMock()
        health_thought.action_hint = "create_mission:investigate agent wellness"
        health_thought.confidence = 0.9

        ops: list[str] = []
        _execute_health_hint(ctx, health_thought, ops)

        # Should NOT have SCOPE_REJECT
        assert not any("SCOPE_REJECT" in op for op in ops)
        # Should NOT have emitted NADI
        nadi_mock.emit.assert_not_called()

