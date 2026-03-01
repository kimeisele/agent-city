"""
CARTRIDGE LOADER — Discover and load cartridges for KARMA routing.
==================================================================

Two cartridge sources:
1. Static — steward-protocol CartridgeRegistry (requires .vibe root)
2. Dynamic — CartridgeFactory generates from Pokedex Jiva data (primary)

Dynamic is the primary path. Static is fallback for when steward-protocol
.vibe root is available.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.CARTRIDGE_LOADER")


@dataclass
class CityCartridgeLoader:
    """Discover and load cartridges from static registry + dynamic factory.

    Primary path: CartridgeFactory (Pokedex Jiva → runtime classes).
    Fallback: CartridgeRegistry (steward-protocol .vibe root).
    """

    _available: list[str] = field(default_factory=list)
    _loaded: dict[str, object] = field(default_factory=dict)
    _registry: object = None  # CartridgeRegistry
    _factory: object = None  # CartridgeFactory
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

    def set_factory(self, factory: object) -> None:
        """Wire CartridgeFactory for dynamic cartridge generation."""
        self._factory = factory

    def get(self, name: str) -> object | None:
        """Get a cartridge by name.

        Tries: cache → static registry → dynamic factory.
        Returns None if not available or load fails.
        """
        if name in self._loaded:
            return self._loaded[name]

        if not self._initialized:
            self.discover()

        # Try static registry first
        if name in self._available and self._registry is not None:
            try:
                cartridge = self._registry.get_cartridge(name)
                self._loaded[name] = cartridge
                logger.info("Loaded static cartridge: %s", name)
                return cartridge
            except Exception as e:
                logger.warning("Static cartridge %s load failed: %s", name, e)

        # Fall through to dynamic factory
        if self._factory is not None:
            cartridge = self._factory.get(name)
            if cartridge is not None:
                self._loaded[name] = cartridge
                return cartridge

        return None

    def list_available(self) -> list[str]:
        """List all cartridge names (static + dynamic)."""
        if not self._initialized:
            self.discover()
        names = set(self._available)
        if self._factory is not None:
            names.update(self._factory.list_generated())
        return sorted(names)

    def list_loaded(self) -> list[str]:
        """List currently loaded cartridge names."""
        return list(self._loaded.keys())

    def route_mission(self, mission_name: str) -> str | None:
        """Try to match a mission name to a cartridge.

        Tries keyword matching against static names first,
        then falls through to dynamic factory names.
        Returns cartridge name or None.
        """
        if not self._initialized:
            self.discover()

        name_lower = mission_name.lower()

        # Static cartridges (keyword match)
        for cartridge_name in self._available:
            if cartridge_name in name_lower:
                return cartridge_name

        # Dynamic cartridges (agent name match)
        if self._factory is not None:
            for agent_name in self._factory.list_generated():
                if agent_name.lower() in name_lower:
                    return agent_name

        return None

    def stats(self) -> dict:
        """Loader statistics."""
        dynamic_count = len(self._factory.list_generated()) if self._factory else 0
        return {
            "static": len(self._available),
            "dynamic": dynamic_count,
            "loaded": len(self._loaded),
            "cartridge_names": self._available,
            "loaded_names": list(self._loaded.keys()),
        }
