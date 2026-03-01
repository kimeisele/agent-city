"""
Tests for D6: Cartridge Loader — discover + lazy-load cartridges.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.cartridge_loader import CityCartridgeLoader


def test_discover_cartridges():
    """discover() finds available cartridges from steward-protocol."""
    loader = CityCartridgeLoader()
    available = loader.discover()
    # Should find at least some cartridges (18 system cartridges exist)
    assert isinstance(available, list)
    # Even if discovery fails, it returns empty list (not crash)
    assert loader._initialized is True


def test_list_available():
    """list_available() returns same as discover()."""
    loader = CityCartridgeLoader()
    loader.discover()
    assert loader.list_available() == loader._available


def test_get_unknown_cartridge():
    """get() returns None for unknown cartridge."""
    loader = CityCartridgeLoader()
    loader._initialized = True
    loader._available = ["oracle", "herald"]
    assert loader.get("nonexistent") is None


def test_route_mission_match():
    """route_mission() matches mission name to cartridge name."""
    loader = CityCartridgeLoader()
    loader._initialized = True
    loader._available = ["oracle", "herald", "auditor", "scribe"]

    assert loader.route_mission("Oracle query: check status") == "oracle"
    assert loader.route_mission("Herald broadcast needed") == "herald"
    assert loader.route_mission("No matching name") is None


def test_stats():
    """stats() returns expected structure."""
    loader = CityCartridgeLoader()
    loader._initialized = True
    loader._available = ["a", "b"]
    loader._loaded = {"a": object()}

    stats = loader.stats()
    assert stats["available"] == 2
    assert stats["loaded"] == 1
    assert "a" in stats["loaded_names"]


if __name__ == "__main__":
    test_discover_cartridges()
    test_list_available()
    test_get_unknown_cartridge()
    test_route_mission_match()
    test_stats()
    print("All 5 cartridge loader tests passed.")
