"""Layer 2 Integration Tests — Addressing, Gateway, Network, Mayor, Issues, Manifest.
Linked to GitHub Issue #9.
"""

import sys
import tempfile
import shutil
from pathlib import Path

# Ensure steward-protocol is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Phase 1: Addressing ─────────────────────────────────────────────


def test_address_deterministic():
    """Same name always resolves to the same address."""
    from city.addressing import CityAddressBook

    book = CityAddressBook()
    addr1 = book.resolve("Ronin")
    addr2 = book.resolve("Ronin")
    assert addr1 == addr2
    assert isinstance(addr1, int)
    assert addr1 > 0


def test_address_unique():
    """Different names produce different addresses."""
    from city.addressing import CityAddressBook

    book = CityAddressBook()
    addr_ronin = book.resolve("Ronin")
    addr_zode = book.resolve("zode")
    assert addr_ronin != addr_zode


def test_address_register_and_lookup():
    """Register a cell and look it up by address."""
    from city.addressing import CityAddressBook
    from city.jiva import derive_jiva

    book = CityAddressBook()
    jiva = derive_jiva("Ronin")

    address = book.register("Ronin", jiva.cell)
    assert address == book.resolve("Ronin")

    cell = book.lookup(address)
    assert cell is not None
    assert cell.lifecycle.dna == "Ronin"

    assert book.is_registered("Ronin")
    assert book.registered_count == 1


def test_address_route_header():
    """Route creates a valid MahaHeader between two agents."""
    from city.addressing import CityAddressBook

    book = CityAddressBook()
    header = book.route("Ronin", "zode", operation=42)

    assert header.sravanam == book.resolve("Ronin")
    assert header.kirtanam == book.resolve("zode")
    assert header.pada_sevanam == 42
    assert header.is_valid()


def test_jiva_has_address():
    """Jiva now carries a deterministic city-level address."""
    from city.jiva import derive_jiva

    jiva = derive_jiva("Ronin")
    assert isinstance(jiva.address, int)
    assert jiva.address > 0

    # City address (SHA-256 enhanced) differs from cell sravanam (raw MahaCompression)
    # Both are valid, just at different routing layers
    assert isinstance(jiva.cell.header.sravanam, int)
    assert jiva.cell.header.sravanam > 0

    # Deterministic: same name → same address, always
    jiva2 = derive_jiva("Ronin")
    assert jiva.address == jiva2.address


def test_pokedex_stores_address():
    """Pokedex stores and returns the agent's address."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)

    entry = pdx.discover("Ronin")
    assert "address" in entry
    assert isinstance(entry["address"], int)
    assert entry["address"] > 0

    # Can look up by address
    found = pdx.get_by_address(entry["address"])
    assert found is not None
    assert found["name"] == "Ronin"

    shutil.rmtree(tmpdir)


# ── Phase 2: Gateway ────────────────────────────────────────────────


def test_gateway_process():
    """Gateway processes input through MahaCompression + Buddhi."""
    from city.gateway import CityGateway

    gw = CityGateway()
    result = gw.process("Hello Agent City", source="TestAgent")

    assert result["seed"] > 0
    assert result["source"] == "TestAgent"
    assert result["source_class"] == "external"
    assert result["source_address"] > 0
    assert result["buddhi_function"]  # BuddhiResult.function — carrier/creator/etc.
    assert 1 <= result["buddhi_chapter"] <= 18
    assert result["buddhi_mode"] in ("SATTVA", "RAJAS", "TAMAS")
    assert result["buddhi_prana"] >= 0
    assert isinstance(result["buddhi_is_alive"], bool)
    assert result["input_size"] > 0


def test_gateway_signature_verification():
    """Gateway verifies ECDSA signatures correctly."""
    from city.gateway import CityGateway
    from city.identity import generate_identity
    from city.jiva import derive_jiva

    gw = CityGateway()
    jiva = derive_jiva("Ronin")
    identity = generate_identity(jiva)

    payload = b"test message"
    sig = identity.sign(payload)

    # Valid signature passes
    assert gw.validate_agent_message("Ronin", payload, sig, identity.public_key_pem)

    # Tampered payload fails
    assert not gw.validate_agent_message("Ronin", b"tampered", sig, identity.public_key_pem)


def test_gateway_source_classification():
    """Gateway classifies sources into trust tiers."""
    from city.gateway import _classify_source

    assert _classify_source("ci_pipeline") == "ci"
    assert _classify_source("github_webhook") == "ci"
    assert _classify_source("local_dev") == "local"
    assert _classify_source("agent_prahlad") == "agent"
    assert _classify_source("federation_relay") == "agent"
    assert _classify_source("moltbook_dm") == "agent"
    assert _classify_source("random_input") == "external"


def test_gateway_webhook_rejects_empty_secret():
    """Gateway rejects webhook with empty secret."""
    from city.gateway import CityGateway

    gw = CityGateway()
    result = gw.ingest_github_webhook(b'{"test": 1}', "sha256=abc123", "")
    assert result["status"] == "error"
    assert result["message"] == "missing_secret"


def test_gateway_webhook_rejects_missing_signature():
    """Gateway rejects webhook with missing/invalid signature header."""
    from city.gateway import CityGateway

    gw = CityGateway()
    result = gw.ingest_github_webhook(b'{"test": 1}', "", "valid_secret")
    assert result["status"] == "error"
    assert result["message"] == "invalid_signature_format"


# ── Phase 3: Network ────────────────────────────────────────────────


def test_network_send():
    """Messages route between agents via the network."""
    from city.jiva import derive_jiva
    from city.network import CityNetwork

    net = CityNetwork()
    jiva_a = derive_jiva("AgentA")
    jiva_b = derive_jiva("AgentB")

    net.register_agent("AgentA", jiva_a.cell)
    net.register_agent("AgentB", jiva_b.cell)

    assert net.send("AgentA", "AgentB", "Hello B")
    log = net.get_message_log()
    assert len(log) == 1
    assert log[0]["from_name"] == "AgentA"
    assert log[0]["to_name"] == "AgentB"


def test_network_broadcast():
    """Broadcast reaches all registered agents."""
    from city.jiva import derive_jiva
    from city.network import CityNetwork

    net = CityNetwork()
    for name in ("Agent1", "Agent2", "Agent3"):
        jiva = derive_jiva(name)
        net.register_agent(name, jiva.cell)

    recipients = net.broadcast("Agent1", "Hello everyone")
    assert recipients == 2  # All except sender


def test_network_agent_health():
    """Health check returns cell vitals."""
    from city.jiva import derive_jiva
    from city.network import CityNetwork

    net = CityNetwork()
    jiva = derive_jiva("Ronin")
    net.register_agent("Ronin", jiva.cell)

    health = net.agent_health("Ronin")
    assert health is not None
    assert health["name"] == "Ronin"
    assert health["prana"] > 0
    assert health["is_alive"] is True
    assert health["body_sthula"] is True
    assert health["body_prana"] is True
    assert health["body_purusha"] is True


def test_network_stats():
    """Network stats include agent count and Sesha status."""
    from city.jiva import derive_jiva
    from city.network import CityNetwork

    net = CityNetwork()
    jiva = derive_jiva("Ronin")
    net.register_agent("Ronin", jiva.cell)

    stats = net.stats()
    assert stats["registered_agents"] == 1
    assert "address_book" in stats


# ── Phase 4: Mayor ──────────────────────────────────────────────────


def test_mayor_heartbeat_cycle():
    """Each heartbeat runs a FULL MURALI cycle (all 4 phases)."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    mayor = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
    )

    results = mayor.run_cycle(4)

    assert len(results) == 4
    # Post-MURALI: each heartbeat is a full cycle, department is always "MURALI"
    departments = [r["department"] for r in results]
    assert departments == ["MURALI", "MURALI", "MURALI", "MURALI"]

    # Each result has the right fields
    for r in results:
        assert "heartbeat" in r
        assert "timestamp" in r
        assert "department" in r
        assert "department_idx" in r

    shutil.rmtree(tmpdir)


def test_mayor_enqueue_and_process():
    """Mayor processes gateway queue during KARMA phase within a MURALI heartbeat."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    mayor = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
    )

    # Enqueue items
    mayor.enqueue("TestAgent", "Hello world")
    mayor.enqueue("OtherAgent", "Process this")

    # One heartbeat = full MURALI (GENESIS→DHARMA→KARMA→MOKSHA)
    # KARMA phase within the heartbeat processes the gateway queue
    results = mayor.run_cycle(1)
    result = results[0]
    assert result["department"] == "MURALI"
    # 2 gateway ops processed during the KARMA phase of this heartbeat
    ops = result["operations"]
    gateway_ops = [o for o in ops if o.startswith("processed:")]
    assert len(gateway_ops) == 2

    shutil.rmtree(tmpdir)


def test_mayor_metabolism():
    """DHARMA phase runs cell metabolism."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    # Register an agent first
    pdx.register("Ronin")
    initial_cell = pdx.get_cell("Ronin")
    initial_prana = initial_cell.prana

    mayor = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
    )

    # Run one MURALI heartbeat (all phases in one)
    results = mayor.run_cycle(1)
    murali = results[0]
    assert murali["department"] == "MURALI"

    # Cell should have lost prana (inactive agent)
    cell_after = pdx.get_cell("Ronin")
    assert cell_after.prana < initial_prana

    shutil.rmtree(tmpdir)


def test_mayor_state_persistence():
    """Mayor heartbeat count persists across instances."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)
    state_path = tmpdir / "mayor_state.json"

    mayor1 = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=state_path,
        _offline_mode=True,
    )
    mayor1.run_cycle(4)

    # New instance should resume from heartbeat 4
    mayor2 = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=state_path,
        _offline_mode=True,
    )
    result = mayor2.heartbeat()
    assert result["heartbeat"] == 4  # Continues from where mayor1 left off

    shutil.rmtree(tmpdir)


# ── Phase 5: Issues ─────────────────────────────────────────────────


def test_issue_cell_lifecycle():
    """Issue cells metabolize and track health."""
    from city.issues import CityIssueManager
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    mgr = CityIssueManager()

    # Manually create a cell for an issue (bypasses gh CLI)
    cell = MahaCellUnified.from_content("Test Issue Title", register=False)
    mgr._issue_cells[42] = cell

    health = mgr.get_issue_health(42)
    assert health is not None
    assert health["issue_number"] == 42
    assert health["prana"] > 0
    assert health["is_alive"] is True

    # Metabolize the cell
    cell.metabolize(0)  # No energy
    health2 = mgr.get_issue_health(42)
    assert health2["prana"] < health["prana"]


def test_issue_manager_stats():
    """Issue manager tracks statistics."""
    from city.issues import CityIssueManager
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    mgr = CityIssueManager()
    mgr._issue_cells[1] = MahaCellUnified.from_content("Issue 1", register=False)
    mgr._issue_cells[2] = MahaCellUnified.from_content("Issue 2", register=False)

    stats = mgr.stats()
    assert stats["tracked_issues"] == 2
    assert stats["alive"] == 2
    assert stats["dead"] == 0


# ── Cross-Layer Integration ─────────────────────────────────────────


def test_full_layer2_pipeline():
    """End-to-end: register → address → gateway → network → mayor."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    # Register agents
    pdx.register("AgentA")
    pdx.register("AgentB")

    agent_a = pdx.get("AgentA")
    agent_b = pdx.get("AgentB")
    assert agent_a["address"] != agent_b["address"]

    # Register in network
    cell_a = pdx.get_cell("AgentA")
    cell_b = pdx.get_cell("AgentB")
    network.register_agent("AgentA", cell_a)
    network.register_agent("AgentB", cell_b)

    # Send message
    assert network.send("AgentA", "AgentB", "Hello from A")

    # Process through gateway
    result = gateway.process("Test input", source="AgentA")
    assert result["seed"] > 0
    assert result["source_address"] == agent_a["address"]

    # Run mayor
    mayor = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
    )
    results = mayor.run_cycle(4)
    assert len(results) == 4

    # MOKSHA reflection should report 2 agents
    moksha = results[3]
    assert moksha["reflection"]["chain_valid"] is True
    city_stats = moksha["reflection"]["city_stats"]
    assert city_stats["total"] == 2

    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        # Phase 1: Addressing
        test_address_deterministic,
        test_address_unique,
        test_address_register_and_lookup,
        test_address_route_header,
        test_jiva_has_address,
        test_pokedex_stores_address,
        # Phase 2: Gateway
        test_gateway_process,
        test_gateway_signature_verification,
        # Phase 3: Network
        test_network_send,
        test_network_broadcast,
        test_network_agent_health,
        test_network_stats,
        # Phase 4: Mayor
        test_mayor_heartbeat_cycle,
        test_mayor_enqueue_and_process,
        test_mayor_metabolism,
        test_mayor_state_persistence,
        # Phase 5: Issues
        test_issue_cell_lifecycle,
        test_issue_manager_stats,
        # Cross-Layer
        test_full_layer2_pipeline,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            failed += 1

    print(f"\n=== {passed}/{passed + failed} LAYER 2 TESTS PASSED ===")
    if failed:
        print(f"    {failed} FAILED")
        sys.exit(1)
