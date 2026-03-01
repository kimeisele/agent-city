"""
Tests for CityAttention + CityReactor — the Agent City nervous system.

Issue #17 Stufe 2a/2b: O(1) intent routing + self-awareness.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pokedex(tmpdir: Path):
    """Minimal Pokedex for testing — mocks heavy deps."""
    from unittest.mock import MagicMock

    with patch("city.pokedex.CivicBank") as MockBank:
        MockBank.return_value = MagicMock()
        with patch("city.pokedex.get_config") as mock_cfg:
            mock_cfg.return_value = {
                "agent_classes": {
                    "standard": {"genesis_prana": 13700, "metabolic_cost": 3, "max_age": 432},
                    "ephemeral": {"genesis_prana": 1370, "metabolic_cost": 3, "max_age": 108},
                },
            }
            from city.pokedex import Pokedex

            return Pokedex(db_path=str(tmpdir / "city.db"), bank=MockBank())


# ===========================================================================
# CityAttention Tests (Stufe 2a)
# ===========================================================================


class TestCityAttention:
    """O(1) intent routing via MahaAttention."""

    def test_import(self):
        """CityAttention is importable."""
        from city.attention import CityAttention

    def test_register_and_route(self):
        """Register an intent handler and route to it in O(1)."""
        from city.attention import CityAttention

        attn = CityAttention()
        attn.register("metabolize_slow", "upgrade_prana_engine")
        result = attn.route("metabolize_slow")
        assert result == "upgrade_prana_engine"

    def test_route_unknown_returns_none(self):
        """Unknown intents return None, not crash."""
        from city.attention import CityAttention

        attn = CityAttention()
        assert attn.route("nonexistent_intent") is None

    def test_builtin_city_intents_registered(self):
        """CityAttention ships with built-in city intents."""
        from city.attention import CityAttention

        attn = CityAttention()
        # These should be pre-registered
        assert attn.route("metabolize_slow") is not None
        assert attn.route("zone_empty") is not None
        assert attn.route("agent_death_spike") is not None
        assert attn.route("contract_failing") is not None

    def test_register_callable_handler(self):
        """Handlers can be callables, not just strings."""
        from city.attention import CityAttention

        attn = CityAttention()
        handler = lambda ctx: "healed"
        attn.register("custom_pain", handler)
        result = attn.route("custom_pain")
        assert result is handler
        assert result(None) == "healed"

    def test_stats(self):
        """Stats reports registered intents and queries."""
        from city.attention import CityAttention

        attn = CityAttention()
        attn.route("metabolize_slow")
        attn.route("unknown_thing")
        stats = attn.stats()
        assert stats["queries"] >= 2
        assert stats["registered"] >= 4  # built-in intents

    def test_batch_route(self):
        """Batch routing resolves multiple intents at once."""
        from city.attention import CityAttention

        attn = CityAttention()
        results = attn.route_batch(["metabolize_slow", "zone_empty", "nonexistent"])
        assert len(results) == 3
        assert results[0] is not None  # metabolize_slow
        assert results[1] is not None  # zone_empty
        assert results[2] is None  # nonexistent


# ===========================================================================
# CityReactor Tests (Stufe 2b)
# ===========================================================================


class TestCityReactor:
    """Self-awareness: pain detection + intent generation."""

    def test_import(self):
        """CityReactor is importable."""
        from city.reactor import CityReactor

    def test_record_metric(self):
        """Record a phase metric without crash."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("metabolize_all", duration_ms=120.0, success=True)

    def test_no_pain_when_healthy(self):
        """No pain signals when metrics are healthy."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("metabolize_all", duration_ms=50.0, success=True)
        reactor.record("metabolize_all", duration_ms=45.0, success=True)
        intents = reactor.detect_pain()
        assert len(intents) == 0

    def test_pain_on_slow_metabolize(self):
        """Detects pain when metabolize_all is slow 3× in a row."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        # 3 consecutive slow runs
        reactor.record("metabolize_all", duration_ms=600.0, success=True)
        reactor.record("metabolize_all", duration_ms=700.0, success=True)
        reactor.record("metabolize_all", duration_ms=800.0, success=True)
        intents = reactor.detect_pain()
        signals = [i.signal for i in intents]
        assert "metabolize_slow" in signals

    def test_pain_on_agent_death_spike(self):
        """Detects pain when many agents die in one cycle."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("agent_deaths", count=8)
        intents = reactor.detect_pain()
        signals = [i.signal for i in intents]
        assert "agent_death_spike" in signals

    def test_pain_on_zone_empty(self):
        """Detects pain when a zone has 0 agents."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("zone_population", zones={"north": 5, "east": 0, "south": 3, "west": 2})
        intents = reactor.detect_pain()
        signals = [i.signal for i in intents]
        assert "zone_empty" in signals

    def test_pain_cleared_after_detect(self):
        """Pain signals are consumed (not repeated) after detection."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("agent_deaths", count=10)
        intents1 = reactor.detect_pain()
        assert len(intents1) > 0
        intents2 = reactor.detect_pain()
        assert len(intents2) == 0  # consumed

    def test_no_pain_on_single_slow_run(self):
        """A single slow run is not enough to trigger pain (need 3×)."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("metabolize_all", duration_ms=600.0, success=True)
        intents = reactor.detect_pain()
        assert "metabolize_slow" not in [i.signal for i in intents]

    def test_city_intent_dataclass(self):
        """CityIntent has signal, priority, and context."""
        from city.reactor import CityIntent

        intent = CityIntent(signal="test", priority="high", context={"key": "val"})
        assert intent.signal == "test"
        assert intent.priority == "high"
        assert intent.context == {"key": "val"}

    def test_stats(self):
        """Reactor reports stats."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        reactor.record("metabolize_all", duration_ms=50.0, success=True)
        stats = reactor.stats()
        assert stats["total_records"] >= 1
        assert "pain_detected" in stats


# ===========================================================================
# Integration: CityAttention + CityReactor
# ===========================================================================


class TestNervousSystemIntegration:
    """CityReactor generates intents → CityAttention routes them."""

    def test_reactor_to_attention_flow(self):
        """Full flow: record pain → detect → route → handler."""
        from city.attention import CityAttention
        from city.reactor import CityReactor

        reactor = CityReactor()
        attention = CityAttention()

        # Simulate slow metabolize 3×
        for _ in range(3):
            reactor.record("metabolize_all", duration_ms=700.0, success=True)

        # Detect pain
        intents = reactor.detect_pain()
        assert len(intents) > 0

        # Route each intent through attention
        for intent in intents:
            handler = attention.route(intent.signal)
            assert handler is not None, f"No handler for signal: {intent.signal}"

    def test_healthy_system_no_routing(self):
        """Healthy system: no pain, nothing to route."""
        from city.attention import CityAttention
        from city.reactor import CityReactor

        reactor = CityReactor()
        attention = CityAttention()

        reactor.record("metabolize_all", duration_ms=50.0, success=True)
        intents = reactor.detect_pain()
        assert len(intents) == 0

    def test_multiple_pain_sources(self):
        """Multiple pain sources generate multiple routable intents."""
        from city.attention import CityAttention
        from city.reactor import CityReactor

        reactor = CityReactor()
        attention = CityAttention()

        # Slow metabolize
        for _ in range(3):
            reactor.record("metabolize_all", duration_ms=600.0, success=True)
        # Death spike
        reactor.record("agent_deaths", count=10)
        # Empty zone
        reactor.record("zone_population", zones={"north": 0, "east": 5, "south": 3, "west": 2})

        intents = reactor.detect_pain()
        assert len(intents) >= 3

        # All should be routable
        for intent in intents:
            handler = attention.route(intent.signal)
            assert handler is not None


# ===========================================================================
# Pluggable PainRule Tests (Immune System)
# ===========================================================================


class TestPainRuleProtocol:
    """Pluggable pain rules — the city's adaptive immune system."""

    def test_custom_rule_registration(self):
        """Custom PainRules can be registered and triggered."""
        from city.reactor import CityIntent, CityReactor, MetricStore, PainRule

        class HighLatencyRule(PainRule):
            @property
            def name(self):
                return "api_latency_high"

            @property
            def listens_to(self):
                return ("api_latency",)

            def evaluate(self, metric, store, **kwargs):
                ms = kwargs.get("duration_ms", 0)
                if ms > 1000:
                    return CityIntent(signal="api_latency_high", priority="high",
                                      context={"ms": ms})
                return None

        reactor = CityReactor()
        reactor.register_rule(HighLatencyRule())

        # Should not trigger on fast API
        reactor.record("api_latency", duration_ms=50.0)
        assert len(reactor.detect_pain()) == 0

        # Should trigger on slow API
        reactor.record("api_latency", duration_ms=1500.0)
        intents = reactor.detect_pain()
        assert len(intents) == 1
        assert intents[0].signal == "api_latency_high"
        assert intents[0].context["ms"] == 1500.0

    def test_rule_replacement(self):
        """Registering a rule with the same name replaces the old one."""
        from city.reactor import CityReactor, MetabolizeSlowRule

        reactor = CityReactor()

        # Replace built-in with stricter threshold
        strict = MetabolizeSlowRule(threshold_ms=100.0, consecutive=2)
        reactor.register_rule(strict)

        # 2× over 100ms should now trigger (was 3× over 500ms)
        reactor.record("metabolize_all", duration_ms=150.0)
        reactor.record("metabolize_all", duration_ms=200.0)
        intents = reactor.detect_pain()
        assert any(i.signal == "metabolize_slow" for i in intents)

    def test_empty_reactor_no_rules(self):
        """Reactor with no rules never produces pain."""
        from city.reactor import CityReactor

        reactor = CityReactor(rules=[])
        reactor.record("metabolize_all", duration_ms=9999.0)
        reactor.record("agent_deaths", count=100)
        assert len(reactor.detect_pain()) == 0

    def test_stats_lists_all_rules(self):
        """Stats include names of all registered rules."""
        from city.reactor import CityReactor

        reactor = CityReactor()
        stats = reactor.stats()
        assert "metabolize_slow" in stats["rules"]
        assert "agent_death_spike" in stats["rules"]
        assert "zone_empty" in stats["rules"]

    def test_rule_error_does_not_crash_reactor(self):
        """A broken rule logs an error but doesn't crash the reactor."""
        from city.reactor import CityIntent, CityReactor, MetricStore, PainRule

        class BrokenRule(PainRule):
            @property
            def name(self):
                return "broken"

            @property
            def listens_to(self):
                return ("metabolize_all",)

            def evaluate(self, metric, store, **kwargs):
                raise RuntimeError("I'm broken")

        reactor = CityReactor()
        reactor.register_rule(BrokenRule())

        # Should not crash — broken rule is caught
        reactor.record("metabolize_all", duration_ms=600.0)
        reactor.record("metabolize_all", duration_ms=600.0)
        reactor.record("metabolize_all", duration_ms=600.0)

        # Built-in metabolize_slow should still fire despite broken rule
        intents = reactor.detect_pain()
        signals = [i.signal for i in intents]
        assert "metabolize_slow" in signals

    def test_multi_metric_rule(self):
        """A single rule can listen to multiple metrics."""
        from city.reactor import CityIntent, CityReactor, MetricStore, PainRule

        class ComboRule(PainRule):
            @property
            def name(self):
                return "system_overload"

            @property
            def listens_to(self):
                return ("cpu_usage", "memory_usage")

            def evaluate(self, metric, store, **kwargs):
                pct = kwargs.get("count", 0)
                if pct > 90:
                    return CityIntent(signal="system_overload", priority="critical",
                                      context={"metric": metric, "pct": pct})
                return None

        reactor = CityReactor(rules=[])  # no built-ins
        reactor.register_rule(ComboRule())

        # Trigger via cpu_usage
        reactor.record("cpu_usage", count=95)
        intents = reactor.detect_pain()
        assert len(intents) == 1
        assert intents[0].context["metric"] == "cpu_usage"

        # Trigger via memory_usage
        reactor.record("memory_usage", count=92)
        intents = reactor.detect_pain()
        assert len(intents) == 1
        assert intents[0].context["metric"] == "memory_usage"

    def test_custom_rule_with_attention_routing(self):
        """Custom rule + custom attention handler = end-to-end."""
        from city.attention import CityAttention
        from city.reactor import CityIntent, CityReactor, MetricStore, PainRule

        class DiskFullRule(PainRule):
            @property
            def name(self):
                return "disk_full"

            @property
            def listens_to(self):
                return ("disk_usage",)

            def evaluate(self, metric, store, **kwargs):
                pct = kwargs.get("count", 0)
                if pct > 95:
                    return CityIntent(signal="disk_full", priority="critical")
                return None

        reactor = CityReactor()
        reactor.register_rule(DiskFullRule())

        attention = CityAttention()
        attention.register("disk_full", "emergency_cleanup")

        # Trigger
        reactor.record("disk_usage", count=98)
        intents = reactor.detect_pain()
        assert len(intents) == 1

        handler = attention.route(intents[0].signal)
        assert handler == "emergency_cleanup"


class TestMetricStore:
    """MetricStore rolling window tests."""

    def test_series_append_and_read(self):
        """Append values and read them back."""
        from city.reactor import MetricStore

        store = MetricStore(window=5)
        for i in range(3):
            store.append("test", i)
        assert store.series("test") == [0, 1, 2]

    def test_series_window_eviction(self):
        """Old values evicted when window is full."""
        from city.reactor import MetricStore

        store = MetricStore(window=3)
        for i in range(5):
            store.append("test", i)
        assert store.series("test") == [2, 3, 4]

    def test_last_n(self):
        """last_n returns exactly N most recent values."""
        from city.reactor import MetricStore

        store = MetricStore()
        for i in range(7):
            store.append("m", i)
        assert store.last_n("m", 3) == [4, 5, 6]
        assert store.last_n("m", 100) == []  # not enough data

    def test_latest_snapshot(self):
        """set_latest / latest stores and retrieves snapshots."""
        from city.reactor import MetricStore

        store = MetricStore()
        store.set_latest("zones", {"north": 5, "east": 0})
        assert store.latest("zones") == {"north": 5, "east": 0}
        assert store.latest("nonexistent") is None

    def test_empty_series(self):
        """Unknown metric returns empty list."""
        from city.reactor import MetricStore

        store = MetricStore()
        assert store.series("unknown") == []
