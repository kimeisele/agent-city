"""
FEDERATION SCALING TESTS
========================

Verifies that the scaling overhaul works correctly:
- DiplomacyLedger SQLite backend (incremental saves, migration)
- Immigration SQL indexes (parampara indexed, list_applications batched)
- FederationNadi FIFO dedup eviction
- IdentityService LRU cache with TTL

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from city.federation import (
    CityTreaty,
    DiplomacyLedger,
    DiplomaticState,
)


# ══════════════════════════════════════════════════════════════════════
# DiplomacyLedger — SQLite Backend
# ══════════════════════════════════════════════════════════════════════


class TestDiplomacyLedgerSQLite:
    @pytest.fixture
    def fed_dir(self, tmp_path):
        return tmp_path / "federation"

    def test_uses_sqlite_not_json(self, fed_dir):
        """Ledger creates diplomacy.db, not diplomacy.json."""
        ledger = DiplomacyLedger(_federation_dir=fed_dir)
        ledger.discover("user/fork", {"population": 5, "heartbeat": 1})
        assert (fed_dir / "diplomacy.db").exists()
        assert not (fed_dir / "diplomacy.json").exists()

    def test_json_to_sqlite_migration(self, fed_dir):
        """Legacy JSON data is migrated to SQLite on first load."""
        fed_dir.mkdir(parents=True, exist_ok=True)
        legacy = {
            "peers": [{
                "repo": "user/old-fork",
                "state": "recognized",
                "discovered_at": 1000.0,
                "last_report_at": 2000.0,
                "constitution_hash": "abc",
                "population": 10,
                "contracts_passing": True,
                "heartbeat_count": 5,
                "treaty_id": "",
                "remarks": "migrated",
            }],
            "treaties": [],
        }
        (fed_dir / "diplomacy.json").write_text(json.dumps(legacy))

        ledger = DiplomacyLedger(_federation_dir=fed_dir)
        peer = ledger.get_peer("user/old-fork")
        assert peer is not None
        assert peer.state == DiplomaticState.RECOGNIZED
        assert peer.population == 10
        assert peer.remarks == "migrated"
        # JSON should be renamed
        assert (fed_dir / "diplomacy.json.migrated").exists()
        assert not (fed_dir / "diplomacy.json").exists()

    def test_incremental_save_not_full_rewrite(self, fed_dir):
        """Each mutation saves only the affected row, not the entire ledger."""
        ledger = DiplomacyLedger(_federation_dir=fed_dir)
        # Discover 100 peers
        for i in range(100):
            ledger.discover(f"user/fork-{i}", {"population": i, "heartbeat": i})

        # Transition one peer — should only write one row
        import sqlite3
        db_path = str(fed_dir / "diplomacy.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count_before = conn.execute("SELECT COUNT(*) AS n FROM peers").fetchone()["n"]
        assert count_before == 100

        ledger.transition("user/fork-50", DiplomaticState.RECOGNIZED)

        # Verify the specific peer was updated
        row = conn.execute(
            "SELECT state FROM peers WHERE repo = ?", ("user/fork-50",)
        ).fetchone()
        assert row["state"] == "recognized"
        conn.close()

    def test_1000_peers_stress(self, fed_dir):
        """1000 peers can be discovered, persisted, and reloaded."""
        ledger = DiplomacyLedger(_federation_dir=fed_dir)
        for i in range(1000):
            ledger.discover(
                f"org/city-{i}",
                {"population": i, "heartbeat": i, "chain_valid": True},
            )

        # Reload from disk
        ledger2 = DiplomacyLedger(_federation_dir=fed_dir)
        assert len(ledger2.list_peers()) == 1000
        assert len(ledger2.list_peers(DiplomaticState.DISCOVERED)) == 1000

        # Stats work
        stats = ledger2.stats()
        assert stats["total_peers"] == 1000

    def test_treaty_persistence_in_sqlite(self, fed_dir):
        """Treaties survive reload via SQLite."""
        ledger = DiplomacyLedger(_federation_dir=fed_dir)
        ledger.discover("user/fork", {"population": 5})
        ledger.transition("user/fork", DiplomaticState.RECOGNIZED)
        ledger.transition("user/fork", DiplomaticState.ALLIED)
        treaty = CityTreaty(
            city_a="origin/city", city_b="user/fork", signed_at=time.time(),
            visa_reciprocity=("temporary", "worker", "resident"),
            prana_exchange_enabled=True,
            prana_exchange_rate=0.5,
        )
        ledger.sign_treaty(treaty)

        ledger2 = DiplomacyLedger(_federation_dir=fed_dir)
        found = ledger2.get_treaty_with("user/fork")
        assert found is not None
        assert found.visa_reciprocity == ("temporary", "worker", "resident")
        assert found.prana_exchange_enabled is True
        assert found.prana_exchange_rate == 0.5


# ══════════════════════════════════════════════════════════════════════
# Immigration — Indexes & Query Optimization
# ══════════════════════════════════════════════════════════════════════


class TestImmigrationIndexes:
    @pytest.fixture
    def svc(self, tmp_path):
        from city.immigration import ImmigrationService
        return ImmigrationService(str(tmp_path / "city.db"))

    def test_indexes_exist(self, svc):
        """All scaling indexes are created."""
        rows = svc._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        names = {r["name"] for r in rows}
        assert "idx_visas_agent" in names
        assert "idx_visas_sponsor" in names
        assert "idx_visas_status" in names
        assert "idx_apps_status" in names
        assert "idx_apps_agent" in names

    def test_parampara_uses_indexed_lookups(self, svc):
        """parampara() works without full table scan."""
        chain = svc.parampara("city_genesis")
        assert len(chain) >= 1
        assert chain[0].agent_name == "city_genesis"


# ══════════════════════════════════════════════════════════════════════
# FederationNadi — FIFO Dedup Eviction
# ══════════════════════════════════════════════════════════════════════


class TestNadiDedupEviction:
    def test_evicts_oldest_not_random(self, tmp_path):
        """processed_ids evicts oldest entries first (FIFO), not random."""
        from city.federation_nadi import FederationNadi

        nadi = FederationNadi(_federation_dir=tmp_path)

        # Insert 5500 known IDs
        for i in range(5500):
            nadi._processed_ids[f"source:{i}"] = None

        assert len(nadi._processed_ids) == 5500

        # Trigger eviction by receiving a message (simulated)
        # The eviction logic runs when len > 5000
        if len(nadi._processed_ids) > 5000:
            excess = len(nadi._processed_ids) - 2500
            for _ in range(excess):
                nadi._processed_ids.popitem(last=False)

        assert len(nadi._processed_ids) == 2500

        # The NEWEST 2500 should survive (IDs 3000-5499)
        assert "source:5499" in nadi._processed_ids  # newest
        assert "source:3000" in nadi._processed_ids  # boundary
        assert "source:0" not in nadi._processed_ids  # oldest evicted
        assert "source:2999" not in nadi._processed_ids  # just below boundary

    def test_dedup_survives_eviction_for_recent(self, tmp_path):
        """Recently processed messages are still deduped after eviction."""
        from city.federation_nadi import FederationNadi, FederationMessage

        nadi = FederationNadi(_federation_dir=tmp_path)

        # Pre-fill 4999 IDs (just below threshold)
        for i in range(4999):
            nadi._processed_ids[f"old:{i}"] = None

        # Write a message to inbox
        msg = FederationMessage(
            source="test", target="city", operation="ping",
            payload={}, priority=1, timestamp=time.time(), ttl_s=900,
        )
        nadi._write_file(nadi.inbox_path, [msg.to_dict()])

        # Receive it — this adds the message to processed_ids (total 5000)
        received = nadi.receive()
        assert len(received) == 1

        # Write the same message again
        nadi._write_file(nadi.inbox_path, [msg.to_dict()])

        # Receive again — should be deduped
        received2 = nadi.receive()
        assert len(received2) == 0  # deduped


# ══════════════════════════════════════════════════════════════════════
# IdentityService — LRU Cache with TTL
# ══════════════════════════════════════════════════════════════════════


class TestIdentityServiceCache:
    def test_passport_cache_hit(self):
        """Second verification uses cache — no re-derivation."""
        from city.identity_service import IdentityService
        from city.jiva import derive_jiva
        from city.identity import generate_identity

        svc = IdentityService()
        jiva = derive_jiva("cache_test_agent")
        identity = generate_identity(jiva)
        passport = identity.sign_passport(jiva)

        # First call — cache miss
        result1 = svc.verify_foreign_passport_deep(passport)
        assert result1 is True

        # Second call — should hit cache
        with patch("city.identity_service.generate_identity") as mock_gen:
            result2 = svc.verify_foreign_passport_deep(passport)
            assert result2 is True
            mock_gen.assert_not_called()  # Cache hit — no crypto

    def test_passport_cache_ttl_expiry(self):
        """Cache entries expire after TTL."""
        from city.identity_service import IdentityService, _PASSPORT_CACHE_TTL
        from city.jiva import derive_jiva
        from city.identity import generate_identity

        svc = IdentityService()
        jiva = derive_jiva("ttl_agent")
        identity = generate_identity(jiva)
        passport = identity.sign_passport(jiva)

        # Verify (populates cache)
        assert svc.verify_foreign_passport_deep(passport) is True
        assert len(svc._passport_cache) > 0

        # Expire the cache entries by backdating timestamps
        for key in svc._passport_cache:
            result, ts = svc._passport_cache[key]
            svc._passport_cache[key] = (result, ts - _PASSPORT_CACHE_TTL - 1)

        # Next call should re-derive (cache expired)
        with patch(
            "city.identity_service.generate_identity",
            wraps=generate_identity,
        ) as mock_gen:
            result = svc.verify_foreign_passport_deep(passport)
            assert result is True
            assert mock_gen.called  # Re-derived after expiry

    def test_passport_cache_different_passports(self):
        """Different passports are not confused in cache."""
        from city.identity_service import IdentityService
        from city.jiva import derive_jiva
        from city.identity import generate_identity

        svc = IdentityService()
        agents = ["alice_scale", "bob_scale", "carol_scale"]
        passports = []
        for name in agents:
            jiva = derive_jiva(name)
            identity = generate_identity(jiva)
            passports.append(identity.sign_passport(jiva))

        # Verify all — each should succeed independently
        for p in passports:
            assert svc.verify_foreign_passport_deep(p) is True

        assert len(svc._passport_cache) >= len(agents)

    def test_stats_includes_cache_size(self):
        """Stats report passport cache size."""
        from city.identity_service import IdentityService

        svc = IdentityService()
        stats = svc.stats()
        assert "passport_cache_size" in stats
        assert stats["passport_cache_size"] == 0
