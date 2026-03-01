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
