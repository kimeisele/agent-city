"""Layer 7 Tests — Config, Council Persistence, Governance Wiring.
Linked to GitHub Issue #14.
"""

import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Config Tests ───────────────────────────────────────────────────────


def test_config_loads():
    """Config singleton loads city.yaml."""
    from config import get_config
    cfg = get_config()
    assert "mayor" in cfg
    assert cfg["mayor"]["audit_cooldown_s"] == 900


def test_config_has_all_sections():
    """Config has all expected sections."""
    from config import get_config
    cfg = get_config()
    for section in ("mayor", "economy", "governance", "issues",
                    "contracts", "executor", "federation", "network", "database"):
        assert section in cfg, f"Missing config section: {section}"


# ── Council Persistence Tests ──────────────────────────────────────────


def test_council_persistence_roundtrip():
    """Council state survives save/load cycle."""
    from city.council import CityCouncil, ProposalType

    tmpdir = Path(tempfile.mkdtemp())
    state_path = tmpdir / "council_state.json"

    # Create council with state persistence
    council = CityCouncil(_state_path=state_path)

    # Run election
    candidates = [
        {"name": "Alice", "prana": 5000, "guardian": "G1", "position": 1},
        {"name": "Bob", "prana": 3000, "guardian": "G2", "position": 2},
    ]
    council.run_election(candidates, heartbeat_count=0)
    assert council.elected_mayor == "Alice"

    # Submit proposal
    council.propose(
        title="Test Proposal",
        description="A test",
        proposer="Alice",
        proposal_type=ProposalType.POLICY,
        action={"type": "improve"},
        timestamp=1000.0,
    )

    # State file should exist
    assert state_path.exists()

    # Load into new council instance
    council2 = CityCouncil(_state_path=state_path)
    assert council2.elected_mayor == "Alice"
    assert council2.member_count == 2
    assert len(council2.get_open_proposals()) == 1
    assert council2.get_open_proposals()[0].title == "Test Proposal"

    shutil.rmtree(tmpdir)


def test_council_election_survives_restart():
    """Election results survive a restart."""
    from city.council import CityCouncil

    tmpdir = Path(tempfile.mkdtemp())
    state_path = tmpdir / "council_state.json"

    council = CityCouncil(_state_path=state_path)
    candidates = [
        {"name": "X", "prana": 9000, "guardian": "G", "position": 0},
        {"name": "Y", "prana": 7000, "guardian": "G", "position": 1},
        {"name": "Z", "prana": 5000, "guardian": "G", "position": 2},
    ]
    council.run_election(candidates, heartbeat_count=42)

    # Simulate restart
    council2 = CityCouncil(_state_path=state_path)
    assert council2.elected_mayor == "X"
    assert council2.member_count == 3
    assert council2.seats == {0: "X", 1: "Y", 2: "Z"}

    shutil.rmtree(tmpdir)


def test_council_no_state_path_no_file():
    """Council without state_path works (no persistence, no crash)."""
    from city.council import CityCouncil

    council = CityCouncil()
    candidates = [
        {"name": "Solo", "prana": 1000, "guardian": "G", "position": 0},
    ]
    council.run_election(candidates, heartbeat_count=0)
    assert council.elected_mayor == "Solo"


def test_council_from_dict():
    """CityCouncil.from_dict() classmethod works."""
    from city.council import CityCouncil

    data = {
        "seats": {0: "A", 1: "B"},
        "elected_mayor": "A",
        "proposals": {},
        "next_proposal_num": 5,
        "last_election_heartbeat": 100,
    }
    council = CityCouncil.from_dict(data)
    assert council.elected_mayor == "A"
    assert council.member_count == 2


# ── State Reliability (Issue #14 RED tests) ────────────────────────────


def test_council_corrupt_state_recovers_from_backup():
    """#14 RED: corrupt file mid-write -> next load recovers from backup.

    Council state is persisted atomically with a bounded .bak rotation;
    a truncated primary file must recover from the most recent valid backup
    instead of silently resetting to empty state.
    """
    from city.council import CityCouncil, ProposalType

    tmpdir = Path(tempfile.mkdtemp())
    try:
        state_path = tmpdir / "council_state.json"
        council = CityCouncil(_state_path=state_path)
        candidates = [
            {"name": "Alice", "prana": 5000, "guardian": "G1", "position": 1},
            {"name": "Bob", "prana": 3000, "guardian": "G2", "position": 2},
        ]
        council.run_election(candidates, heartbeat_count=0)
        assert council.elected_mayor == "Alice"
        # Second mutation -> second atomic save -> backup of the elected state.
        council.propose(
            title="Test Proposal",
            description="A test",
            proposer="Alice",
            proposal_type=ProposalType.POLICY,
            action={"type": "improve"},
            timestamp=1000.0,
        )

        # A backup of the last valid state must exist after the atomic saves.
        backup = tmpdir / "council_state.json.bak"
        assert backup.exists()
        # No temp residue from the atomic writes.
        assert not list(tmpdir.glob("*.tmp"))

        # Simulate a mid-write crash: truncate the primary state file.
        state_path.write_text('{"seats": {0: "Alice", "elected_mayor": "Alice", "proposals"')

        # Next load must recover the last fully-committed state (election),
        # not silently reset to an empty council.
        council2 = CityCouncil(_state_path=state_path)
        assert council2.elected_mayor == "Alice"
        assert council2.member_count == 2
        assert council2.seats == {0: "Alice", 1: "Bob"}
    finally:
        shutil.rmtree(tmpdir)


def test_mayor_corrupt_state_recovers_from_backup(tmp_dir):
    """#14 RED: corrupt mayor state -> next load recovers from backup.

    Mayor state is persisted atomically with a bounded .bak rotation;
    a truncated primary file must recover counters from the most recent
    valid backup instead of silently resetting to zero.
    """
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pdx = Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)
    gw = CityGateway()
    net = CityNetwork(_address_book=gw.address_book, _gateway=gw)
    state_path = tmp_dir / "mayor_state.json"

    mayor = Mayor(
        _pokedex=pdx, _gateway=gw, _network=net,
        _state_path=state_path, _offline_mode=True,
    )
    mayor._heartbeat_count = 17
    mayor._total_governance_actions = 3
    mayor._total_operations = 5
    mayor._save_state()
    # Second save -> backup of the previous committed state (17/3/5).
    mayor._heartbeat_count = 99
    mayor._save_state()
    assert state_path.exists()
    assert (tmp_dir / "mayor_state.json.bak").exists()

    # Simulate a mid-write crash: truncate the primary state file.
    state_path.write_text('{"heartbeat_count": 99')

    # Next load must recover from the most recent valid backup.
    mayor2 = Mayor(
        _pokedex=pdx, _gateway=gw, _network=net,
        _state_path=state_path, _offline_mode=True,
    )
    assert mayor2._heartbeat_count == 17
    assert mayor2._total_governance_actions == 3
    assert mayor2._total_operations == 5
    result = mayor2.heartbeat()
    assert result["department"] == "MURALI"


def test_state_backup_rotation_is_bounded():
    """Council state backup rotation keeps only the N most recent .bak copies."""
    from city.council import STATE_BACKUPS, CityCouncil

    tmpdir = Path(tempfile.mkdtemp())
    try:
        state_path = tmpdir / "council_state.json"
        council = CityCouncil(_state_path=state_path)
        for i in range(STATE_BACKUPS + 4):
            council.run_election(
                [{"name": f"A{i}", "prana": 1000 + i, "guardian": "G", "position": 1},
                 {"name": "B", "prana": 500, "guardian": "G", "position": 2}],
                heartbeat_count=i,
            )
        backups = sorted(tmpdir.glob("council_state.json.bak*"))
        assert len(backups) == STATE_BACKUPS
        # No temp residue from the atomic writes.
        assert not list(tmpdir.glob("*.tmp"))
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        test_config_loads,
        test_config_has_all_sections,
        test_council_persistence_roundtrip,
        test_council_election_survives_restart,
        test_council_no_state_path_no_file,
        test_council_from_dict,
        test_council_corrupt_state_recovers_from_backup,
        test_mayor_corrupt_state_recovers_from_backup,
        test_state_backup_rotation_is_bounded,
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

    print(f"\n=== {passed}/{passed + failed} LAYER 7 TESTS PASSED ===")
    if failed:
        sys.exit(1)
