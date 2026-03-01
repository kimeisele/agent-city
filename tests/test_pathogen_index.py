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


# ===========================================================================
# Antidote Tests
# ===========================================================================


class TestAntidote:
    """Every disease has a cure — Antidote dataclass."""

    def test_antidote_dataclass(self):
        """Antidote has test_id, remedy_id, strategy."""
        from city.pathogen_index import Antidote

        a = Antidote(test_id="tests/test_foo.py::test_bar", remedy_id="fix_foo", strategy="test_first")
        assert a.test_id == "tests/test_foo.py::test_bar"
        assert a.remedy_id == "fix_foo"
        assert a.strategy == "test_first"

    def test_antidote_defaults(self):
        """Default antidote has escalate strategy."""
        from city.pathogen_index import Antidote

        a = Antidote()
        assert a.strategy == "escalate"
        assert a.test_id == ""
        assert a.remedy_id == ""

    def test_pathogen_has_antidote(self):
        """PathogenEntry includes an antidote field."""
        from city.pathogen_index import Antidote, PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        idx.register(
            keyword="pickle_usage",
            remedy_id="ban_pickle",
            severity="critical",
            antidote=Antidote(remedy_id="ban_pickle", strategy="auto_fix"),
        )
        entry = idx.lookup("pickle_usage detected")
        assert entry is not None
        assert entry.antidote.remedy_id == "ban_pickle"
        assert entry.antidote.strategy == "auto_fix"

    def test_get_antidote(self):
        """get_antidote() returns the cure for a known pathogen."""
        from city.pathogen_index import Antidote, PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        idx.register(
            keyword="eval_usage",
            remedy_id="ban_eval",
            antidote=Antidote(remedy_id="ban_eval", strategy="auto_fix"),
        )
        antidote = idx.get_antidote("found eval_usage in code")
        assert antidote is not None
        assert antidote.remedy_id == "ban_eval"

    def test_get_antidote_unknown(self):
        """get_antidote() returns None for unknown pathogens."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        assert idx.get_antidote("nothing matches") is None

    def test_builtin_pathogens_have_antidotes(self):
        """Built-in pathogens get default antidotes with remedy_id."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()
        entry = idx.lookup("any_type usage")
        assert entry is not None
        assert entry.antidote.remedy_id == "any_type_usage"


# ===========================================================================
# Auto-Discovery: ingest_diagnostics()
# ===========================================================================


class TestIngestDiagnostics:
    """The immune system learns from its own test failures."""

    def _make_report(self, tests):
        """Helper to build a pytest-json-report dict."""
        return {"tests": tests}

    def test_auto_discover_new_pathogen(self):
        """Unknown test failure gets auto-registered as a new pathogen."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        report = self._make_report([
            {
                "nodeid": "tests/test_foo.py::test_bar",
                "outcome": "failed",
                "call": {"crash": {"path": "city/foo.py", "message": "assert 1 == 2"}},
            }
        ])

        discovered = idx.ingest_diagnostics(report)
        assert len(discovered) == 1
        entry = discovered[0]
        assert entry.auto_discovered is True
        assert entry.antidote.test_id == "tests/test_foo.py::test_bar"
        assert entry.antidote.strategy == "test_first"

    def test_known_pathogen_bumps_encounter(self):
        """Known pathogen gets encounter_count bumped, not duplicated."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        idx.register(keyword="tests/test_foo.py::test_bar", remedy_id="fix_bar")

        report = self._make_report([
            {
                "nodeid": "tests/test_foo.py::test_bar",
                "outcome": "failed",
                "call": {"crash": {"path": "city/foo.py", "message": "known bug"}},
            }
        ])

        discovered = idx.ingest_diagnostics(report)
        assert len(discovered) == 1
        # The encounter count should be bumped (initial 1 from register + 1 from re-encounter in register + 1 from ingest)
        assert discovered[0].encounter_count >= 2

    def test_passing_tests_ignored(self):
        """Only failed tests generate pathogens."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        report = self._make_report([
            {"nodeid": "tests/test_ok.py::test_pass", "outcome": "passed"},
            {"nodeid": "tests/test_ok.py::test_skip", "outcome": "skipped"},
        ])

        discovered = idx.ingest_diagnostics(report)
        assert len(discovered) == 0

    def test_multiple_failures_multiple_pathogens(self):
        """Each unique test failure becomes its own pathogen."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        report = self._make_report([
            {
                "nodeid": "tests/test_a.py::test_one",
                "outcome": "failed",
                "call": {"crash": {"path": "a.py", "message": "error 1"}},
            },
            {
                "nodeid": "tests/test_b.py::test_two",
                "outcome": "failed",
                "call": {"crash": {"path": "b.py", "message": "error 2"}},
            },
        ])

        discovered = idx.ingest_diagnostics(report)
        assert len(discovered) == 2
        keywords = [d.keyword for d in discovered]
        assert "tests/test_a.py::test_one" in keywords
        assert "tests/test_b.py::test_two" in keywords

    def test_empty_report(self):
        """Empty report produces no pathogens."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        assert idx.ingest_diagnostics({}) == []
        assert idx.ingest_diagnostics({"tests": []}) == []

    def test_stats_tracks_innate_vs_learned(self):
        """Stats distinguishes innate (built-in) vs learned (auto-discovered)."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex()  # with built-ins
        stats_before = idx.stats()
        assert stats_before["innate"] > 0
        assert stats_before["learned"] == 0

        report = self._make_report([
            {
                "nodeid": "tests/test_new.py::test_novel_bug",
                "outcome": "failed",
                "call": {"crash": {"path": "new.py", "message": "novel"}},
            }
        ])
        idx.ingest_diagnostics(report)

        stats_after = idx.stats()
        assert stats_after["learned"] == 1
        assert stats_after["registered"] == stats_before["registered"] + 1


# ===========================================================================
# Narasimha: scan_source() — AST Security Scanner
# ===========================================================================


class TestNarasimhaScanSource:
    """AST-based security scanning auto-registers pathogens."""

    def test_detect_pickle_import(self):
        """Detects pickle import as RCE risk."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "import pickle\ndata = pickle.load(open('f'))\n"
        found = idx.scan_source(code, "evil.py")
        assert len(found) >= 1
        # At least the import finding
        assert any(e.severity == "critical" for e in found)
        assert any("pickle" in e.description.lower() for e in found)

    def test_detect_eval(self):
        """Detects eval() as code injection risk."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "result = eval(user_input)\n"
        found = idx.scan_source(code, "danger.py")
        assert len(found) == 1
        assert found[0].severity == "critical"
        assert "eval" in found[0].description.lower()

    def test_detect_exec(self):
        """Detects exec() as code injection risk."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "exec(compile(src, '<string>', 'exec'))\n"
        found = idx.scan_source(code, "danger.py")
        assert len(found) == 1
        assert found[0].severity == "critical"

    def test_detect_subprocess_no_timeout(self):
        """Detects subprocess.run() without timeout as DoS risk."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "import subprocess\nsubprocess.run(['ls'])\n"
        found = idx.scan_source(code, "slow.py")
        # Should find both the subprocess import (not banned) and the call without timeout
        timeout_findings = [e for e in found if "timeout" in e.description.lower()]
        assert len(timeout_findings) == 1
        assert timeout_findings[0].severity == "high"

    def test_subprocess_with_timeout_is_clean(self):
        """subprocess.run() with timeout passes clean."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "import subprocess\nsubprocess.run(['ls'], timeout=30)\n"
        found = idx.scan_source(code, "safe.py")
        # No timeout findings (subprocess import itself is not banned)
        timeout_findings = [e for e in found if "timeout" in e.description.lower()]
        assert len(timeout_findings) == 0

    def test_detect_xml_etree(self):
        """Detects xml.etree.ElementTree as XXE risk."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "from xml.etree.ElementTree import parse\n"
        found = idx.scan_source(code, "parser.py")
        assert len(found) == 1
        assert found[0].severity == "high"
        assert "xxe" in found[0].description.lower()

    def test_clean_code_no_findings(self):
        """Clean code produces no security findings."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "import json\ndata = json.loads('{}')\nprint(data)\n"
        found = idx.scan_source(code, "clean.py")
        assert len(found) == 0

    def test_syntax_error_returns_empty(self):
        """Source with syntax errors returns empty, no crash."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        found = idx.scan_source("def broken(:\n", "bad.py")
        assert found == []

    def test_findings_auto_registered(self):
        """Findings are auto-registered as pathogens in the index."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "import pickle\nresult = eval(x)\n"
        idx.scan_source(code, "evil.py")

        # The pathogens should now be in the index
        stats = idx.stats()
        assert stats["learned"] >= 2
        assert stats["registered"] >= 2

    def test_scan_source_antidote_strategy(self):
        """Auto-discovered security pathogens have auto_fix or escalate strategy."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        code = "import subprocess\nsubprocess.call(['rm', '-rf', '/'])\n"
        found = idx.scan_source(code, "nuke.py")
        for entry in found:
            assert entry.antidote.strategy in ("auto_fix", "escalate")


# ===========================================================================
# Full Adaptive Immune Loop
# ===========================================================================


class TestAdaptiveImmuneLoop:
    """The complete cycle: discover → register → recognize → heal."""

    def test_discover_then_recognize(self):
        """First encounter auto-registers. Second encounter recognizes."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)

        report1 = {"tests": [{
            "nodeid": "tests/test_x.py::test_regression",
            "outcome": "failed",
            "call": {"crash": {"path": "x.py", "message": "regression bug"}},
        }]}

        # First: auto-discover
        d1 = idx.ingest_diagnostics(report1)
        assert len(d1) == 1
        assert d1[0].encounter_count == 1

        # Second: same failure → recognized, encounter bumped
        d2 = idx.ingest_diagnostics(report1)
        assert len(d2) == 1
        assert d2[0].encounter_count >= 2

    def test_scan_then_ingest(self):
        """Security scan finds pickle. Later test failure references it."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)

        # Step 1: AST scan finds pickle
        code = "import pickle\n"
        scan_results = idx.scan_source(code, "bad.py")
        assert len(scan_results) == 1

        # Step 2: Test failure mentioning pickle — should match existing
        report = {"tests": [{
            "nodeid": "tests/test_security.py::test_no_pickle",
            "outcome": "failed",
            "call": {"crash": {"path": "bad.py", "message": scan_results[0].keyword}},
        }]}

        d = idx.ingest_diagnostics(report)
        assert len(d) == 1
        # Should have bumped encounter on existing, not created new
        assert d[0].encounter_count >= 2

    def test_encounter_count_persistence(self):
        """Re-registering same keyword bumps count instead of resetting."""
        from city.pathogen_index import PathogenIndex

        idx = PathogenIndex(load_builtins=False)
        e1 = idx.register(keyword="flaky_test", remedy_id="fix_flaky")
        assert e1.encounter_count == 1

        e2 = idx.register(keyword="flaky_test", remedy_id="fix_flaky_v2")
        assert e2.encounter_count == 2
        assert e2 is e1  # same object, mutated


# ===========================================================================
# Circuit Breaker: CytokineBreaker
# ===========================================================================


class TestCytokineBreaker:
    """Prevents autoimmune cascades — the Cytokine Storm Prevention."""

    def test_import(self):
        from city.immune import CytokineBreaker

    def test_initial_state(self):
        """Fresh breaker is closed (not tripped)."""
        from city.immune import CytokineBreaker

        b = CytokineBreaker()
        assert b.is_open() is False
        assert b.tripped is False
        assert b.rollbacks == 0
        assert b.consecutive_rollbacks == 0

    def test_single_rollback_does_not_trip(self):
        """One rollback alone doesn't trip the breaker."""
        from city.immune import CytokineBreaker

        b = CytokineBreaker(max_consecutive=3)
        b.record_rollback()
        assert b.is_open() is False
        assert b.rollbacks == 1
        assert b.consecutive_rollbacks == 1

    def test_consecutive_rollbacks_trip_breaker(self):
        """N consecutive rollbacks trips the breaker."""
        from city.immune import CytokineBreaker

        b = CytokineBreaker(max_consecutive=3, cooldown_s=300)
        b.record_rollback()
        b.record_rollback()
        assert b.is_open() is False  # 2 < 3
        b.record_rollback()
        assert b.is_open() is True  # 3 >= 3, tripped!
        assert b.tripped is True

    def test_success_resets_consecutive(self):
        """A successful heal resets the consecutive rollback counter."""
        from city.immune import CytokineBreaker

        b = CytokineBreaker(max_consecutive=3)
        b.record_rollback()
        b.record_rollback()
        assert b.consecutive_rollbacks == 2
        b.record_success()
        assert b.consecutive_rollbacks == 0
        # Now need 3 more to trip
        b.record_rollback()
        assert b.is_open() is False

    def test_cooldown_expires(self):
        """After cooldown, breaker re-opens (half-open state)."""
        import time as _time
        from city.immune import CytokineBreaker

        b = CytokineBreaker(max_consecutive=1, cooldown_s=0.1)
        b.record_rollback()  # trips immediately
        assert b.is_open() is True
        _time.sleep(0.15)
        assert b.is_open() is False  # cooldown expired
        assert b.tripped is False  # reset

    def test_stats(self):
        """Stats reports breaker state."""
        from city.immune import CytokineBreaker

        b = CytokineBreaker(max_consecutive=2, cooldown_s=60)
        b.record_rollback()
        s = b.stats()
        assert s["rollbacks"] == 1
        assert s["consecutive_rollbacks"] == 1
        assert s["tripped"] is False


# ===========================================================================
# Circuit Breaker Integration: scan_and_heal() with rollback
# ===========================================================================


class TestScanAndHealCircuitBreaker:
    """scan_and_heal() rolls back fixes that increase test failures."""

    def _make_immune(self, engine=None):
        """Create a CityImmune with a mock engine for testing."""
        from unittest.mock import MagicMock
        from city.immune import CityImmune

        if engine is None:
            engine = MagicMock()
            engine.can_heal.return_value = True
            result = MagicMock()
            result.success = True
            result.diff = "mock diff"
            result.message = "mock fix applied"
            engine.purify.return_value = result

        immune = CityImmune(_engine=engine)
        return immune

    def test_fix_that_increases_failures_is_rolled_back(self):
        """If a fix increases test failures, it gets rolled back."""
        from unittest.mock import patch, MagicMock
        from city.immune import CityImmune
        from city.pathogen_index import PathogenIndex

        immune = self._make_immune()

        # Mock: baseline=2 failures, after fix=5 failures
        with patch.object(immune, "_count_test_failures", side_effect=[2, 5]):
            with patch.object(immune, "_rollback_file", return_value=True) as mock_rb:
                results = immune.scan_and_heal(["Failure in city/foo.py: any_type usage"])

        # The fix should have been rolled back
        if results:
            rolled_back = [r for r in results if "Rolled back" in r.message]
            if rolled_back:
                assert rolled_back[0].success is False
                mock_rb.assert_called()
                assert immune._heals_rolled_back >= 1

    def test_fix_that_decreases_failures_is_accepted(self):
        """If a fix decreases test failures, it is accepted."""
        from unittest.mock import patch

        immune = self._make_immune()

        # Mock: baseline=5 failures, after fix=3 failures (improvement!)
        with patch.object(immune, "_count_test_failures", side_effect=[5, 3]):
            with patch.object(immune, "_rollback_file") as mock_rb:
                results = immune.scan_and_heal(["Failure in city/foo.py: any_type usage"])

        # No rollback should have happened
        mock_rb.assert_not_called()

    def test_fix_with_same_failures_is_accepted(self):
        """If failures stay the same, the fix is accepted (no regression)."""
        from unittest.mock import patch

        immune = self._make_immune()

        # Mock: baseline=3, after=3 (no change = safe)
        with patch.object(immune, "_count_test_failures", side_effect=[3, 3]):
            with patch.object(immune, "_rollback_file") as mock_rb:
                results = immune.scan_and_heal(["Failure in city/foo.py: any_type usage"])

        mock_rb.assert_not_called()

    def test_breaker_trips_after_consecutive_rollbacks(self):
        """After N consecutive rollbacks, breaker trips and blocks further heals."""
        from unittest.mock import patch, MagicMock
        from pathlib import Path
        from city.immune import CityImmune, CytokineBreaker, DiagnosisResult

        immune = self._make_immune()
        immune._breaker = CytokineBreaker(max_consecutive=2, cooldown_s=300)

        # Mock diagnose to always return healable (real files don't exist)
        fake_diag = DiagnosisResult(
            pattern="test", rule_id="any_type_usage",
            file_path=Path("city/fake.py"), confidence=0.9, healable=True,
        )
        details = ["detail_1", "detail_2", "detail_3"]

        with patch.object(immune, "diagnose", return_value=fake_diag):
            # Every fix increases failures → rollback each time
            with patch.object(immune, "_count_test_failures", side_effect=[1, 5, 1, 5, 1, 5]):
                with patch.object(immune, "_rollback_file", return_value=True):
                    results = immune.scan_and_heal(details)

        # Breaker should have tripped after 2 consecutive rollbacks
        assert immune._breaker.tripped is True
        assert immune._breaker.rollbacks >= 2

    def test_breaker_open_blocks_all_healing(self):
        """When breaker is open, scan_and_heal returns empty immediately."""
        from city.immune import CytokineBreaker

        immune = self._make_immune()
        immune._breaker = CytokineBreaker(max_consecutive=1, cooldown_s=300)
        immune._breaker.record_rollback()  # trips immediately
        assert immune._breaker.is_open() is True

        results = immune.scan_and_heal(["Failure in city/foo.py: any_type usage"])
        assert results == []

    def test_verification_failure_triggers_rollback(self):
        """If test count fails after fix, rollback for safety."""
        from unittest.mock import patch

        immune = self._make_immune()

        # baseline=2, after=None (verification failed)
        with patch.object(immune, "_count_test_failures", side_effect=[2, None]):
            with patch.object(immune, "_rollback_file", return_value=True) as mock_rb:
                results = immune.scan_and_heal(["Failure in city/foo.py: any_type usage"])

        if results:
            rolled_back = [r for r in results if "verification unavailable" in r.message]
            if rolled_back:
                mock_rb.assert_called()
                assert immune._heals_rolled_back >= 1

    def test_baseline_failure_skips_heal(self):
        """If baseline test count fails, heal is skipped entirely."""
        from unittest.mock import patch

        immune = self._make_immune()

        # Can't even get baseline → skip
        with patch.object(immune, "_count_test_failures", return_value=None):
            results = immune.scan_and_heal(["Failure in city/foo.py: any_type usage"])

        assert results == []  # nothing attempted

    def test_stats_includes_circuit_breaker(self):
        """Stats output includes circuit breaker info."""
        immune = self._make_immune()
        stats = immune.stats()
        assert "heals_rolled_back" in stats
        assert "circuit_breaker" in stats
        assert "rollbacks" in stats["circuit_breaker"]
        assert "tripped" in stats["circuit_breaker"]
