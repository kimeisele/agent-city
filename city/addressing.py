"""
AGENT ADDRESSING — Deterministic Mahamantra-Derived Addresses
==============================================================

Every agent name → MahaCompression → deterministic uint32 seed = the agent's address.
Same name always produces same address across all restarts.

Wired from steward-protocol:
- MahaCompression (adapters/compression.py) — string → seed (deterministic)
- MahaHeader (protocols/_header.py) — 72-byte routing header
- CellRouter (cell_system/cell_router.py) — O(1) lookup by address

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from vibe_core.mahamantra.adapters.compression import MahaCompression
from vibe_core.mahamantra.protocols._header import MahaHeader
from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified
from vibe_core.mahamantra.substrate.cell_system.cell_router import CellRouter

logger = logging.getLogger("AGENT_CITY.ADDRESSING")

# Singleton compression engine — deterministic, no new objects per call
_compression: MahaCompression | None = None


def _get_compression() -> MahaCompression:
    global _compression
    if _compression is None:
        _compression = MahaCompression()
    return _compression


@dataclass
class CityAddressBook:
    """Deterministic Mahamantra-derived agent addressing.

    Each agent name → MahaCompression seed → uint32 address.
    Addresses are deterministic: same name = same address, always.
    """

    _router: CellRouter = field(default_factory=CellRouter)
    _name_to_address: dict[str, int] = field(default_factory=dict)
    _address_to_name: dict[int, str] = field(default_factory=dict)

    def resolve(self, name: str) -> int:
        """Name → collision-resistant uint32 address.

        Combines two entropy sources for uniqueness:
          1. MahaCompression seed (Mahamantra-derived, deterministic)
          2. SHA-256(name) (cryptographic, guaranteed unique per name)

        XOR ensures both sources contribute. The name hash alone
        would suffice for uniqueness, but the compression seed
        preserves the Mahamantra binding.
        """
        if name in self._name_to_address:
            return self._name_to_address[name]

        import hashlib

        # Source 1: Mahamantra compression (spiritually meaningful)
        compression = _get_compression()
        result = compression.compress(name)
        mahamantra_seed = result.seed

        # Source 2: SHA-256 of name (cryptographically collision-resistant)
        name_hash = hashlib.sha256(name.encode()).digest()
        # Take first 4 bytes as uint32
        name_seed = int.from_bytes(name_hash[:4], "big")

        # Combine: XOR preserves both sources, abs ensures positive
        address = (mahamantra_seed ^ name_seed) & 0xFFFFFFFF
        # Ensure non-zero (address 0 is reserved)
        if address == 0:
            address = 1

        self._name_to_address[name] = address
        self._address_to_name[address] = name
        logger.debug("Resolved %s → address %d", name, address)
        return address

    def lookup(self, address: int) -> MahaCellUnified | None:
        """Address → CellRouter.get() → O(1) cell lookup."""
        return self._router.get(address)

    def lookup_name(self, address: int) -> str | None:
        """Address → agent name (from local cache)."""
        return self._address_to_name.get(address)

    def register(self, name: str, cell: MahaCellUnified) -> int:
        """Register an agent's cell in the router for O(1) lookup.

        Returns the computed address.
        """
        address = self.resolve(name)
        self._router.insert(address, cell)
        logger.debug("Registered %s at address %d in router", name, address)
        return address

    def unregister(self, name: str) -> bool:
        """Remove an agent from the router."""
        address = self._name_to_address.get(name)
        if address is None:
            return False
        removed = self._router.unregister(address)
        if removed:
            self._name_to_address.pop(name, None)
            self._address_to_name.pop(address, None)
        return removed

    def route(self, source: str, target: str, operation: int = 0) -> MahaHeader:
        """Create routing header: source → target with operation code.

        Returns a 72-byte MahaHeader with addresses computed from names.
        """
        src_addr = self.resolve(source)
        tgt_addr = self.resolve(target)
        return MahaHeader.create(
            source=src_addr,
            target=tgt_addr,
            operation=operation,
        )

    def is_registered(self, name: str) -> bool:
        """Check if an agent is registered in the router."""
        address = self._name_to_address.get(name)
        if address is None:
            return False
        return address in self._router

    @property
    def registered_count(self) -> int:
        """Number of agents registered in the router."""
        return len(self._router)

    def stats(self) -> dict:
        """Address book statistics."""
        return {
            "resolved": len(self._name_to_address),
            "registered": len(self._router),
            "router": self._router.stats(),
        }
