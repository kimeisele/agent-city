"""
Tests for AgentSpec — guardian_spec.build_agent_spec() (Schritt 3).

Covers:
- Prana biology fields (prana_class, genesis_prana, metabolic_cost, max_age)
- Prana class resolution from agent_data
- Default fallback when prana_class missing
- All 4 prana classes (ephemeral, standard, resilient, immortal)
- AgentSpec completeness (all required fields present)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.guardian_spec import AgentSpec, build_agent_spec
from city.seed_constants import (
    GENESIS_PRANA_EPHEMERAL,
    GENESIS_PRANA_RESILIENT,
    GENESIS_PRANA_STANDARD,
    MAX_AGE_EPHEMERAL,
    MAX_AGE_RESILIENT,
    MAX_AGE_STANDARD,
    METABOLIC_COST,
)


def _make_agent_data(
    *,
    prana_class: str = "standard",
    guardian: str = "prahlada",
    guna: str = "RAJAS",
    element: str = "prithvi",
    quarter: str = "karma",
    claim_level: int = 1,
) -> dict:
    """Build minimal agent_data dict (like Pokedex._row_to_dict output)."""
    return {
        "address": 12345,
        "zone": "engineering",
        "classification": {
            "guna": guna,
            "quarter": quarter,
            "guardian": guardian,
            "position": 9,
            "holy_name": "K",
            "trinity_function": "carrier",
            "chapter": 5,
            "chapter_significance": "Karma Yoga",
        },
        "vibration": {
            "seed": 42,
            "element": element,
            "shruti": True,
            "frequency": 49,
        },
        "claim_level": claim_level,
        "prana_class": prana_class,
    }


# ── Prana Biology Tests ──────────────────────────────────────────────


class TestPranaBiology:
    def test_standard_prana_class(self):
        spec = build_agent_spec("test_agent", _make_agent_data(prana_class="standard"))
        assert spec["prana_class"] == "standard"
        assert spec["genesis_prana"] == GENESIS_PRANA_STANDARD
        assert spec["metabolic_cost"] == METABOLIC_COST
        assert spec["max_age"] == MAX_AGE_STANDARD

    def test_ephemeral_prana_class(self):
        spec = build_agent_spec("test_agent", _make_agent_data(prana_class="ephemeral"))
        assert spec["prana_class"] == "ephemeral"
        assert spec["genesis_prana"] == GENESIS_PRANA_EPHEMERAL
        assert spec["metabolic_cost"] == METABOLIC_COST
        assert spec["max_age"] == MAX_AGE_EPHEMERAL

    def test_resilient_prana_class(self):
        spec = build_agent_spec("test_agent", _make_agent_data(prana_class="resilient"))
        assert spec["prana_class"] == "resilient"
        assert spec["genesis_prana"] == GENESIS_PRANA_RESILIENT
        assert spec["metabolic_cost"] == METABOLIC_COST
        assert spec["max_age"] == MAX_AGE_RESILIENT

    def test_immortal_prana_class(self):
        spec = build_agent_spec("test_agent", _make_agent_data(prana_class="immortal"))
        assert spec["prana_class"] == "immortal"
        assert spec["genesis_prana"] == -1
        assert spec["metabolic_cost"] == 0
        assert spec["max_age"] == -1

    def test_missing_prana_class_defaults_standard(self):
        data = _make_agent_data()
        del data["prana_class"]
        spec = build_agent_spec("test_agent", data)
        assert spec["prana_class"] == "standard"
        assert spec["genesis_prana"] == GENESIS_PRANA_STANDARD

    def test_unknown_prana_class_defaults_standard(self):
        spec = build_agent_spec("test_agent", _make_agent_data(prana_class="nonexistent"))
        assert spec["genesis_prana"] == GENESIS_PRANA_STANDARD


# ── AgentSpec Completeness Tests ─────────────────────────────────────


class TestAgentSpecCompleteness:
    def test_all_required_fields_present(self):
        spec = build_agent_spec("test_agent", _make_agent_data())
        required_fields = [
            "name", "address", "zone", "domain", "element",
            "element_capabilities", "style", "guardian", "position",
            "opcode", "role", "is_quarter_head", "capability_protocol",
            "guardian_capabilities", "holy_name", "trinity_function",
            "chapter", "chapter_significance", "shruti", "frequency",
            "guna", "qos", "claim_level", "capability_tier",
            "tier_capabilities", "capabilities",
            "prana_class", "genesis_prana", "metabolic_cost", "max_age",
            "spec_source",
        ]
        for field in required_fields:
            assert field in spec, f"Missing field: {field}"

    def test_capabilities_merged_deduplicated(self):
        spec = build_agent_spec("test_agent", _make_agent_data())
        caps = spec["capabilities"]
        assert len(caps) == len(set(caps)), "Duplicate capabilities found"

    def test_cartridge_caps_take_priority(self):
        spec = build_agent_spec(
            "test_agent",
            _make_agent_data(),
            cartridge_caps=["custom_cap", "special_ability"],
        )
        assert spec["capabilities"][0] == "custom_cap"
        assert spec["capabilities"][1] == "special_ability"
        assert spec["spec_source"] == "cartridge"

    def test_jiva_fallback_source(self):
        spec = build_agent_spec("test_agent", _make_agent_data())
        assert spec["spec_source"] == "jiva_fallback"

    def test_guardian_mapping(self):
        spec = build_agent_spec("test_agent", _make_agent_data(guardian="vyasa"))
        assert spec["guardian"] == "vyasa"
        assert spec["position"] == 0
        assert spec["opcode"] == "SYS_WAKE"
        assert spec["capability_protocol"] == "parse"

    def test_guna_qos(self):
        spec = build_agent_spec("test_agent", _make_agent_data(guna="SATTVA"))
        assert spec["style"] == "contemplative"
        assert spec["qos"]["parallel"] is True
        assert spec["qos"]["io_policy"] == "read"
