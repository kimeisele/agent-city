"""Layer 1 Integration Test — Jiva + MahaCell + Identity + CivicBank + Pokedex.
Linked to GitHub Issue #8.
"""

import sys
import tempfile
import shutil
from pathlib import Path

# Ensure steward-protocol is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_jiva_derivation():
    """Same name always produces same Jiva — via the real Mahamantra VM."""
    from city.jiva import derive_jiva

    j1 = derive_jiva("Ronin")
    j2 = derive_jiva("Ronin")

    # Deterministic: same name → same classification (always)
    assert j1.seed.rama_coordinates == j2.seed.rama_coordinates
    assert j1.seed.signature == j2.seed.signature
    assert j1.classification.guna == j2.classification.guna
    assert j1.classification.quarter == j2.classification.quarter
    assert j1.classification.guardian == j2.classification.guardian
    assert j1.vibration.seed == j2.vibration.seed

    # Verify against known VM output for "Ronin"
    assert j1.classification.guna == "TAMAS"
    assert j1.classification.quarter == "genesis"
    assert j1.classification.guardian == "shambhu"
    assert j1.classification.position == 3
    assert j1.classification.holy_name == "K"
    assert j1.classification.trinity_function == "source"
    assert j1.classification.chapter == 15
    assert j1.vitals.is_alive is True

    # Vibration signature from VM
    assert j1.vibration.element == "prithvi"
    assert j1.vibration.shruti is True


def test_jiva_has_living_cell():
    """Each Jiva carries a MahaCellUnified — the biological substrate."""
    from city.jiva import derive_jiva
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    jiva = derive_jiva("Ronin")

    # Cell exists and is alive
    assert isinstance(jiva.cell, MahaCellUnified)
    assert jiva.cell.is_alive is True
    assert jiva.cell.prana > 0

    jiva2 = derive_jiva("Ronin")
    assert jiva.address == jiva2.address

    # City address (SHA-256 enhanced) differs from cell sravanam (raw MahaCompression)
    # This is by design: cell-level routing uses raw Mahamantra, city-level uses
    # collision-resistant SHA-256 addressing
    assert isinstance(jiva.cell.header.sravanam, int)
    assert jiva.cell.header.sravanam > 0
    assert jiva.cell.header.is_valid()

    # Cell DNA = agent name
    assert jiva.cell.lifecycle.dna == "Ronin"

    # Cell can serialize/deserialize
    cell_bytes = jiva.cell.to_bytes()
    restored, _ = MahaCellUnified.from_bytes(cell_bytes)
    assert restored.lifecycle.dna == "Ronin"
    assert restored.is_alive is True


def test_cell_lifecycle_operations():
    """MahaCellUnified provides real lifecycle: metabolize, apoptosis."""
    from city.jiva import derive_jiva

    jiva = derive_jiva("Ronin")
    cell = jiva.cell

    initial_prana = cell.prana
    assert cell.is_alive

    # Metabolize — costs TRINITY (3) per cycle, gains energy
    new_prana = cell.metabolize(10)
    assert new_prana > 0
    assert cell.is_alive

    # Homeostasis check
    assert cell.homeostasis() is True

    # Apoptosis — death
    cell.apoptosis()
    assert cell.is_alive is False
    assert cell.prana == 0


def test_jiva_different_names():
    """Different names produce different VM-derived identities."""
    from city.jiva import derive_jiva

    j_ronin = derive_jiva("Ronin")
    j_zode = derive_jiva("zode")

    assert j_ronin.seed.rama_coordinates != j_zode.seed.rama_coordinates
    assert j_ronin.vibration.seed != j_zode.vibration.seed
    assert j_ronin.cell.header.sravanam != j_zode.cell.header.sravanam


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


def test_civic_bank_from_steward():
    """CivicBank from steward-protocol works standalone."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))

    # MINT has 1 billion
    assert bank.get_balance("MINT") == 1_000_000_000

    # Mint to agent
    tx = bank.transfer("MINT", "test_agent", 500, "test_grant", "minting")
    assert tx.startswith("TX-")
    assert bank.get_balance("test_agent") == 500

    # Transfer between agents (CivicBank auto-creates receiver account)
    bank.transfer("test_agent", "test_agent_2", 200, "trade", "transfer")
    assert bank.get_balance("test_agent") == 300
    assert bank.get_balance("test_agent_2") == 200

    # Freeze enforcement
    bank.freeze_account("test_agent", "violation")
    assert bank.is_frozen("test_agent")

    # Integrity check
    assert bank.verify_integrity()

    # System stats
    stats = bank.get_system_stats()
    assert stats["accounts"] > 0

    shutil.rmtree(tmpdir)


def test_pokedex_discover():
    """Discover an agent — stores Mahamantra VM data, no identity yet."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)

    entry = pdx.discover("Ronin", moltbook_profile={"karma": 6459, "follower_count": 1423})

    assert entry["name"] == "Ronin"
    assert entry["status"] == "discovered"
    assert entry["classification"]["guna"] == "TAMAS"
    assert entry["classification"]["quarter"] == "genesis"
    assert entry["classification"]["guardian"] == "shambhu"
    assert entry["zone"] == "discovery"
    assert entry["identity"] is None  # Not yet a citizen
    assert entry["oath"] is None
    assert entry["economy"] is None
    assert entry["moltbook"]["karma"] == 6459

    # Idempotent
    entry2 = pdx.discover("Ronin")
    assert entry2["name"] == "Ronin"

    shutil.rmtree(tmpdir)


def test_pokedex_register():
    """Full citizenship: Jiva + Identity + Wallet + Oath."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)

    entry = pdx.register("Ronin", moltbook_profile={"karma": 6459, "follower_count": 1423})

    assert entry["name"] == "Ronin"
    assert entry["status"] == "citizen"

    # Real VM values
    assert entry["classification"]["guna"] == "TAMAS"
    assert entry["classification"]["quarter"] == "genesis"
    assert entry["classification"]["guardian"] == "shambhu"
    assert entry["classification"]["chapter"] == 15
    assert entry["zone"] == "discovery"

    # Identity bound
    assert entry["identity"]["fingerprint"]
    assert entry["identity"]["public_key"]
    assert entry["identity"]["seed_hash"]

    # Constitutional oath signed
    assert entry["oath"]["hash"]
    assert entry["oath"]["signature"]

    # Economy via CivicBank (genesis grant - zone tax)
    from city.seed_constants import GENESIS_GRANT
    expected_balance = GENESIS_GRANT - (GENESIS_GRANT // 10)
    assert entry["economy"]["balance"] == expected_balance  # 108 - 10% zone tax = 98

    # Moltbook metadata
    assert entry["moltbook"]["karma"] == 6459

    # Living MahaCell stored
    cell = pdx.get_cell("Ronin")
    assert cell is not None
    assert cell.is_alive
    assert cell.lifecycle.dna == "Ronin"

    shutil.rmtree(tmpdir)


def test_pokedex_lifecycle():
    """Full lifecycle: discover → citizen → active → frozen → unfrozen."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)

    # Discover
    pdx.discover("TestAgent")
    assert pdx.get("TestAgent")["status"] == "discovered"

    # Register (discover → citizen)
    pdx.register("TestAgent")
    assert pdx.get("TestAgent")["status"] == "citizen"

    # Activate (citizen → active)
    pdx.activate("TestAgent")
    assert pdx.get("TestAgent")["status"] == "active"

    # Freeze (active → frozen)
    pdx.freeze("TestAgent", "test_violation")
    assert pdx.get("TestAgent")["status"] == "frozen"
    assert bank.is_frozen("TestAgent")

    # Unfreeze (frozen → active)
    pdx.unfreeze("TestAgent", "amnesty")
    assert pdx.get("TestAgent")["status"] == "active"

    # Event chain integrity
    events = pdx.get_events("TestAgent")
    assert len(events) >= 4  # discover, register, activate, freeze, unfreeze
    assert pdx.verify_event_chain()

    shutil.rmtree(tmpdir)


def test_pokedex_zones():
    """Agents are assigned to zones based on Mahamantra quarter."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)

    pdx.register("Ronin")  # quarter=genesis → zone=discovery
    ronin = pdx.get("Ronin")
    assert ronin["zone"] == "discovery"

    # List by zone
    discovery_agents = pdx.list_by_zone("discovery")
    assert len(discovery_agents) >= 1

    # Zone treasury got funded (10% of genesis grant)
    zone_balance = bank.get_balance("ZONE_DISCOVERY")
    assert zone_balance >= 10

    shutil.rmtree(tmpdir)


def test_pokedex_stats():
    """City-wide stats work."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)

    pdx.register("Agent1")
    pdx.discover("Agent2")

    s = pdx.stats()
    assert s["total"] == 2
    assert s["citizen"] == 1
    assert s["discovered"] == 1
    assert "zones" in s
    assert "economy" in s
    assert "constitution_hash" in s

    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        test_jiva_derivation,
        test_jiva_has_living_cell,
        test_cell_lifecycle_operations,
        test_jiva_different_names,
        test_identity_deterministic,
        test_identity_unique_per_agent,
        test_sign_and_verify,
        test_civic_bank_from_steward,
        test_pokedex_discover,
        test_pokedex_register,
        test_pokedex_lifecycle,
        test_pokedex_zones,
        test_pokedex_stats,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print(f"\n=== ALL {len(tests)} LAYER 1 TESTS PASSED ===")
