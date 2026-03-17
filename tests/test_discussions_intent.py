"""
Tests for discussions_intent — Intent-routed discussion responses.

Each intent handler returns deterministic city data. No LLM.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from city.discussions_intent import (
    classify_and_respond,
    respond_contribution,
    respond_fallback,
    respond_federation,
    respond_governance,
    respond_immigration,
    respond_population,
)


# ── Fake Context ─────────────────────────────────────────────────────


class FakePokedex:
    def stats(self):
        return {
            "total": 37,
            "active": 32,
            "citizen": 0,
            "discovered": 5,
            "zones": {"engineering": 13, "research": 10, "discovery": 8, "governance": 6},
        }


class FakeImmigration:
    def stats(self):
        return {
            "total_visas": 7,
            "citizenship_granted": 6,
            "pending_applications": 0,
        }


class FakeCouncil:
    seats = {0: "sys_artisan", 1: "sys_oracle", 2: "sys_supreme_court"}
    elected_mayor = "sys_artisan"


def _ctx():
    ctx = SimpleNamespace()
    ctx.heartbeat_count = 200
    ctx.pokedex = FakePokedex()
    ctx.immigration = FakeImmigration()
    ctx.council = FakeCouncil()
    return ctx


# ── Handler Tests ────────────────────────────────────────────────────


def test_respond_population():
    result = respond_population(_ctx())
    assert "37 agents" in result
    assert "32 citizens" in result
    assert "engineering" in result


def test_respond_immigration():
    result = respond_immigration(_ctx())
    assert "6 citizenships granted" in result
    assert "registration Issue" in result
    assert "Jiva" in result


def test_respond_governance():
    result = respond_governance(_ctx())
    assert "3 seats filled" in result
    assert "sys_artisan" in result
    assert "Elections" in result


def test_respond_contribution():
    result = respond_contribution(_ctx())
    assert "help-wanted" in result
    assert "#136" in result or "#137" in result or "#138" in result


def test_respond_federation():
    result = respond_federation(_ctx())
    assert "NADI" in result
    assert "agent-template" in result


def test_respond_fallback():
    result = respond_fallback(_ctx())
    assert "37 agents" in result
    assert "registration Issue" in result


# ── classify_and_respond routing ─────────────────────────────────────


def test_classify_immigration():
    result = classify_and_respond(_ctx(), "How does immigration work?")
    assert "citizenships granted" in result


def test_classify_population():
    result = classify_and_respond(_ctx(), "What is the current population?")
    assert "37 agents" in result
    assert "zones" in result.lower()


def test_classify_governance():
    result = classify_and_respond(_ctx(), "How do elections work?")
    assert "seats filled" in result


def test_classify_contribution():
    result = classify_and_respond(_ctx(), "What tasks can I help with?")
    assert "help-wanted" in result


def test_classify_federation():
    result = classify_and_respond(_ctx(), "Tell me about the federation protocol")
    assert "NADI" in result


def test_classify_fallback():
    result = classify_and_respond(_ctx(), "Hello, just checking things out")
    assert "37 agents" in result
