import json

import pytest


def test_corrupted_mayor_state_survives(tmp_dir):
    """Mayor must recover from a valid backup when state file is corrupted.

    Attack vector: Truncate mayor_state.json mid-write (crash).
    Impact: Without recovery the Mayor restarts with zeroed counters.
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

    # Persist a valid mayor state so a backup exists.
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

    # Corrupt the primary state file (mid-write crash simulation)
    state_path.write_text("{{{{CORRUPT_JSON_!@#$%")

    # Mayor must initialize and RECOVER from backup (data preserved, not reset)
    try:
        mayor2 = Mayor(
            _pokedex=pdx, _gateway=gw, _network=net,
            _state_path=state_path, _offline_mode=True,
        )
        assert mayor2._heartbeat_count == 17
        assert mayor2._total_governance_actions == 3
        assert mayor2._total_operations == 5
        result = mayor2.heartbeat()
        assert result["department"] == "MURALI"
    except json.JSONDecodeError:
        pytest.fail(
            "VULNERABILITY: Corrupted state file crashes Mayor! "
            "System cannot recover from disk corruption."
        )


def test_corrupted_council_state_survives(tmp_dir):
    """Council must recover from a valid backup when state file is corrupted.

    Attack vector: Truncate council_state.json mid-write (crash).
    Impact: Without recovery the council loses elected seats + mayor.
    """
    from city.council import CityCouncil, ProposalType

    state_path = tmp_dir / "council_state.json"

    # Persist a valid elected council so a backup exists.
    council = CityCouncil(_state_path=state_path)
    council.run_election(
        [
            {"name": "Alice", "prana": 5000, "guardian": "G1", "position": 1},
            {"name": "Bob", "prana": 3000, "guardian": "G2", "position": 2},
        ],
        heartbeat_count=0,
    )
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

    # Corrupt the primary state file (mid-write crash simulation)
    state_path.write_text("NOT_VALID_JSON{{{")

    # Council must initialize and RECOVER from backup (data preserved, not reset)
    try:
        council2 = CityCouncil(_state_path=state_path)
        assert council2.elected_mayor == "Alice"
        assert council2.member_count == 2
        assert council2.seats == {0: "Alice", 1: "Bob"}
    except (json.JSONDecodeError, KeyError):
        pytest.fail(
            "VULNERABILITY: Corrupted council state crashes initialization!"
        )
