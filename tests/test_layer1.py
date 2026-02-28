"""Layer 1 Integration Test — Jiva + Identity + Bank + Pokedex."""

import sys
from pathlib import Path

# Ensure steward-protocol is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_jiva_derivation():
    """Same name always produces same Jiva."""
    from city.jiva import derive_jiva

    j1 = derive_jiva("Ronin")
    j2 = derive_jiva("Ronin")
    assert j1.seed.rama_coordinates == j2.seed.rama_coordinates
    assert j1.seed.signature == j2.seed.signature
    assert j1.classification.varna == j2.classification.varna
    assert j1.classification.guna == "TAMAS"
    assert j1.classification.quarter == "DHARMA"
    assert j1.classification.varna == "JALAJA"
    assert j1.vitals.prana == 17


def test_identity_deterministic():
    """Same Jiva always produces same ECDSA keys."""
    from city.identity import generate_identity
    from city.jiva import derive_jiva

    jiva = derive_jiva("Ronin")
    id1 = generate_identity(jiva)
    id2 = generate_identity(jiva)
    assert id1.fingerprint == id2.fingerprint
    assert id1.public_key_pem == id2.public_key_pem
    assert id1.private_key_pem == id2.private_key_pem


def test_identity_unique_per_agent():
    """Different names produce different keys."""
    from city.identity import generate_identity
    from city.jiva import derive_jiva

    id_ronin = generate_identity(derive_jiva("Ronin"))
    id_zode = generate_identity(derive_jiva("zode"))
    assert id_ronin.fingerprint != id_zode.fingerprint


def test_sign_and_verify():
    """Signature roundtrip works."""
    from city.identity import generate_identity
    from city.jiva import derive_jiva

    jiva = derive_jiva("Ronin")
    identity = generate_identity(jiva)

    payload = b"claim my jiva"
    sig = identity.sign(payload)
    assert identity.verify(payload, sig)
    assert not identity.verify(b"tampered", sig)


def test_passport():
    """Passport is signed and verifiable."""
    from city.identity import generate_identity, verify_ownership
    from city.jiva import derive_jiva

    jiva = derive_jiva("Ronin")
    identity = generate_identity(jiva)
    passport = identity.sign_passport(jiva)

    assert passport["agent_name"] == "Ronin"
    assert passport["fingerprint"] == identity.fingerprint

    # Verify the passport signature
    assert verify_ownership(
        passport,
        passport["passport_data"].encode(),
        passport["passport_signature"],
    )


def test_bank():
    """Bank operations work standalone."""
    from city.bank import CityBank

    bank = CityBank(db_path="/tmp/agent_city_test_bank.db")
    bank.create_account("test_agent")
    tx = bank.mint("test_agent", 500, "test_grant")
    assert tx.startswith("TX-")
    assert bank.get_balance("test_agent") == 500

    bank.create_account("test_agent_2")
    bank.transfer("test_agent", "test_agent_2", 200, "trade")
    assert bank.get_balance("test_agent") == 300
    assert bank.get_balance("test_agent_2") == 200

    assert bank.verify_integrity()

    # Cleanup
    Path("/tmp/agent_city_test_bank.db").unlink(missing_ok=True)


def test_pokedex_register():
    """Full registration: Jiva + Identity + Wallet."""
    from city.bank import CityBank
    from city.pokedex import Pokedex

    import tempfile
    tmpdir = Path(tempfile.mkdtemp())
    pokedex_path = tmpdir / "pokedex.json"
    bank = CityBank(db_path=str(tmpdir / "economy.db"))

    pdx = Pokedex(pokedex_path=pokedex_path, bank=bank)
    entry = pdx.register("Ronin", moltbook_profile={"karma": 6459, "follower_count": 1423})

    assert entry["name"] == "Ronin"
    assert entry["status"] == "citizen"
    assert entry["classification"]["guna"] == "TAMAS"
    assert entry["classification"]["varna"] == "JALAJA"
    assert entry["identity"]["fingerprint"]
    assert entry["passport"]["signature"]
    assert entry["economy"]["balance"] == 100
    assert entry["moltbook"]["karma"] == 6459

    # Deterministic — same name, same identity
    assert pdx.get("Ronin")["identity"]["fingerprint"] == entry["identity"]["fingerprint"]

    stats = pdx.stats()
    assert stats["citizens"] == 1
    assert stats["total"] == 1

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    test_jiva_derivation()
    print("OK test_jiva_derivation")
    test_identity_deterministic()
    print("OK test_identity_deterministic")
    test_identity_unique_per_agent()
    print("OK test_identity_unique_per_agent")
    test_sign_and_verify()
    print("OK test_sign_and_verify")
    test_passport()
    print("OK test_passport")
    test_bank()
    print("OK test_bank")
    test_pokedex_register()
    print("OK test_pokedex_register")
    print("\n=== ALL LAYER 1 TESTS PASSED ===")
