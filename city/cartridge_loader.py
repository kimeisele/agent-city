"""
CARTRIDGE LOADER — Discover and lazy-load steward-protocol cartridges.
======================================================================

18 system cartridges exist in steward-protocol. This loader discovers
and lazy-loads them via CartridgeRegistry for use in KARMA routing.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.CARTRIDGE_LOADER")


@dataclass
class CityCartridgeLoader:
    """Discovers and lazy-loads cartridges from steward-protocol.

    Uses CartridgeRegistry for auto-discovery. Cartridges are loaded
    lazily on first access (get).
    """

    _available: list[str] = field(default_factory=list)
    _loaded: dict[str, object] = field(default_factory=dict)
    _registry: object = None  # CartridgeRegistry
    _initialized: bool = False

    def discover(self) -> list[str]:
        """Discover available cartridges from steward-protocol.

        Returns list of cartridge names.
        """
        if self._initialized:
            return self._available

        try:
            from vibe_core.cartridges.registry import get_default_cartridge_registry

            self._registry = get_default_cartridge_registry()
            self._available = self._registry.get_cartridge_names()
            self._initialized = True
            logger.info("Discovered %d cartridges: %s", len(self._available), self._available)
        except Exception as e:
            logger.warning("Cartridge discovery failed: %s", e)
            self._available = []
            self._initialized = True

        return self._available

    def get(self, name: str) -> object | None:
        """Get a cartridge by name (lazy-loaded, cached).

        Returns None if not available or load fails.
        """
        if name in self._loaded:
            return self._loaded[name]

        if not self._initialized:
            self.discover()

        if name not in self._available:
            logger.warning("Cartridge %s not available", name)
            return None

        try:
            cartridge = self._registry.get_cartridge(name)
            self._loaded[name] = cartridge
            logger.info("Loaded cartridge: %s", name)
            return cartridge
        except Exception as e:
            logger.warning("Cartridge %s load failed: %s", name, e)
            return None

    def list_available(self) -> list[str]:
        """List all discovered cartridge names."""
        if not self._initialized:
            self.discover()
        return list(self._available)

    def list_loaded(self) -> list[str]:
        """List currently loaded cartridge names."""
        return list(self._loaded.keys())

    def route_mission(self, mission_name: str) -> str | None:
        """Try to match a mission name to a cartridge.

        Uses keyword matching against known cartridge names.
        Returns cartridge name or None.
        """
        if not self._initialized:
            self.discover()

        name_lower = mission_name.lower()
        for cartridge_name in self._available:
            if cartridge_name in name_lower:
                return cartridge_name

        return None

    def stats(self) -> dict:
        """Loader statistics."""
        return {
            "available": len(self._available),
            "loaded": len(self._loaded),
            "cartridge_names": self._available,
            "loaded_names": list(self._loaded.keys()),
        }
