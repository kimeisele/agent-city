"""
Tests for D3: Adaptive Daemon — entropy-driven continuous operation.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.daemon import (
    GAJENDRA,
    SAMADHI,
    SADHANA,
    CityEntropy,
    DaemonService,
)


def test_entropy_perfect_health():
    """Perfect city → health 1.0 → SAMADHI."""
    e = CityEntropy()
    assert e.health == 1.0
    assert e.recommended_hz == SAMADHI


def test_entropy_moderate_stress():
    """Moderate dead ratio → health ~0.9 → SADHANA."""
    e = CityEntropy(dead_ratio=0.3, contract_fail_ratio=0.1)
    health = e.health
    assert 0.80 < health < 0.95
    assert e.recommended_hz == SADHANA


def test_entropy_crisis():
    """High dead ratio + contract failures → health < 0.80 → GAJENDRA."""
    e = CityEntropy(
        dead_ratio=0.8,
        contract_fail_ratio=0.5,
        queue_pressure=0.5,
        pathogen_count=5,
    )
    assert e.health < 0.80
    assert e.recommended_hz == GAJENDRA


def test_entropy_to_dict():
    """CityEntropy serializes correctly."""
    e = CityEntropy(dead_ratio=0.2, pathogen_count=3)
    d = e.to_dict()
    assert "health" in d
    assert "recommended_hz" in d
    assert d["dead_ratio"] == 0.2
    assert d["pathogen_count"] == 3


def test_daemon_stats():
    """DaemonService stats returns expected keys."""
    from unittest.mock import MagicMock

    mayor = MagicMock()
    daemon = DaemonService(mayor=mayor)
    stats = daemon.stats()
    assert stats["running"] is False
    assert stats["frequency_hz"] == SADHANA
    assert stats["total_beats"] == 0
    assert "entropy" in stats


def test_daemon_set_frequency_clamped():
    """set_frequency clamps to [0.1, GAJENDRA]."""
    from unittest.mock import MagicMock

    mayor = MagicMock()
    daemon = DaemonService(mayor=mayor)

    daemon.set_frequency(100.0)
    assert daemon.frequency_hz == GAJENDRA

    daemon.set_frequency(0.001)
    assert daemon.frequency_hz == 0.1


if __name__ == "__main__":
    test_entropy_perfect_health()
    test_entropy_moderate_stress()
    test_entropy_crisis()
    test_entropy_to_dict()
    test_daemon_stats()
    test_daemon_set_frequency_clamped()
    print("All 6 adaptive daemon tests passed.")
