"""Tests for city/resonator.py — CityResonator bridge."""

import pytest


def test_resonator_basic():
    """CityResonator produces scores for agents given input text."""
    from city.resonator import CityResonator

    resonator = CityResonator()
    specs = {
        "agent_alpha": {"domain": "DISCOVERY", "element": "akasha"},
        "agent_beta": {"domain": "RESEARCH", "element": "agni"},
        "agent_gamma": {"domain": "SECURITY", "element": "prithvi"},
    }

    result = resonator.resonate("How can agents collaborate on code?", specs)

    assert len(result.scores) > 0
    assert len(result.scores) <= 3
    assert len(result.input_coords) > 0
    assert result.chamber_mode in ("SOLO", "CALL_RESPONSE", "CHORUS")

    # Each score has the right fields
    for score in result.scores:
        assert score.agent_name in specs
        assert isinstance(score.prana_delta, int)
        assert isinstance(score.integrity_after, int)
        assert isinstance(score.is_alive, bool)


def test_resonator_empty_input():
    """Empty input returns empty result."""
    from city.resonator import CityResonator

    resonator = CityResonator()
    result = resonator.resonate("", {"a": {}})
    assert result.scores == ()
    assert result.input_coords == ()


def test_resonator_no_agents():
    """No agents returns empty scores."""
    from city.resonator import CityResonator

    resonator = CityResonator()
    result = resonator.resonate("test input", {})
    assert result.scores == ()


def test_resonator_different_inputs_different_scores():
    """Different input texts produce different resonance patterns."""
    from city.resonator import CityResonator

    resonator = CityResonator()
    specs = {
        "agent_a": {"domain": "DISCOVERY"},
        "agent_b": {"domain": "SECURITY"},
    }

    r1 = resonator.resonate("security vulnerability in authentication", specs)
    r2 = resonator.resonate("creative exploration of new ideas", specs)

    # Different inputs should produce different RAMA coordinates
    assert r1.input_coords != r2.input_coords

    # Scores should differ (different phonetic resonance)
    if r1.scores and r2.scores:
        scores_1 = {s.agent_name: s.prana_delta for s in r1.scores}
        scores_2 = {s.agent_name: s.prana_delta for s in r2.scores}
        # At least one agent should have different prana_delta
        assert scores_1 != scores_2


def test_resonator_deterministic():
    """Same input + same agents = same result (deterministic)."""
    from city.resonator import CityResonator

    specs = {"agent_x": {"domain": "TEST"}, "agent_y": {"domain": "TEST"}}
    text = "deterministic resonance test"

    r1 = CityResonator().resonate(text, specs)
    r2 = CityResonator().resonate(text, specs)

    assert r1.scores == r2.scores
    assert r1.input_coords == r2.input_coords


def test_pick_agents_returns_names():
    """pick_agents convenience returns agent names."""
    from city.resonator import CityResonator

    resonator = CityResonator()
    specs = {
        "a1": {"domain": "D1"},
        "a2": {"domain": "D2"},
        "a3": {"domain": "D3"},
    }

    agents = resonator.pick_agents("test input", specs, min_agents=1, max_agents=2)
    assert len(agents) >= 1
    assert len(agents) <= 2
    assert all(name in specs for name in agents)


def test_pick_agents_empty_input():
    """pick_agents with empty input returns empty list."""
    from city.resonator import CityResonator

    agents = CityResonator().pick_agents("", {"a": {}})
    assert agents == []


def test_resonator_singleton():
    """get_resonator returns singleton."""
    from city.resonator import get_resonator

    r1 = get_resonator()
    r2 = get_resonator()
    assert r1 is r2


def test_resonator_max_agents_cap():
    """Result is capped at max_agents."""
    from city.resonator import CityResonator

    specs = {f"agent_{i}": {"domain": "TEST"} for i in range(10)}
    result = CityResonator().resonate("test", specs, max_agents=3)
    assert len(result.scores) <= 3


def test_resonate_count_increments():
    """resonate_count tracks calls."""
    from city.resonator import CityResonator

    r = CityResonator()
    assert r.resonate_count == 0
    r.resonate("x", {"a": {}})
    assert r.resonate_count == 1
    r.resonate("y", {"b": {}})
    assert r.resonate_count == 2
