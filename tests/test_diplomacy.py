"""
Tests for Diplomacy — Peer-to-Peer City Federation.

Covers: DiplomaticState transitions, PeerCity, CityTreaty, DiplomacyLedger,
cross-city passport verification, foreign visa acceptance, and nadi_bridge
diplomatic operations.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def _has_vibe_core() -> bool:
    try:
        import vibe_core.mahamantra  # noqa: F401
        import ecdsa  # noqa: F401
        return True
    except ImportError:
        return False


from city.federation import (  # noqa: E402
    CityTreaty,
    DiplomacyLedger,
    DiplomaticState,
    PeerCity,
    _DIPLOMATIC_TRANSITIONS,
)


# ── Helpers ────────────────────────────────────────────────────────────


@pytest.fixture
def fed_dir(tmp_path):
    d = tmp_path / "federation"
    d.mkdir()
    return d


@pytest.fixture
def ledger(fed_dir):
    return DiplomacyLedger(_federation_dir=fed_dir)


def _report_payload(heartbeat: int = 1, population: int = 10) -> dict:
    return {
        "heartbeat": heartbeat,
        "population": population,
        "chain_valid": True,
        "constitution_hash": "abc123",
    }


# ══════════════════════════════════════════════════════════════════════
# DiplomaticState
# ══════════════════════════════════════════════════════════════════════


class TestDiplomaticState:
    def test_all_states_exist(self):
        assert len(DiplomaticState) == 7

    def test_unknown_can_only_become_discovered(self):
        allowed = _DIPLOMATIC_TRANSITIONS[DiplomaticState.UNKNOWN]
        assert allowed == {DiplomaticState.DISCOVERED}

    def test_severed_is_terminal(self):
        allowed = _DIPLOMATIC_TRANSITIONS[DiplomaticState.SEVERED]
        assert allowed == set()

    def test_suspended_can_recover_or_sever(self):
        allowed = _DIPLOMATIC_TRANSITIONS[DiplomaticState.SUSPENDED]
        assert DiplomaticState.RECOGNIZED in allowed
        assert DiplomaticState.SEVERED in allowed

    def test_all_states_have_transitions(self):
        for state in DiplomaticState:
            assert state in _DIPLOMATIC_TRANSITIONS


# ══════════════════════════════════════════════════════════════════════
# PeerCity
# ══════════════════════════════════════════════════════════════════════


class TestPeerCity:
    def test_roundtrip(self):
        peer = PeerCity(
            repo="user/fork",
            state=DiplomaticState.DISCOVERED,
            discovered_at=time.time(),
            population=5,
        )
        d = peer.to_dict()
        restored = PeerCity.from_dict(d)
        assert restored.repo == "user/fork"
        assert restored.state == DiplomaticState.DISCOVERED
        assert restored.population == 5

    def test_frozen(self):
        peer = PeerCity(
            repo="user/fork",
            state=DiplomaticState.UNKNOWN,
            discovered_at=time.time(),
        )
        with pytest.raises(AttributeError):
            peer.repo = "changed"  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════
# CityTreaty
# ══════════════════════════════════════════════════════════════════════


class TestCityTreaty:
    def test_auto_treaty_id(self):
        treaty = CityTreaty(
            city_a="origin/city",
            city_b="user/fork",
            signed_at=1000.0,
        )
        assert len(treaty.treaty_id) == 16
        assert treaty.treaty_id != ""

    def test_deterministic_treaty_id(self):
        t1 = CityTreaty(city_a="a", city_b="b", signed_at=1000.0)
        t2 = CityTreaty(city_a="a", city_b="b", signed_at=1000.0)
        assert t1.treaty_id == t2.treaty_id

    def test_roundtrip(self):
        treaty = CityTreaty(
            city_a="origin/city",
            city_b="user/fork",
            signed_at=1000.0,
            visa_reciprocity=("temporary", "worker", "resident"),
            prana_exchange_enabled=True,
            prana_exchange_rate=1.5,
            agent_migration_enabled=True,
            migration_visa_class="worker",
            wiki_propagation=True,
        )
        d = treaty.to_dict()
        restored = CityTreaty.from_dict(d)
        assert restored.treaty_id == treaty.treaty_id
        assert restored.visa_reciprocity == ("temporary", "worker", "resident")
        assert restored.prana_exchange_enabled is True
        assert restored.prana_exchange_rate == 1.5
        assert restored.agent_migration_enabled is True
        assert restored.wiki_propagation is True


# ══════════════════════════════════════════════════════════════════════
# DiplomacyLedger
# ══════════════════════════════════════════════════════════════════════


class TestDiplomacyLedger:
    def test_discover_creates_peer(self, ledger):
        peer = ledger.discover("user/fork", _report_payload())
        assert peer.state == DiplomaticState.DISCOVERED
        assert peer.repo == "user/fork"
        assert peer.population == 10

    def test_discover_idempotent(self, ledger):
        ledger.discover("user/fork", _report_payload(heartbeat=1, population=5))
        peer = ledger.discover("user/fork", _report_payload(heartbeat=2, population=15))
        assert peer.population == 15  # updated
        assert peer.state == DiplomaticState.DISCOVERED

    def test_transition_valid(self, ledger):
        ledger.discover("user/fork", _report_payload())
        peer = ledger.transition("user/fork", DiplomaticState.RECOGNIZED)
        assert peer.state == DiplomaticState.RECOGNIZED

    def test_transition_invalid_raises(self, ledger):
        ledger.discover("user/fork", _report_payload())
        with pytest.raises(ValueError, match="Invalid transition"):
            ledger.transition("user/fork", DiplomaticState.FEDERATED)

    def test_transition_unknown_peer_raises(self, ledger):
        with pytest.raises(ValueError, match="Unknown peer"):
            ledger.transition("nonexistent/city", DiplomaticState.DISCOVERED)

    def test_full_progression(self, ledger):
        """Test UNKNOWN → DISCOVERED → RECOGNIZED → ALLIED → FEDERATED."""
        ledger.discover("user/fork", _report_payload())
        ledger.transition("user/fork", DiplomaticState.RECOGNIZED)
        ledger.transition("user/fork", DiplomaticState.ALLIED)
        peer = ledger.transition("user/fork", DiplomaticState.FEDERATED)
        assert peer.state == DiplomaticState.FEDERATED

    def test_suspension_and_recovery(self, ledger):
        ledger.discover("user/fork", _report_payload())
        ledger.transition("user/fork", DiplomaticState.RECOGNIZED)
        ledger.transition("user/fork", DiplomaticState.ALLIED)
        ledger.transition("user/fork", DiplomaticState.SUSPENDED, "treaty violation")
        peer = ledger.transition("user/fork", DiplomaticState.RECOGNIZED, "resolved")
        assert peer.state == DiplomaticState.RECOGNIZED

    def test_severance_is_terminal(self, ledger):
        ledger.discover("user/fork", _report_payload())
        ledger.transition("user/fork", DiplomaticState.SEVERED)
        with pytest.raises(ValueError, match="Invalid transition"):
            ledger.transition("user/fork", DiplomaticState.DISCOVERED)

    def test_sign_treaty(self, ledger):
        ledger.discover("user/fork", _report_payload())
        ledger.transition("user/fork", DiplomaticState.RECOGNIZED)
        ledger.transition("user/fork", DiplomaticState.ALLIED)

        treaty = CityTreaty(
            city_a="origin/city",
            city_b="user/fork",
            signed_at=time.time(),
            visa_reciprocity=("temporary", "worker"),
        )
        signed = ledger.sign_treaty(treaty)
        assert signed.treaty_id != ""

        # Peer now has treaty_id
        peer = ledger.get_peer("user/fork")
        assert peer.treaty_id == signed.treaty_id

    def test_sign_treaty_requires_allied(self, ledger):
        ledger.discover("user/fork", _report_payload())
        treaty = CityTreaty(
            city_a="origin/city",
            city_b="user/fork",
            signed_at=time.time(),
        )
        with pytest.raises(ValueError, match="need allied or federated"):
            ledger.sign_treaty(treaty)

    def test_get_treaty_with(self, ledger):
        ledger.discover("user/fork", _report_payload())
        ledger.transition("user/fork", DiplomaticState.RECOGNIZED)
        ledger.transition("user/fork", DiplomaticState.ALLIED)

        treaty = CityTreaty(
            city_a="origin/city",
            city_b="user/fork",
            signed_at=time.time(),
        )
        ledger.sign_treaty(treaty)
        found = ledger.get_treaty_with("user/fork")
        assert found is not None
        assert found.treaty_id == treaty.treaty_id

    def test_list_peers(self, ledger):
        ledger.discover("a/fork", _report_payload())
        ledger.discover("b/fork", _report_payload())
        assert len(ledger.list_peers()) == 2

    def test_list_peers_filtered(self, ledger):
        ledger.discover("a/fork", _report_payload())
        ledger.discover("b/fork", _report_payload())
        ledger.transition("b/fork", DiplomaticState.RECOGNIZED)
        discovered = ledger.list_peers(state=DiplomaticState.DISCOVERED)
        assert len(discovered) == 1
        assert discovered[0].repo == "a/fork"

    def test_list_allies(self, ledger):
        ledger.discover("a/fork", _report_payload())
        ledger.discover("b/fork", _report_payload())
        ledger.transition("a/fork", DiplomaticState.RECOGNIZED)
        ledger.transition("a/fork", DiplomaticState.ALLIED)
        allies = ledger.list_allies()
        assert len(allies) == 1
        assert allies[0].repo == "a/fork"

    def test_stats(self, ledger):
        ledger.discover("a/fork", _report_payload())
        ledger.discover("b/fork", _report_payload())
        stats = ledger.stats()
        assert stats["total_peers"] == 2
        assert stats["by_state"]["discovered"] == 2

    def test_persistence(self, fed_dir):
        """Ledger survives reload from disk."""
        ledger1 = DiplomacyLedger(_federation_dir=fed_dir)
        ledger1.discover("user/fork", _report_payload())
        ledger1.transition("user/fork", DiplomaticState.RECOGNIZED)

        # Create new ledger from same directory
        ledger2 = DiplomacyLedger(_federation_dir=fed_dir)
        peer = ledger2.get_peer("user/fork")
        assert peer is not None
        assert peer.state == DiplomaticState.RECOGNIZED

    def test_persistence_with_treaty(self, fed_dir):
        ledger1 = DiplomacyLedger(_federation_dir=fed_dir)
        ledger1.discover("user/fork", _report_payload())
        ledger1.transition("user/fork", DiplomaticState.RECOGNIZED)
        ledger1.transition("user/fork", DiplomaticState.ALLIED)
        treaty = CityTreaty(
            city_a="origin/city", city_b="user/fork", signed_at=time.time(),
        )
        ledger1.sign_treaty(treaty)

        ledger2 = DiplomacyLedger(_federation_dir=fed_dir)
        found = ledger2.get_treaty_with("user/fork")
        assert found is not None

    def test_corrupt_ledger_handled(self, fed_dir):
        """Corrupt ledger file doesn't crash — starts fresh."""
        (fed_dir / "diplomacy.json").write_text("not json{{{")
        ledger = DiplomacyLedger(_federation_dir=fed_dir)
        assert len(ledger.list_peers()) == 0


# ══════════════════════════════════════════════════════════════════════
# Cross-City Passport Verification
# ══════════════════════════════════════════════════════════════════════


class TestCrossPassportVerification:
    def test_verify_foreign_passport(self):
        from city.identity import generate_identity
        from city.identity_service import IdentityService
        from city.jiva import derive_jiva

        # City A creates passport
        jiva = derive_jiva("test_agent")
        identity = generate_identity(jiva)
        passport = identity.sign_passport(jiva)

        # City B verifies it (stateless — no prior knowledge of agent)
        svc = IdentityService()
        assert svc.verify_foreign_passport(passport) is True

    def test_verify_foreign_passport_deep(self):
        from city.identity import generate_identity
        from city.identity_service import IdentityService
        from city.jiva import derive_jiva

        jiva = derive_jiva("test_agent")
        identity = generate_identity(jiva)
        passport = identity.sign_passport(jiva)

        svc = IdentityService()
        assert svc.verify_foreign_passport_deep(passport) is True

    def test_forged_passport_fails_deep(self):
        from city.identity import generate_identity
        from city.identity_service import IdentityService
        from city.jiva import derive_jiva

        # Create passport for "alice"
        jiva = derive_jiva("alice")
        identity = generate_identity(jiva)
        passport = identity.sign_passport(jiva)

        # Tamper: claim to be "bob" but keep alice's keys
        passport["agent_name"] = "bob"

        svc = IdentityService()
        # Basic verify passes (signature is valid for the key)
        assert svc.verify_foreign_passport(passport) is True
        # Deep verify fails (fingerprint doesn't match "bob"'s derivation)
        assert svc.verify_foreign_passport_deep(passport) is False

    def test_missing_fields_rejected(self):
        from city.identity_service import IdentityService

        svc = IdentityService()
        assert svc.verify_foreign_passport({}) is False
        assert svc.verify_foreign_passport({"public_key": "x"}) is False


# ══════════════════════════════════════════════════════════════════════
# Cross-City Visa Reciprocity
# ══════════════════════════════════════════════════════════════════════


class TestForeignVisaAcceptance:
    @pytest.fixture
    def immigration(self, tmp_path):
        from city.immigration import ImmigrationService
        db_path = str(tmp_path / "city.db")
        return ImmigrationService(db_path)

    def test_accept_foreign_visa(self, immigration):
        from city.visa import VisaClass, issue_visa

        # Foreign city issued a citizen visa
        foreign = issue_visa(
            agent_name="alice",
            visa_class=VisaClass.CITIZEN,
            sponsor="genesis",
        )
        local = immigration.accept_foreign_visa(
            foreign_visa=foreign.to_dict(),
            source_city="user/fork",
            treaty_visa_class="worker",
        )

        assert local is not None
        assert local.agent_name == "alice"
        assert local.visa_class == VisaClass.WORKER  # capped by treaty
        assert local.lineage_depth == foreign.lineage_depth + 1
        assert "user/fork" in local.remarks
        assert local.sponsor_visa_id == foreign.visa_id

    def test_accept_foreign_visa_temporary(self, immigration):
        from city.visa import VisaClass, issue_visa

        foreign = issue_visa(
            agent_name="bob",
            visa_class=VisaClass.TEMPORARY,
            sponsor="genesis",
        )
        # Treaty allows worker, but foreign is only temporary → gets temporary
        local = immigration.accept_foreign_visa(
            foreign_visa=foreign.to_dict(),
            source_city="user/fork",
            treaty_visa_class="worker",
        )

        assert local is not None
        assert local.visa_class == VisaClass.TEMPORARY

    def test_reject_revoked_foreign_visa(self, immigration):
        from city.visa import VisaClass, issue_visa, revoke_visa

        foreign = issue_visa(
            agent_name="charlie",
            visa_class=VisaClass.CITIZEN,
            sponsor="genesis",
        )
        revoked = revoke_visa(foreign, "bad behavior")

        local = immigration.accept_foreign_visa(
            foreign_visa=revoked.to_dict(),
            source_city="user/fork",
        )
        assert local is None

    def test_reject_invalid_visa_dict(self, immigration):
        local = immigration.accept_foreign_visa(
            foreign_visa={"garbage": True},
            source_city="user/fork",
        )
        assert local is None


# ══════════════════════════════════════════════════════════════════════
# Nadi emit() with target parameter
# ══════════════════════════════════════════════════════════════════════


class TestNadiPeerTarget:
    def test_emit_with_custom_target(self, fed_dir):
        from city.federation_nadi import FederationNadi

        nadi = FederationNadi(_federation_dir=fed_dir)
        nadi.emit("moksha", "city_report", {"heartbeat": 1}, target="user/fork")
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert data[0]["target"] == "user/fork"

    def test_emit_default_target_unchanged(self, fed_dir):
        from city.federation_nadi import FederationNadi

        nadi = FederationNadi(_federation_dir=fed_dir)
        nadi.emit("moksha", "city_report", {"heartbeat": 1})
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert data[0]["target"] == "steward-protocol"


# ══════════════════════════════════════════════════════════════════════
# nadi_bridge.py CLI — Diplomatic Commands
# ══════════════════════════════════════════════════════════════════════


class TestNadiBridgeDiplomacy:
    def test_list_peers_empty(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "list-peers"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == []

    def test_list_allies_empty(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "list-allies"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == []

    def test_diplomacy_stats(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "diplomacy-stats"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        stats = json.loads(result.stdout)
        assert stats["total_peers"] == 0
        assert stats["total_treaties"] == 0

    def test_diplomatic_hello(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path),
             "diplomatic-hello", "--city-repo", "user/my-city"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        resp = json.loads(result.stdout)
        assert resp["emitted"] is True
        assert resp["city_repo"] == "user/my-city"

        # Verify message in outbox
        outbox = tmp_path / "nadi_outbox.json"
        assert outbox.exists()
        data = json.loads(outbox.read_text())
        assert len(data) == 1
        assert data[0]["operation"] == "diplomatic_hello"
        assert data[0]["payload"]["city_repo"] == "user/my-city"
