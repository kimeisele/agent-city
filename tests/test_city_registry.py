"""Tests for city/city_registry.py — Entity lifecycle via SiksastakamRegistry."""

import time

import pytest

from city.city_registry import (
    CityRegistry,
    ClaimTicket,
    ClaimViolationError,
    EntityKind,
    get_city_registry,
)


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


# ── 8D: Claim Protocol Tests ────────────────────────────────────────────


class TestClaimTicket:
    """ClaimTicket dataclass tests."""

    def test_create_and_fields(self):
        now = time.time()
        t = ClaimTicket(thread_id="42", agent_id="alice", timestamp=now, expires_at=now + 60)
        assert t.thread_id == "42"
        assert t.agent_id == "alice"
        assert not t.is_expired(now)

    def test_expired(self):
        past = time.time() - 100
        t = ClaimTicket(thread_id="42", agent_id="alice", timestamp=past, expires_at=past + 10)
        assert t.is_expired()

    def test_to_from_dict(self):
        now = time.time()
        t = ClaimTicket(thread_id="42", agent_id="alice", timestamp=now, expires_at=now + 60)
        d = t.to_dict()
        t2 = ClaimTicket.from_dict(d)
        assert t == t2

    def test_frozen(self):
        now = time.time()
        t = ClaimTicket(thread_id="42", agent_id="alice", timestamp=now, expires_at=now + 60)
        with pytest.raises(AttributeError):
            t.agent_id = "bob"  # type: ignore[misc]


class TestClaimProtocol:
    """CityRegistry claim lifecycle tests."""

    def test_request_claim_granted(self):
        reg = CityRegistry()
        ticket = reg.request_claim("42", "alice")
        assert ticket is not None
        assert ticket.agent_id == "alice"
        assert ticket.thread_id == "42"

    def test_request_claim_denied_different_agent(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice")
        denied = reg.request_claim("42", "bob")
        assert denied is None

    def test_request_claim_refresh_same_agent(self):
        reg = CityRegistry()
        t1 = reg.request_claim("42", "alice", ttl_seconds=30)
        t2 = reg.request_claim("42", "alice", ttl_seconds=60)
        assert t2 is not None
        assert t2.expires_at > t1.expires_at

    def test_request_claim_after_expiry(self):
        """Expired claim allows another agent to claim."""
        reg = CityRegistry()
        now = time.time()
        # Manually inject an expired claim
        reg._active_claims["42"] = ClaimTicket(
            thread_id="42", agent_id="alice",
            timestamp=now - 100, expires_at=now - 1,
        )
        ticket = reg.request_claim("42", "bob")
        assert ticket is not None
        assert ticket.agent_id == "bob"

    def test_release_claim_success(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice")
        released = reg.release_claim("42", "alice")
        assert released is True
        # Thread is now free
        ticket = reg.request_claim("42", "bob")
        assert ticket is not None

    def test_release_claim_wrong_agent(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice")
        released = reg.release_claim("42", "bob")
        assert released is False

    def test_release_claim_nonexistent(self):
        reg = CityRegistry()
        assert reg.release_claim("99", "alice") is False

    def test_check_claim(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice")
        assert reg.check_claim("42", "alice") is True
        assert reg.check_claim("42", "bob") is False
        assert reg.check_claim("99", "alice") is False

    def test_check_claim_expired(self):
        reg = CityRegistry()
        now = time.time()
        reg._active_claims["42"] = ClaimTicket(
            thread_id="42", agent_id="alice",
            timestamp=now - 100, expires_at=now - 1,
        )
        assert reg.check_claim("42", "alice") is False

    def test_get_claim_holder(self):
        reg = CityRegistry()
        assert reg.get_claim_holder("42") is None
        reg.request_claim("42", "alice")
        assert reg.get_claim_holder("42") == "alice"

    def test_get_claim_holder_expired(self):
        reg = CityRegistry()
        now = time.time()
        reg._active_claims["42"] = ClaimTicket(
            thread_id="42", agent_id="alice",
            timestamp=now - 100, expires_at=now - 1,
        )
        assert reg.get_claim_holder("42") is None

    def test_purge_expired_claims(self):
        reg = CityRegistry()
        now = time.time()
        reg._active_claims["42"] = ClaimTicket(
            thread_id="42", agent_id="alice",
            timestamp=now - 100, expires_at=now - 1,
        )
        reg._active_claims["43"] = ClaimTicket(
            thread_id="43", agent_id="bob",
            timestamp=now - 100, expires_at=now - 1,
        )
        reg.request_claim("44", "carol")  # active — should survive
        purged = reg.purge_expired_claims()
        assert purged == 2
        assert "42" not in reg._active_claims
        assert "43" not in reg._active_claims
        assert "44" in reg._active_claims

    def test_purge_with_no_expired(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice")
        assert reg.purge_expired_claims() == 0

    def test_stats_includes_claims(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice")
        s = reg.stats()
        assert s["active_claims"] == 1

    def test_multiple_threads_independent(self):
        """Claims on different threads are independent."""
        reg = CityRegistry()
        t1 = reg.request_claim("42", "alice")
        t2 = reg.request_claim("43", "bob")
        assert t1 is not None
        assert t2 is not None
        # alice can't claim bob's thread
        assert reg.request_claim("43", "alice") is None
        # bob can't claim alice's thread
        assert reg.request_claim("42", "bob") is None


class TestClaimPersistence:
    """Claims survive snapshot/restore cycle."""

    def test_snapshot_restore_claims(self):
        reg = CityRegistry()
        reg.request_claim("42", "alice", ttl_seconds=3600)
        snap = reg.snapshot()
        assert "active_claims" in snap
        assert "42" in snap["active_claims"]

        reg2 = CityRegistry()
        reg2.restore(snap)
        assert reg2.check_claim("42", "alice") is True

    def test_restore_skips_expired_claims(self):
        reg = CityRegistry()
        now = time.time()
        reg._active_claims["42"] = ClaimTicket(
            thread_id="42", agent_id="alice",
            timestamp=now - 100, expires_at=now - 1,
        )
        snap = reg.snapshot()

        reg2 = CityRegistry()
        reg2.restore(snap)
        assert reg2.get_claim_holder("42") is None

    def test_restore_empty_claims(self):
        """Restore with no claims key is safe."""
        reg = CityRegistry()
        reg.restore({"key_to_slot": {}, "entity_kinds": {}, "entity_meta": {}})
        assert len(reg._active_claims) == 0


class TestClaimViolationError:
    """ClaimViolationError exception tests."""

    def test_error_attributes(self):
        err = ClaimViolationError("42", "bob", "alice")
        assert err.thread_id == "42"
        assert err.agent_id == "bob"
        assert err.holder == "alice"
        assert "bob" in str(err)
        assert "alice" in str(err)
        assert "42" in str(err)

    def test_is_runtime_error(self):
        err = ClaimViolationError("42", "bob", "alice")
        assert isinstance(err, RuntimeError)
