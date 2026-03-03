"""
CITY REGISTRY — Entity Lifecycle via SiksastakamRegistry
==========================================================

Bridge between steward-protocol's SiksastakamRegistry (512-slot O(1) memory)
and Agent City's entity management needs.

PROBLEM: discussions_bridge.py, moltbook_bridge.py, and other services each
maintain their own ad-hoc Python dicts/sets (_seed_threads, _seen_comment_ids,
_posted_hashes, _seen_post_ids, etc.). This is:
  - Fragile: no validation, no lifecycle, no deletion detection
  - Unscalable: Python dicts + manual snapshot/restore
  - Spaghetti: state management scattered across bridge files

SOLUTION: A CityRegistry wraps SiksastakamRegistry to manage city entities
(threads, comments, agents, posts) as MahaCells. Each entity gets a
deterministic slot via MahaCompression. The registry provides:
  - O(1) lookup/insert/remove
  - Null Object pattern (no None checks)
  - Built-in liveness detection (is the entity still alive?)
  - Binary persistence (to_bytes/from_bytes)
  - VenuOrchestrator-driven lifecycle (DIW transformations decay/refresh entities)

ENTITY TYPES:
  - THREAD:  GitHub Discussion threads (seed threads, user threads)
  - COMMENT: Individual comments within threads
  - POST:   Moltbook posts
  - AGENT:  Agent registrations (supplementary to Pokedex)

Each entity is a MahaCell with:
  - source: entity hash (deterministic from key)
  - target: parent hash (e.g., thread for a comment)
  - prana:  liveness energy (decays over time, refreshed on activity)
  - integrity: data consistency (drops if entity is stale/deleted)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import NamedTuple

import time as _time

from vibe_core.mahamantra.adapters.compression import MahaCompression
from vibe_core.mahamantra.substrate.cell import MahaCellUnified
from vibe_core.mahamantra.substrate.cell_system.registry import (
    SIKSASTAKAM_CACHE,
    SiksastakamRegistry,
)

logger = logging.getLogger("AGENT_CITY.REGISTRY")

# Default claim TTL: 60 seconds (one KARMA cycle is ~15 min, 60s is generous)
_DEFAULT_CLAIM_TTL: int = 60


# -- Claim Protocol ----------------------------------------------------------


@dataclass(frozen=True)
class ClaimTicket:
    """Concurrency lock for an agent acting on a thread.

    Prevents double-posting when multiple agents resonate with the same
    discussion. The ticket is created by request_claim() and released
    by release_claim() after a successful post.
    """

    thread_id: str
    agent_id: str
    timestamp: float
    expires_at: float

    def is_expired(self, now: float | None = None) -> bool:
        """Check if this claim has timed out."""
        return (now or _time.time()) >= self.expires_at

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "thread_id": self.thread_id,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ClaimTicket:
        """Deserialize from persistence."""
        return cls(
            thread_id=data["thread_id"],
            agent_id=data["agent_id"],
            timestamp=data["timestamp"],
            expires_at=data["expires_at"],
        )


class ClaimViolationError(RuntimeError):
    """Raised when a bridge post is attempted without a valid claim."""

    def __init__(self, thread_id: str, agent_id: str, holder: str) -> None:
        self.thread_id = thread_id
        self.agent_id = agent_id
        self.holder = holder
        super().__init__(
            f"Claim violation: agent '{agent_id}' tried to act on thread "
            f"'{thread_id}' but claim is held by '{holder}'"
        )


# -- Entity Types -----------------------------------------------------------


class EntityKind(IntEnum):
    """Kind of city entity stored in the registry."""

    THREAD = 0
    COMMENT = 1
    POST = 2
    AGENT = 3


class EntityEntry(NamedTuple):
    """Lightweight view of a registered entity."""

    key: str
    kind: EntityKind
    slot: int
    prana: int
    integrity: int
    is_alive: bool


# -- City Registry -----------------------------------------------------------


@dataclass
class CityRegistry:
    """Entity lifecycle manager backed by SiksastakamRegistry.

    Entities are stored as MahaCells in a 512-slot O(1) registry.
    Each entity key is hashed to a deterministic slot via MahaCompression.

    Usage:
        registry = CityRegistry()
        registry.register("brainstream", EntityKind.THREAD, parent="seed")
        registry.register("welcome", EntityKind.THREAD, parent="seed")

        if registry.is_alive("brainstream"):
            ...  # thread exists

        registry.remove("brainstream")  # marks cell as null

        # Detect missing entities
        missing = registry.find_missing(["brainstream", "welcome", "registry"])
    """

    _registry: SiksastakamRegistry = field(default_factory=SiksastakamRegistry)
    _compression: MahaCompression = field(default_factory=MahaCompression)
    _key_to_slot: dict[str, int] = field(default_factory=dict)
    _slot_to_key: dict[int, str] = field(default_factory=dict)
    _entity_kinds: dict[str, EntityKind] = field(default_factory=dict)
    _entity_meta: dict[str, dict] = field(default_factory=dict)
    _active_claims: dict[str, ClaimTicket] = field(default_factory=dict)

    def _resolve_slot(self, key: str) -> int:
        """Key → deterministic slot (0-511) via MahaCompression."""
        if key in self._key_to_slot:
            return self._key_to_slot[key]
        result = self._compression.compress(key)
        slot = result.seed % SIKSASTAKAM_CACHE
        self._key_to_slot[key] = slot
        self._slot_to_key[slot] = key
        return slot

    def register(
        self,
        key: str,
        kind: EntityKind,
        *,
        parent: str = "",
        meta: dict | None = None,
    ) -> int:
        """Register an entity in the registry.

        Creates a MahaCell at the entity's deterministic slot.
        If the slot is already occupied by a different entity (collision),
        the existing entity is merged (prana additive).

        Args:
            key: Unique entity identifier (e.g., "brainstream", "comment:123")
            kind: Entity type
            parent: Parent entity key (e.g., thread key for a comment)
            meta: Optional metadata dict stored alongside

        Returns:
            Slot index where entity was placed
        """
        slot = self._resolve_slot(key)
        parent_hash = self._compression.compress(parent).seed if parent else 0

        cell = MahaCellUnified.create(
            source=self._compression.compress(key).seed,
            target=parent_hash,
            operation=int(kind),
        )

        existing = self._registry.get(slot)
        if existing.is_alive:
            # Collision or refresh — merge prana
            existing.lifecycle.prana += cell.lifecycle.prana
            logger.debug("REGISTRY: Refreshed '%s' at slot %d (prana=%d)", key, slot, existing.lifecycle.prana)
        else:
            self._registry.set(slot, cell)
            logger.debug("REGISTRY: Registered '%s' at slot %d", key, slot)

        self._key_to_slot[key] = slot
        self._slot_to_key[slot] = key
        self._entity_kinds[key] = kind
        if meta:
            self._entity_meta[key] = meta

        return slot

    def remove(self, key: str) -> bool:
        """Remove an entity by nulling its slot.

        Returns True if entity was alive and is now removed.
        """
        slot = self._key_to_slot.get(key)
        if slot is None:
            return False

        cell = self._registry.get(slot)
        if not cell.is_alive:
            return False

        self._registry.set(slot, MahaCellUnified.null())
        logger.info("REGISTRY: Removed '%s' from slot %d", key, slot)
        return True

    def is_alive(self, key: str) -> bool:
        """Check if an entity is alive in the registry."""
        slot = self._key_to_slot.get(key)
        if slot is None:
            return False
        return self._registry.get(slot).is_alive

    def get_entry(self, key: str) -> EntityEntry | None:
        """Get entity info. Returns None if not registered."""
        slot = self._key_to_slot.get(key)
        if slot is None:
            return None
        cell = self._registry.get(slot)
        return EntityEntry(
            key=key,
            kind=self._entity_kinds.get(key, EntityKind.THREAD),
            slot=slot,
            prana=cell.lifecycle.prana,
            integrity=cell.lifecycle.integrity,
            is_alive=cell.is_alive,
        )

    def get_meta(self, key: str) -> dict:
        """Get entity metadata (e.g., discussion_number for threads)."""
        return self._entity_meta.get(key, {})

    def set_meta(self, key: str, meta: dict) -> None:
        """Update entity metadata."""
        self._entity_meta[key] = meta

    def find_missing(self, expected_keys: list[str]) -> list[str]:
        """Find keys that are expected but not alive in the registry.

        This is the core resilience check: call with your expected
        entity keys, get back which ones are missing/dead.
        """
        return [k for k in expected_keys if not self.is_alive(k)]

    def find_alive(self, kind: EntityKind | None = None) -> list[EntityEntry]:
        """List all alive entities, optionally filtered by kind."""
        entries = []
        for key, slot in self._key_to_slot.items():
            cell = self._registry.get(slot)
            if not cell.is_alive:
                continue
            entity_kind = self._entity_kinds.get(key, EntityKind.THREAD)
            if kind is not None and entity_kind != kind:
                continue
            entries.append(EntityEntry(
                key=key,
                kind=entity_kind,
                slot=slot,
                prana=cell.lifecycle.prana,
                integrity=cell.lifecycle.integrity,
                is_alive=True,
            ))
        return entries

    @property
    def alive_count(self) -> int:
        """Number of alive entities."""
        return len(self._registry.active_cells())

    @property
    def capacity(self) -> int:
        """Total registry capacity (512)."""
        return SIKSASTAKAM_CACHE

    def stats(self) -> dict:
        """Registry statistics."""
        alive = self._registry.active_cells()
        total_prana = sum(c.lifecycle.prana for c in alive)
        return {
            "alive": len(alive),
            "capacity": SIKSASTAKAM_CACHE,
            "total_prana": total_prana,
            "registered_keys": len(self._key_to_slot),
            "active_claims": len(self._active_claims),
            "kinds": {
                kind.name: sum(1 for k, kd in self._entity_kinds.items() if kd == kind and self.is_alive(k))
                for kind in EntityKind
            },
        }

    # -- Claim Protocol -------------------------------------------------------

    def request_claim(
        self,
        thread_id: str,
        agent_id: str,
        ttl_seconds: int = _DEFAULT_CLAIM_TTL,
    ) -> ClaimTicket | None:
        """Request exclusive claim on a thread for an agent.

        Returns a ClaimTicket if the claim is granted (no active claim by
        another agent exists). Returns None if the thread is already
        claimed by a different agent.

        If the agent already holds the claim, refreshes the TTL and
        returns the updated ticket.
        """
        now = _time.time()
        existing = self._active_claims.get(thread_id)

        if existing is not None and not existing.is_expired(now):
            if existing.agent_id == agent_id:
                # Same agent — refresh TTL
                refreshed = ClaimTicket(
                    thread_id=thread_id,
                    agent_id=agent_id,
                    timestamp=existing.timestamp,
                    expires_at=now + ttl_seconds,
                )
                self._active_claims[thread_id] = refreshed
                logger.debug(
                    "CLAIM: Refreshed claim on '%s' for '%s' (expires +%ds)",
                    thread_id, agent_id, ttl_seconds,
                )
                return refreshed
            # Different agent holds the claim
            logger.info(
                "CLAIM: Denied '%s' on thread '%s' — held by '%s' (expires %.0fs)",
                agent_id, thread_id, existing.agent_id,
                existing.expires_at - now,
            )
            return None

        # No active claim — grant it
        ticket = ClaimTicket(
            thread_id=thread_id,
            agent_id=agent_id,
            timestamp=now,
            expires_at=now + ttl_seconds,
        )
        self._active_claims[thread_id] = ticket
        logger.info(
            "CLAIM: Granted '%s' → thread '%s' (ttl=%ds)",
            agent_id, thread_id, ttl_seconds,
        )
        return ticket

    def release_claim(self, thread_id: str, agent_id: str) -> bool:
        """Release a claim after successful action.

        Returns True if the claim was held by this agent and is now released.
        Returns False if no claim exists or it belongs to another agent.
        """
        existing = self._active_claims.get(thread_id)
        if existing is None:
            return False
        if existing.agent_id != agent_id:
            logger.warning(
                "CLAIM: Release denied — '%s' tried to release '%s' (held by '%s')",
                agent_id, thread_id, existing.agent_id,
            )
            return False
        del self._active_claims[thread_id]
        logger.debug("CLAIM: Released '%s' → thread '%s'", agent_id, thread_id)
        return True

    def check_claim(self, thread_id: str, agent_id: str) -> bool:
        """Check if an agent holds a valid (non-expired) claim on a thread."""
        existing = self._active_claims.get(thread_id)
        if existing is None:
            return False
        if existing.is_expired():
            del self._active_claims[thread_id]
            return False
        return existing.agent_id == agent_id

    def get_claim_holder(self, thread_id: str) -> str | None:
        """Return the agent_id holding the claim, or None if unclaimed/expired."""
        existing = self._active_claims.get(thread_id)
        if existing is None:
            return None
        if existing.is_expired():
            del self._active_claims[thread_id]
            return None
        return existing.agent_id

    def purge_expired_claims(self, now: float | None = None) -> int:
        """Remove all expired claims. Returns count of purged claims."""
        now = now or _time.time()
        expired = [
            tid for tid, ticket in self._active_claims.items()
            if ticket.is_expired(now)
        ]
        for tid in expired:
            agent = self._active_claims[tid].agent_id
            del self._active_claims[tid]
            logger.debug("CLAIM: Purged expired claim '%s' → '%s'", agent, tid)
        if expired:
            logger.info("CLAIM: Purged %d expired claims", len(expired))
        return len(expired)

    # -- Persistence ----------------------------------------------------------

    def snapshot(self) -> dict:
        """Serialize for persistence."""
        return {
            "registry_bytes": self._registry.to_bytes().hex(),
            "key_to_slot": dict(self._key_to_slot),
            "entity_kinds": {k: int(v) for k, v in self._entity_kinds.items()},
            "entity_meta": dict(self._entity_meta),
            "active_claims": {
                tid: ticket.to_dict()
                for tid, ticket in self._active_claims.items()
            },
        }

    def restore(self, data: dict) -> None:
        """Restore from persisted snapshot."""
        registry_hex = data.get("registry_bytes", "")
        if registry_hex:
            try:
                self._registry.from_bytes(bytes.fromhex(registry_hex))
            except Exception as exc:
                logger.warning("REGISTRY: Failed to restore registry bytes: %s", exc)

        self._key_to_slot = data.get("key_to_slot", {})
        # Rebuild reverse mapping
        self._slot_to_key = {int(v): k for k, v in self._key_to_slot.items()}
        # Convert slot values to int
        self._key_to_slot = {k: int(v) for k, v in self._key_to_slot.items()}
        self._entity_kinds = {
            k: EntityKind(v) for k, v in data.get("entity_kinds", {}).items()
        }
        self._entity_meta = data.get("entity_meta", {})

        # Restore claims (purge any that expired while we were down)
        raw_claims = data.get("active_claims", {})
        now = _time.time()
        restored_claims = 0
        for tid, ticket_data in raw_claims.items():
            try:
                ticket = ClaimTicket.from_dict(ticket_data)
                if not ticket.is_expired(now):
                    self._active_claims[tid] = ticket
                    restored_claims += 1
            except (KeyError, TypeError) as exc:
                logger.debug("CLAIM: Skipped invalid claim data for '%s': %s", tid, exc)

        alive = len(self._registry.active_cells())
        logger.info(
            "REGISTRY: Restored %d keys, %d alive cells, %d active claims",
            len(self._key_to_slot), alive, restored_claims,
        )


# -- Singleton ---------------------------------------------------------------

_city_registry: CityRegistry | None = None


def get_city_registry() -> CityRegistry:
    """Get the singleton CityRegistry."""
    global _city_registry
    if _city_registry is None:
        _city_registry = CityRegistry()
    return _city_registry
