"""
Tests for PathogenIndex + CityImmune ↔ CityReactor bridge.

The PathogenIndex is the Pokedex for code diseases:
pattern matching → remedy lookup, dynamic registration,
and wiring into the CityReactor nervous system.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest


# ===========================================================================
# PathogenIndex Tests
# ===========================================================================


class TestPathogenIndex:
    """Dynamic pathogen registry — Pokedex for code diseases."""

    def test_import(self):
        """PathogenIndex is importable."""
        from city.pathogen_index import PathogenIndex

    def test_register_and_lookup(self):
        """Register a pathogen pattern and look it up."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        idx.register(
            keyword="any_type",
            remedy_id="any_type_usage",
            severity="high",
            description="Untyped `Any` usage weakens type safety",
        )
        result = idx.lookup("Found any_type usage in foo.py")
        assert result is not None
        assert result.remedy_id == "any_type_usage"
        assert result.severity == "high"

    def test_lookup_case_insensitive(self):
        """Lookup is case-insensitive."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        idx.register(keyword="subprocess", remedy_id="subprocess_timeout")
        result = idx.lookup("SUBPROCESS call without timeout")
        assert result is not None
        assert result.remedy_id == "subprocess_timeout"

    def test_lookup_no_match(self):
        """Lookup returns None when no pathogen matches."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        result = idx.lookup("everything is fine")
        assert result is None

    def test_builtin_pathogens_loaded(self):
        """Default PathogenIndex ships with built-in pathogens."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        # Built-in pathogens from the old _PATTERN_TO_REMEDY
        assert idx.lookup("any_type usage") is not None
        assert idx.lookup("hardcoded constant") is not None
        assert idx.lookup("subprocess call") is not None

    def test_register_overwrites_same_keyword(self):
        """Registering same keyword again overwrites the entry."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        idx.register(keyword="test_bug", remedy_id="fix_v1")
        idx.register(keyword="test_bug", remedy_id="fix_v2")
        result = idx.lookup("test_bug found")
        assert result.remedy_id == "fix_v2"

    def test_list_pathogens(self):
        """List all registered pathogens."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        pathogens = idx.list_pathogens()
        assert isinstance(pathogens, list)
        assert len(pathogens) >= 5  # built-ins

    def test_stats(self):
        """Stats reports pathogen count."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        stats = idx.stats()
        assert stats["registered"] >= 5
        assert stats["lookups"] == 0
        idx.lookup("any_type")
        stats2 = idx.stats()
        assert stats2["lookups"] == 1

    def test_empty_index(self):
        """Empty index (no built-ins) works."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        assert idx.lookup("any_type") is None
        assert len(idx.list_pathogens()) == 0

    def test_pathogen_entry_dataclass(self):
        """PathogenEntry is a proper dataclass."""
        from city.pathogen_index import PathogenEntry

        entry = PathogenEntry(
            keyword="test",
            remedy_id="test_fix",
            severity="low",
            description="A test pathogen",
        )
        assert entry.keyword == "test"
        assert entry.severity == "low"

    def test_first_match_wins(self):
        """When multiple pathogens match, first registered wins."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        idx.register(keyword="type", remedy_id="type_fix")
        idx.register(keyword="any_type", remedy_id="any_type_fix")
        # "any_type" contains both "type" and "any_type"
        # "type" was registered first, so it should match first
        result = idx.lookup("any_type usage")
        assert result.remedy_id == "type_fix"

    def test_multiple_matches_all(self):
        """lookup_all returns all matching pathogens."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        idx.register(keyword="type", remedy_id="type_fix")
        idx.register(keyword="any_type", remedy_id="any_type_fix")
        results = idx.lookup_all("any_type usage")
        assert len(results) == 2


# ===========================================================================
# CityImmune ↔ CityReactor Bridge Tests
# ===========================================================================


class TestImmuneReactorBridge:
    """CityImmune registers PainRules with CityReactor."""

    def test_immune_pain_rule_on_test_failure(self):
        """TestFailureRule fires when test_failures metric exceeds threshold."""
        from city.pathogen_index import TestFailureRule
        from city.reactor import CityReactor

        reactor = CityReactor(rules=[])
        reactor.register_rule(TestFailureRule(threshold=3))

        # Below threshold — no pain
        reactor.record("test_failures", count=2)
        assert len(reactor.detect_pain()) == 0

        # At threshold — pain
        reactor.record("test_failures", count=5)
        intents = reactor.detect_pain()
        assert len(intents) == 1
        assert intents[0].signal == "test_failures_spike"

    def test_immune_pain_rule_on_heal_failure(self):
        """HealFailureRule fires when heal success rate drops."""
        from city.pathogen_index import HealFailureRule
        from city.reactor import CityReactor

        reactor = CityReactor(rules=[])
        reactor.register_rule(HealFailureRule(min_attempts=3, failure_rate=0.5))

        # Record heals: 3 failures out of 4 → 75% failure rate
        # Rule fires on 3rd record (100%) and again on 4th (75%)
        reactor.record("heal_outcome", count=0)  # failure
        reactor.record("heal_outcome", count=0)
        reactor.record("heal_outcome", count=0)
        reactor.record("heal_outcome", count=1)  # success

        intents = reactor.detect_pain()
        assert len(intents) >= 1
        assert all(i.signal == "heal_effectiveness_low" for i in intents)

    def test_security_violation_rule(self):
        """SecurityViolationRule fires on security scan findings."""
        from city.pathogen_index import SecurityViolationRule
        from city.reactor import CityReactor

        reactor = CityReactor(rules=[])
        reactor.register_rule(SecurityViolationRule())

        reactor.record("security_violations", count=1)
        intents = reactor.detect_pain()
        assert len(intents) == 1
        assert intents[0].signal == "security_violation"
        assert intents[0].priority == "critical"

    def test_immune_rules_coexist_with_builtin_rules(self):
        """Immune PainRules work alongside built-in metabolize/death rules."""
        from city.pathogen_index import SecurityViolationRule, TestFailureRule
        from city.reactor import CityReactor

        reactor = CityReactor()  # with built-in rules
        reactor.register_rule(TestFailureRule())
        reactor.register_rule(SecurityViolationRule())

        # Trigger built-in (metabolize slow) + immune (security)
        for _ in range(3):
            reactor.record("metabolize_all", duration_ms=600.0)
        reactor.record("security_violations", count=2)

        intents = reactor.detect_pain()
        signals = [i.signal for i in intents]
        assert "metabolize_slow" in signals
        assert "security_violation" in signals

    def test_connect_reactor_registers_immune_rules(self):
        """PathogenIndex.connect_reactor() wires all immune PainRules."""
        from city.pathogen_index import PathogenIndex
        from city.reactor import CityReactor

        idx = PathogenIndex()
        reactor = CityReactor()
        idx.connect_reactor(reactor)

        stats = reactor.stats()
        # Should have built-in rules + immune rules
        assert "test_failures_spike" in stats["rules"] or len(stats["rules"]) > 3
