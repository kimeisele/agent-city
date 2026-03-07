"""
Tests for Sankirtan Adaptation — Provider Cells in the Real Chamber.

Verifies that:
- Provider cells are REAL MahaCellUnified from steward-protocol
- Provider prana and integrity behave per substrate rules
- Provider selection respects prana ordering (free first)
- Failover reduces integrity, not just skipping
- Daily reset refreshes all providers
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from vibe_core.mahamantra.protocols._seed import COSMIC_FRAME, MAHA_QUANTUM
from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

from steward.provider import (
    ProviderChamber,
    ProviderPayload,
    _AdapterResponse,
    GoogleAdapter,
    _PRANA_CHEAP,
    _PRANA_FREE,
    _is_valid_key,
    build_chamber,
)


# ── Helpers ──────────────────────────────────────────────────────────────


@dataclass
class FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 20


@dataclass
class FakeResponse:
    content: str = '{"comprehension":"test"}'
    usage: FakeUsage | None = None

    def __post_init__(self):
        if self.usage is None:
            self.usage = FakeUsage()


class FakeProvider:
    def __init__(self, response: FakeResponse | None = None):
        self._response = response or FakeResponse()
        self.calls: list[dict] = []

    def invoke(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self._response


class FailingProvider:
    def invoke(self, **kwargs: Any) -> Any:
        raise RuntimeError("provider down")


# ── Provider cells are REAL MahaCellUnified ──────────────────────────────


class TestProviderCellsAreReal:
    """Verify cells are the real substrate, not fake reinventions."""

    def test_cell_is_real_mahacell(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="test", provider=FakeProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        cell = chamber._cells[0]
        assert isinstance(cell, MahaCellUnified), (
            "Provider cell MUST be a real MahaCellUnified from steward-protocol"
        )

    def test_cell_has_real_header(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="test", provider=FakeProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        cell = chamber._cells[0]
        assert cell.header.is_valid(), "Cell header MUST pass parampara validation"
        assert cell.header.sravanam == MAHA_QUANTUM * 10

    def test_cell_has_real_lifecycle(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="test", provider=FakeProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        cell = chamber._cells[0]
        assert cell.lifecycle.prana == _PRANA_FREE
        assert cell.lifecycle.integrity == COSMIC_FRAME
        assert cell.lifecycle.is_active

    def test_cell_payload_is_provider(self):
        chamber = ProviderChamber()
        provider = FakeProvider()
        chamber.add_provider(
            name="google", provider=provider, model="gemini-2.5-flash",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        cell = chamber._cells[0]
        assert isinstance(cell.payload, ProviderPayload)
        assert cell.payload.name == "google"
        assert cell.payload.model == "gemini-2.5-flash"
        assert cell.payload.provider is provider


# ── Prana Constants SSOT ─────────────────────────────────────────────────


class TestPranaConstants:
    def test_free_prana_is_genesis(self):
        assert _PRANA_FREE == MAHA_QUANTUM * 100, "Free provider prana MUST be SSOT-derived"

    def test_cheap_prana_is_ephemeral(self):
        assert _PRANA_CHEAP == MAHA_QUANTUM * 10, "Paid provider prana MUST be SSOT-derived"

    def test_free_has_more_prana_than_paid(self):
        assert _PRANA_FREE > _PRANA_CHEAP, "Free providers MUST have higher prana than paid"


# ── Provider Selection ───────────────────────────────────────────────────


class TestProviderSelection:
    def test_empty_chamber_returns_none(self):
        chamber = ProviderChamber()
        result = chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        assert result is None

    def test_single_provider_success(self):
        chamber = ProviderChamber()
        provider = FakeProvider()
        chamber.add_provider(
            name="test", provider=provider, model="m1",
            source_address=MAHA_QUANTUM * 10,
        )
        result = chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        assert result is not None
        assert result.content == '{"comprehension":"test"}'
        assert len(provider.calls) == 1

    def test_uses_cell_model_not_caller(self):
        """Chamber MUST use cell's model — caller doesn't know which provider handles it."""
        chamber = ProviderChamber()
        provider = FakeProvider()
        chamber.add_provider(
            name="google", provider=provider, model="gemini-2.5-flash",
            source_address=MAHA_QUANTUM * 10,
        )
        chamber.invoke(
            messages=[{"role": "user", "content": "hi"}],
            model="deepseek/deepseek-v3.2",
        )
        assert provider.calls[0]["model"] == "gemini-2.5-flash"

    def test_highest_prana_goes_first(self):
        """Free provider (high prana) is tried before paid (low prana)."""
        chamber = ProviderChamber()
        paid = FakeProvider()
        free = FakeProvider()
        chamber.add_provider(
            name="paid", provider=paid, model="m1",
            source_address=MAHA_QUANTUM * 12, prana=_PRANA_CHEAP,
        )
        chamber.add_provider(
            name="free", provider=free, model="m2",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        assert len(free.calls) == 1, "Free (high prana) should be tried first"
        assert len(paid.calls) == 0, "Paid (low prana) should not be reached"


# ── Failover ─────────────────────────────────────────────────────────────


class TestFailover:
    def test_failover_to_next(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="broken", provider=FailingProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        good = FakeProvider()
        chamber.add_provider(
            name="good", provider=good, model="m2",
            source_address=MAHA_QUANTUM * 11, prana=_PRANA_FREE,
        )
        result = chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        assert result is not None
        assert len(good.calls) == 1

    def test_failure_reduces_integrity(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="broken", provider=FailingProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10,
        )
        chamber.add_provider(
            name="backup", provider=FakeProvider(), model="m2",
            source_address=MAHA_QUANTUM * 11,
        )
        chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        broken_cell = chamber._cells[0]
        assert broken_cell.lifecycle.integrity < COSMIC_FRAME, (
            "Failure MUST reduce cell integrity"
        )

    def test_all_fail_returns_none(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="bad1", provider=FailingProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10,
        )
        chamber.add_provider(
            name="bad2", provider=FailingProvider(), model="m2",
            source_address=MAHA_QUANTUM * 11,
        )
        result = chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        assert result is None
        assert chamber._total_failures == 2


# ── Usage Tracking ───────────────────────────────────────────────────────


class TestUsageTracking:
    def test_prana_decreases_with_usage(self):
        chamber = ProviderChamber()
        response = FakeResponse(usage=FakeUsage(input_tokens=100, output_tokens=50))
        chamber.add_provider(
            name="test", provider=FakeProvider(response), model="m1",
            source_address=MAHA_QUANTUM * 10, prana=_PRANA_FREE,
        )
        chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        cell = chamber._cells[0]
        assert cell.lifecycle.prana == _PRANA_FREE - 150, (
            "Prana MUST decrease by total tokens used"
        )

    def test_daily_reset_refreshes(self):
        chamber = ProviderChamber()
        chamber.add_provider(
            name="test", provider=FakeProvider(), model="m1",
            source_address=MAHA_QUANTUM * 10, prana=100,
        )
        # Simulate yesterday
        chamber._last_reset = date.today() - timedelta(days=1)
        chamber.invoke(messages=[{"role": "user", "content": "hi"}])
        cell = chamber._cells[0]
        # After daily reset, prana should be back near _PRANA_FREE
        assert cell.lifecycle.prana >= _PRANA_FREE - 100


# ── build_chamber ────────────────────────────────────────────────────────


class TestBuildChamber:
    def test_no_keys_empty(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("GOOGLE_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            chamber = build_chamber()
            assert len(chamber) == 0

    def test_placeholder_keys_rejected(self):
        with patch.dict(os.environ, {
            "GOOGLE_API_KEY": "your-api-key-here",
            "MISTRAL_API_KEY": "xxx-placeholder",
            "OPENROUTER_API_KEY": "example-key",
        }):
            chamber = build_chamber()
            assert len(chamber) == 0


# ── GoogleAdapter ────────────────────────────────────────────────────────


class TestGoogleAdapter:
    def test_adapter_builds_prompt_from_messages(self):
        """GoogleAdapter MUST build prompt from messages for GoogleProvider compat."""
        provider = FakeProvider()
        adapter = GoogleAdapter(provider)
        adapter.invoke(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
            model="gemini-2.5-flash",
        )
        assert len(provider.calls) == 1
        assert "prompt" in provider.calls[0]
        assert "You are helpful." in provider.calls[0]["prompt"]
        assert "Hello" in provider.calls[0]["prompt"]

    def test_adapter_passes_messages_through(self):
        """GoogleAdapter still passes messages for providers that support it."""
        provider = FakeProvider()
        adapter = GoogleAdapter(provider)
        adapter.invoke(
            messages=[{"role": "user", "content": "hi"}],
            model="gemini-2.5-flash",
        )
        assert "messages" in provider.calls[0]


# ── _is_valid_key ────────────────────────────────────────────────────────


class TestIsValidKey:
    @pytest.mark.parametrize("key", [
        "your-api-key-here", "xxx", "placeholder-key", "example-api-key", "test-key-123", "",
    ])
    def test_rejects_placeholders(self, key):
        assert not _is_valid_key(key)

    @pytest.mark.parametrize("key", [
        "sk-1234567890abcdef", "AIzaSyB-real-google-key", "or-real-openrouter-key",
    ])
    def test_accepts_real_keys(self, key):
        assert _is_valid_key(key)


# ── Brain ↔ Chamber Integration ─────────────────────────────────────────


class TestBrainChamberIntegration:
    """Verify Brain uses ProviderChamber when available."""

    def test_brain_uses_chamber(self):
        from city.brain import CityBrain

        brain = CityBrain()
        chamber = ProviderChamber()
        response = FakeResponse(content='{"comprehension":"test","intent":"observe","confidence":0.8}')
        chamber.add_provider(
            name="test", provider=FakeProvider(response), model="m1",
            source_address=MAHA_QUANTUM * 10,
        )
        brain._chamber = chamber
        brain._available = True

        thought = brain._invoke_and_parse(
            [{"role": "system", "content": "test"}, {"role": "user", "content": "hi"}]
        )
        assert thought is not None
        assert thought.comprehension == "test"

    def test_brain_chamber_exhausted_returns_none(self):
        from city.brain import CityBrain

        brain = CityBrain()
        brain._chamber = ProviderChamber()  # empty
        brain._available = True

        thought = brain._invoke_and_parse(
            [{"role": "system", "content": "test"}, {"role": "user", "content": "hi"}]
        )
        assert thought is None

    def test_brain_falls_back_to_single_provider(self):
        from city.brain import CityBrain

        brain = CityBrain()
        response = FakeResponse(content='{"comprehension":"fallback","intent":"observe","confidence":0.5}')
        brain._provider = FakeProvider(response)
        brain._chamber = None
        brain._available = True

        thought = brain._invoke_and_parse(
            [{"role": "system", "content": "test"}, {"role": "user", "content": "hi"}]
        )
        assert thought is not None
        assert thought.comprehension == "fallback"
