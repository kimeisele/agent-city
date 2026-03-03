"""Tests for city/city_registry.py — Entity lifecycle via SiksastakamRegistry."""

import pytest

from city.city_registry import CityRegistry, EntityKind, get_city_registry


def test_register_and_lookup():
    """Register an entity and verify it's alive."""
    reg = CityRegistry()
    slot = reg.register("brainstream", EntityKind.THREAD, parent="seed")
    assert slot >= 0
    assert reg.is_alive("brainstream")


def test_register_with_meta():
    """Register with metadata and retrieve it."""
    reg = CityRegistry()
    reg.register("brainstream", EntityKind.THREAD, meta={"discussion_number": 42})
    assert reg.get_meta("brainstream") == {"discussion_number": 42}


def test_remove_entity():
    """Remove nulls the slot."""
    reg = CityRegistry()
    reg.register("test_thread", EntityKind.THREAD)
    assert reg.is_alive("test_thread")

    removed = reg.remove("test_thread")
    assert removed is True
    assert not reg.is_alive("test_thread")


def test_remove_nonexistent():
    """Remove of unknown key returns False."""
    reg = CityRegistry()
    assert reg.remove("ghost") is False


def test_is_alive_unknown():
    """Unknown key is not alive."""
    reg = CityRegistry()
    assert not reg.is_alive("nonexistent")


def test_get_entry():
    """get_entry returns EntityEntry with correct fields."""
    reg = CityRegistry()
    reg.register("welcome", EntityKind.THREAD)

    entry = reg.get_entry("welcome")
    assert entry is not None
    assert entry.key == "welcome"
    assert entry.kind == EntityKind.THREAD
    assert entry.is_alive is True
    assert entry.prana > 0


def test_get_entry_unknown():
    """get_entry returns None for unknown key."""
    reg = CityRegistry()
    assert reg.get_entry("ghost") is None


def test_find_missing():
    """find_missing detects unregistered or dead entities."""
    reg = CityRegistry()
    reg.register("welcome", EntityKind.THREAD)
    reg.register("registry", EntityKind.THREAD)

    missing = reg.find_missing(["welcome", "registry", "brainstream", "city_log"])
    assert "brainstream" in missing
    assert "city_log" in missing
    assert "welcome" not in missing
    assert "registry" not in missing


def test_find_missing_after_removal():
    """Removed entities show as missing."""
    reg = CityRegistry()
    reg.register("brainstream", EntityKind.THREAD)
    assert reg.find_missing(["brainstream"]) == []

    reg.remove("brainstream")
    assert reg.find_missing(["brainstream"]) == ["brainstream"]


def test_find_alive_by_kind():
    """find_alive filters by EntityKind."""
    reg = CityRegistry()
    reg.register("thread_1", EntityKind.THREAD)
    reg.register("comment_1", EntityKind.COMMENT)
    reg.register("thread_2", EntityKind.THREAD)

    threads = reg.find_alive(EntityKind.THREAD)
    assert len(threads) == 2
    assert all(e.kind == EntityKind.THREAD for e in threads)

    comments = reg.find_alive(EntityKind.COMMENT)
    assert len(comments) == 1


def test_find_alive_all():
    """find_alive without filter returns all alive."""
    reg = CityRegistry()
    reg.register("a", EntityKind.THREAD)
    reg.register("b", EntityKind.COMMENT)
    reg.register("c", EntityKind.POST)

    alive = reg.find_alive()
    assert len(alive) >= 3


def test_refresh_prana_on_re_register():
    """Re-registering an alive entity adds prana (refresh)."""
    reg = CityRegistry()
    reg.register("thread_x", EntityKind.THREAD)
    entry1 = reg.get_entry("thread_x")

    reg.register("thread_x", EntityKind.THREAD)
    entry2 = reg.get_entry("thread_x")

    assert entry2.prana > entry1.prana


def test_deterministic_slots():
    """Same key always maps to same slot."""
    reg1 = CityRegistry()
    reg2 = CityRegistry()
    slot1 = reg1.register("brainstream", EntityKind.THREAD)
    slot2 = reg2.register("brainstream", EntityKind.THREAD)
    assert slot1 == slot2


def test_different_keys_different_slots():
    """Different keys map to different slots (usually)."""
    reg = CityRegistry()
    slots = set()
    keys = ["welcome", "registry", "ideas", "city_log", "brainstream"]
    for k in keys:
        slots.add(reg.register(k, EntityKind.THREAD))
    # Hash collisions are possible; just verify reasonable distribution
    assert len(slots) >= 2


def test_stats():
    """stats() returns registry health info."""
    reg = CityRegistry()
    reg.register("a", EntityKind.THREAD)
    reg.register("b", EntityKind.COMMENT)

    s = reg.stats()
    assert s["alive"] >= 2
    assert s["capacity"] == 512
    assert s["total_prana"] > 0
    assert "THREAD" in s["kinds"]
    assert "COMMENT" in s["kinds"]


def test_snapshot_restore():
    """Snapshot and restore preserves entities."""
    reg = CityRegistry()
    reg.register("welcome", EntityKind.THREAD, meta={"number": 10})
    reg.register("registry", EntityKind.THREAD, meta={"number": 11})

    snap = reg.snapshot()

    # New registry, restore from snapshot
    reg2 = CityRegistry()
    reg2.restore(snap)

    assert reg2.get_meta("welcome") == {"number": 10}
    assert reg2.get_meta("registry") == {"number": 11}
    assert "welcome" in reg2._key_to_slot
    assert "registry" in reg2._key_to_slot


def test_capacity():
    """Capacity is 512."""
    reg = CityRegistry()
    assert reg.capacity == 512


def test_singleton():
    """get_city_registry returns singleton."""
    # Reset singleton for test isolation
    import city.city_registry as mod
    mod._city_registry = None

    r1 = get_city_registry()
    r2 = get_city_registry()
    assert r1 is r2

    mod._city_registry = None  # cleanup


def test_entity_kinds_enum():
    """EntityKind has expected values."""
    assert EntityKind.THREAD == 0
    assert EntityKind.COMMENT == 1
    assert EntityKind.POST == 2
    assert EntityKind.AGENT == 3
