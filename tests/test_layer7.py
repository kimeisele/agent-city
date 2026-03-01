"""Layer 7 Tests — Config, Council Persistence, Governance Wiring."""

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


if __name__ == "__main__":
    tests = [
        test_config_loads,
        test_config_has_all_sections,
        test_council_persistence_roundtrip,
        test_council_election_survives_restart,
        test_council_no_state_path_no_file,
        test_council_from_dict,
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
