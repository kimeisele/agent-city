"""Layer 6 Tests — Federation Communication (Relay + Directives + Reports)."""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Phase 1: FederationRelay Unit Tests ───────────────────────────


def test_relay_creation():
    """Relay starts with default mothership and empty state."""
    from city.federation import DEFAULT_MOTHERSHIP, FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        assert relay._mothership_repo == DEFAULT_MOTHERSHIP
        assert relay.last_report == {}
        stats = relay.stats()
        assert stats["mothership"] == DEFAULT_MOTHERSHIP
        assert stats["reports_sent"] == 0
        assert stats["pending_directives"] == 0
    finally:
        shutil.rmtree(tmp)


def test_build_city_report():
    """CityReport contains all required fields."""
    from city.federation import CityReport

    report = CityReport(
        heartbeat=42,
        timestamp=time.time(),
        population=20,
        alive=18,
        dead=2,
        elected_mayor="Agent_Alpha",
        council_seats=6,
        open_proposals=1,
        chain_valid=True,
        recent_actions=["election:mayor=Agent_Alpha"],
        contract_status={"ruff_clean": "passing"},
        mission_results=[],
        directive_acks=["DIR-001"],
    )
    d = report.to_dict()
    assert d["heartbeat"] == 42
    assert d["population"] == 20
    assert d["elected_mayor"] == "Agent_Alpha"
    assert d["chain_valid"] is True
    assert "DIR-001" in d["directive_acks"]


def test_send_report_dry_run():
    """Dry-run logs but doesn't call gh CLI."""
    from city.federation import CityReport, FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _dry_run=True,
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        report = CityReport(
            heartbeat=1, timestamp=time.time(), population=10,
            alive=8, dead=2, elected_mayor="Boss",
            council_seats=4, open_proposals=0, chain_valid=True,
            recent_actions=[], contract_status={},
            mission_results=[], directive_acks=[],
        )
        result = relay.send_report(report)
        assert result is True
        assert relay.last_report["heartbeat"] == 1
        # Report file saved locally
        report_file = tmp / "reports" / "report_1.json"
        assert report_file.exists()
        saved = json.loads(report_file.read_text())
        assert saved["population"] == 10
    finally:
        shutil.rmtree(tmp)


def test_check_directives_empty():
    """No directive files → empty list."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        directives = relay.check_directives()
        assert directives == []
    finally:
        shutil.rmtree(tmp)


def test_check_directives_reads_json():
    """Directive files are read and parsed correctly."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        # Write a test directive
        directive_data = {
            "id": "DIR-001",
            "directive_type": "register_agent",
            "params": {"name": "NewAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }
        (tmp / "directives" / "DIR-001.json").write_text(
            json.dumps(directive_data),
        )

        directives = relay.check_directives()
        assert len(directives) == 1
        assert directives[0].id == "DIR-001"
        assert directives[0].directive_type == "register_agent"
        assert directives[0].params["name"] == "NewAgent"
    finally:
        shutil.rmtree(tmp)


def test_acknowledge_directive():
    """Acknowledging renames .json to .json.done."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        directive_data = {
            "id": "DIR-002",
            "directive_type": "freeze_agent",
            "params": {"name": "BadAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }
        json_path = tmp / "directives" / "DIR-002.json"
        json_path.write_text(json.dumps(directive_data))

        result = relay.acknowledge_directive("DIR-002")
        assert result is True
        assert not json_path.exists()
        assert (tmp / "directives" / "DIR-002.json.done").exists()

        # Second check returns empty (acknowledged directives are skipped)
        directives = relay.check_directives()
        assert len(directives) == 0
    finally:
        shutil.rmtree(tmp)


# ── Phase 2: Directive Execution Tests ────────────────────────────


def _make_mayor_with_federation(tmp_dir, directives_dir=None):
    """Helper: create a Mayor with federation relay in a temp dir."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.federation import FederationRelay
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    db_path = tmp_dir / "city.db"
    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pokedex = Pokedex(db_path=str(db_path), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    relay = FederationRelay(
        _dry_run=True,
        _directives_dir=directives_dir or (tmp_dir / "directives"),
        _reports_dir=tmp_dir / "reports",
    )

    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _state_path=tmp_dir / "mayor_state.json",
        _offline_mode=True,
        _federation=relay,
    )
    return mayor, pokedex, relay


def test_execute_register_agent():
    """register_agent directive → agent registered in Pokedex."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Write directive
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-REG.json").write_text(json.dumps({
            "id": "DIR-REG",
            "directive_type": "register_agent",
            "params": {"name": "FederatedAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run GENESIS (heartbeat 0)
        result = mayor.heartbeat()
        assert result["department"] == "GENESIS"

        # Agent should be registered
        agent = pokedex.get("FederatedAgent")
        assert agent is not None
        assert agent["name"] == "FederatedAgent"

        # Directive should be acknowledged
        assert (directives_dir / "DIR-REG.json.done").exists()
        assert not (directives_dir / "DIR-REG.json").exists()
    finally:
        shutil.rmtree(tmp)


def test_execute_freeze_agent():
    """freeze_agent directive → agent frozen in Pokedex."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Register an agent first (register → citizen status)
        pokedex.register("TargetAgent")
        assert pokedex.get("TargetAgent")["status"] == "citizen"

        # Write freeze directive
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-FRZ.json").write_text(json.dumps({
            "id": "DIR-FRZ",
            "directive_type": "freeze_agent",
            "params": {"name": "TargetAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run GENESIS
        result = mayor.heartbeat()
        assert any("directive:freeze_agent:True" in d for d in result["discovered"])

        # Agent should be frozen
        agent = pokedex.get("TargetAgent")
        assert agent["status"] == "frozen"
    finally:
        shutil.rmtree(tmp)


def test_execute_unknown_directive():
    """Unknown directive type → False, not crash."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        directives_dir = tmp / "directives"
        (directives_dir / "DIR-UNK.json").write_text(json.dumps({
            "id": "DIR-UNK",
            "directive_type": "self_destruct",
            "params": {},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        result = mayor.heartbeat()
        assert any("directive:self_destruct:False" in d for d in result["discovered"])
    finally:
        shutil.rmtree(tmp)


def test_directive_lifecycle():
    """Full lifecycle: write → check → execute → ack → gone."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _dry_run=True,
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )

        # Write directive
        (tmp / "directives" / "DIR-LC.json").write_text(json.dumps({
            "id": "DIR-LC",
            "directive_type": "policy_update",
            "params": {"description": "New slop rule"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Check → found
        directives = relay.check_directives()
        assert len(directives) == 1
        assert directives[0].id == "DIR-LC"

        # Acknowledge → renamed
        relay.acknowledge_directive("DIR-LC")
        assert not (tmp / "directives" / "DIR-LC.json").exists()
        assert (tmp / "directives" / "DIR-LC.json.done").exists()

        # Check again → empty
        directives = relay.check_directives()
        assert len(directives) == 0

        # Ack tracked
        assert "DIR-LC" in relay.pending_acks
    finally:
        shutil.rmtree(tmp)


# ── Phase 3: Mayor Integration Tests ─────────────────────────────


def test_mayor_no_federation_backward_compatible():
    """Mayor with _federation=None works exactly as before."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
        )

        # Run full rotation — no crash, no federation fields in output
        results = mayor.run_cycle(4)
        assert len(results) == 4
        moksha = results[3]
        assert "federation_report_sent" not in moksha["reflection"]
    finally:
        shutil.rmtree(tmp)


def test_genesis_processes_directives():
    """GENESIS processes directive files from federation."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Write two directives
        directives_dir = tmp / "directives"
        for i, name in enumerate(["AgentA", "AgentB"]):
            (directives_dir / f"DIR-{i}.json").write_text(json.dumps({
                "id": f"DIR-{i}",
                "directive_type": "register_agent",
                "params": {"name": name},
                "timestamp": time.time(),
                "source": "mothership",
            }))

        result = mayor.heartbeat()
        assert result["department"] == "GENESIS"

        # Both agents registered
        assert pokedex.get("AgentA") is not None
        assert pokedex.get("AgentB") is not None

        # Both directives acknowledged
        assert (directives_dir / "DIR-0.json.done").exists()
        assert (directives_dir / "DIR-1.json.done").exists()
    finally:
        shutil.rmtree(tmp)


def test_moksha_sends_report():
    """MOKSHA sends federation report (dry-run)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Register some agents for population stats
        pokedex.register("Citizen1")
        pokedex.register("Citizen2")

        # Advance to MOKSHA (heartbeat 3)
        results = mayor.run_cycle(4)
        moksha = results[3]
        assert moksha["department"] == "MOKSHA"
        assert moksha["reflection"].get("federation_report_sent") is True

        # Report saved locally
        report = relay.last_report
        assert report["heartbeat"] == 3
        assert report["population"] >= 2
        assert report["chain_valid"] is True
    finally:
        shutil.rmtree(tmp)


# ── Phase 4: Full Cycle Test ─────────────────────────────────────


def test_full_rotation_with_federation():
    """Full MURALI rotation: GENESIS (directives) → DHARMA → KARMA → MOKSHA (report)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Seed a directive for GENESIS
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-FULL.json").write_text(json.dumps({
            "id": "DIR-FULL",
            "directive_type": "register_agent",
            "params": {"name": "FedCitizen"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run full rotation
        results = mayor.run_cycle(4)
        assert len(results) == 4

        # GENESIS: directive processed
        genesis = results[0]
        assert genesis["department"] == "GENESIS"
        assert any("directive:register_agent:True" in d for d in genesis["discovered"])

        # Agent registered
        assert pokedex.get("FedCitizen") is not None

        # DHARMA: governance ran
        dharma = results[1]
        assert dharma["department"] == "DHARMA"

        # KARMA: operations ran
        karma = results[2]
        assert karma["department"] == "KARMA"

        # MOKSHA: report sent
        moksha = results[3]
        assert moksha["department"] == "MOKSHA"
        assert moksha["reflection"]["federation_report_sent"] is True

        # Report includes the newly registered citizen
        report = relay.last_report
        assert report["population"] >= 1
        assert "DIR-FULL" in report["directive_acks"]

        # Directive file acknowledged
        assert (directives_dir / "DIR-FULL.json.done").exists()
    finally:
        shutil.rmtree(tmp)


# ── Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import unittest
    # Collect all test functions
    test_functions = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    suite = unittest.TestSuite()
    for fn in test_functions:
        suite.addTest(unittest.FunctionTestCase(fn))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
