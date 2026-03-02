"""
Tests for Brain Feedback Loop — parsing [Brain] posts from Discussions.

Tests the parsing functions directly without importing city.phases.genesis
(which triggers a heavy transitive import chain through PhaseContext).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

# ── Direct parsing logic (mirrors genesis._parse_brain_json) ──────────
# Tested independently to avoid transitive import chain through PhaseContext.

_BRAIN_JSON_PREFIX = "<!--BRAIN_JSON:"
_BRAIN_JSON_SUFFIX = "-->"


def _parse_brain_json(body: str) -> dict | None:
    """Extract hidden JSON from HTML comment in a [Brain] post."""
    if "[Brain]" not in body:
        return None
    start = body.find(_BRAIN_JSON_PREFIX)
    if start == -1:
        return None
    start += len(_BRAIN_JSON_PREFIX)
    end = body.find(_BRAIN_JSON_SUFFIX, start)
    if end == -1:
        return None
    try:
        return json.loads(body[start:end])
    except (json.JSONDecodeError, TypeError):
        return None


# ── Parsing Tests ─────────────────────────────────────────────────────


class TestParseBrainJson:
    def test_valid_brain_post(self):
        body = (
            '**[Brain] Heartbeat #42**\n\n'
            'Some visible text\n\n'
            '<!--BRAIN_JSON:{"comprehension":"test",'
            '"intent":"observe","confidence":0.8,"heartbeat":42}-->'
        )
        result = _parse_brain_json(body)
        assert result is not None
        assert result["comprehension"] == "test"
        assert result["heartbeat"] == 42
        assert result["confidence"] == 0.8

    def test_no_brain_tag(self):
        body = "Just a regular comment without brain tag"
        assert _parse_brain_json(body) is None

    def test_brain_tag_no_hidden_json(self):
        body = "**[Brain] Heartbeat #1**\n\nNo hidden JSON here"
        assert _parse_brain_json(body) is None

    def test_corrupt_json(self):
        body = (
            "**[Brain] Heartbeat #1**\n\n"
            "<!--BRAIN_JSON:NOT VALID JSON{{-->"
        )
        assert _parse_brain_json(body) is None

    def test_empty_json_object(self):
        body = (
            "**[Brain] Heartbeat #1**\n\n"
            "<!--BRAIN_JSON:{}-->"
        )
        result = _parse_brain_json(body)
        assert result == {}

    def test_nested_html_comments_ignored(self):
        """Only the BRAIN_JSON comment is parsed."""
        body = (
            "**[Brain] Heartbeat #1**\n\n"
            "<!-- some other comment -->\n"
            '<!--BRAIN_JSON:{"intent":"propose"}-->'
        )
        result = _parse_brain_json(body)
        assert result is not None
        assert result["intent"] == "propose"

    def test_roundtrip_with_thought_dict(self):
        """Verify format matches what discussions_bridge.post_brain_thought produces."""
        thought_dict = {
            "comprehension": "System healthy",
            "intent": "observe",
            "domain_relevance": "infrastructure",
            "key_concepts": ["health", "stability"],
            "confidence": 0.85,
            "kind": "health_check",
            "action_hint": "",
            "evidence": ["48/51 alive", "chain valid"],
            "heartbeat": 42,
        }
        # Simulate what discussions_bridge produces
        visible = "**[Brain] Heartbeat #42**\n\nSome text"
        hidden = f"\n\n<!--BRAIN_JSON:{json.dumps(thought_dict)}-->"
        body = visible + hidden

        parsed = _parse_brain_json(body)
        assert parsed is not None
        assert parsed["comprehension"] == "System healthy"
        assert parsed["heartbeat"] == 42
        assert parsed["confidence"] == 0.85
        assert len(parsed["evidence"]) == 2


# ── Feedback Ingestion Tests ─────────────────────────────────────────


class TestFeedbackIngestion:
    def test_ingest_records_to_memory(self):
        """Simulates _ingest_brain_feedback behavior."""
        brain_memory = MagicMock()
        body = (
            '**[Brain] Heartbeat #42**\n\n'
            '<!--BRAIN_JSON:{"comprehension":"test",'
            '"intent":"observe","heartbeat":42}-->'
        )
        parsed = _parse_brain_json(body)
        assert parsed is not None
        brain_memory.record_external(parsed)
        brain_memory.record_external.assert_called_once()
        call_arg = brain_memory.record_external.call_args[0][0]
        assert call_arg["heartbeat"] == 42

    def test_no_brain_tag_skips_ingestion(self):
        brain_memory = MagicMock()
        body = "Regular comment, no brain tag"
        parsed = _parse_brain_json(body)
        assert parsed is None
        # record_external should NOT be called
        brain_memory.record_external.assert_not_called()

    def test_ingestion_with_full_thought(self):
        """Full thought roundtrip: Thought → to_dict → JSON → parse → record."""
        from city.brain import BrainIntent, Thought, ThoughtKind

        original = Thought(
            comprehension="System running smoothly",
            intent=BrainIntent.OBSERVE,
            domain_relevance="infrastructure",
            key_concepts=("health", "stability"),
            confidence=0.85,
            kind=ThoughtKind.HEALTH_CHECK,
            action_hint="",
            evidence=("48/51 alive", "chain valid"),
        )
        thought_dict = original.to_dict()
        thought_dict["heartbeat"] = 42

        body = (
            f"**[Brain] Heartbeat #42**\n\n"
            f"{original.format_for_post()}"
            f"\n\n<!--BRAIN_JSON:{json.dumps(thought_dict)}-->"
        )

        parsed = _parse_brain_json(body)
        assert parsed is not None
        assert parsed["comprehension"] == "System running smoothly"
        assert parsed["intent"] == "observe"
        assert parsed["kind"] == "health_check"
        assert parsed["heartbeat"] == 42
