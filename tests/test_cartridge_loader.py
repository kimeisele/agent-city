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
    assert isinstance(available, list)
    assert loader._initialized is True
    # When vibe_core is installed, real cartridges are discovered
    try:
        import vibe_core  # noqa: F401

        assert len(available) >= 18, f"Expected >=18 cartridges, got {len(available)}"
        # Core system cartridges must be present
        for name in ("envoy", "engineer", "auditor", "herald", "oracle"):
            assert name in available, f"Missing core cartridge: {name}"
        # Registry must be populated
        assert loader._registry is not None
    except ImportError:
        pass  # No vibe_core = graceful empty list


def test_list_available():
    """list_available() includes static cartridges."""
    loader = CityCartridgeLoader()
    loader.discover()
    available = loader.list_available()
    for name in loader._available:
        assert name in available


def test_discover_uses_correct_vibe_root():
    """discover() resolves vibe_root from vibe_core.__path__, not .vibe/ detection."""
    try:
        import vibe_core

        expected_root = Path(vibe_core.__path__[0]).parent
        cartridge_dir = expected_root / "vibe_core" / "cartridges" / "system"
        assert cartridge_dir.exists(), f"Cartridge dir not found: {cartridge_dir}"

        loader = CityCartridgeLoader()
        available = loader.discover()
        assert len(available) > 0, "No cartridges discovered despite vibe_core present"
    except ImportError:
        pass  # Skip when vibe_core not installed


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
    assert stats["static"] == 2
    assert stats["loaded"] == 1
    assert "a" in stats["loaded_names"]


if __name__ == "__main__":
    test_discover_cartridges()
    test_list_available()
    test_get_unknown_cartridge()
    test_route_mission_match()
    test_stats()
    print("All 5 cartridge loader tests passed.")
