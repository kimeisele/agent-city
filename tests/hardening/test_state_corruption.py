import json

import pytest


def test_corrupted_mayor_state_survives(tmp_dir):
    """Mayor must start cleanly even if state file is corrupted.

    Attack vector: Write garbage to mayor_state.json.
    Impact: Mayor cannot restart after crash.
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

    # Corrupt the state file
    state_path.write_text("{{{{CORRUPT_JSON_!@#$%")

    # Mayor must still initialize
    try:
        mayor = Mayor(
            _pokedex=pdx, _gateway=gw, _network=net,
            _state_path=state_path, _offline_mode=True,
        )
        result = mayor.heartbeat()
        assert result["department"] == "MURALI"
    except json.JSONDecodeError:
        pytest.fail(
            "VULNERABILITY: Corrupted state file crashes Mayor! "
            "System cannot recover from disk corruption."
        )


def test_corrupted_council_state_survives(tmp_dir):
    """Council must start cleanly even if state file is corrupted.

    Attack vector: Write garbage to council_state.json.
    Impact: Council cannot restart after crash.
    """
    from city.council import CityCouncil

    state_path = tmp_dir / "council_state.json"
    state_path.write_text("NOT_VALID_JSON{{{}")

    # Council must still initialize
    try:
        council = CityCouncil(_state_path=state_path)
        assert council.elected_mayor is None
        assert council.member_count == 0
    except (json.JSONDecodeError, KeyError):
        pytest.fail(
            "VULNERABILITY: Corrupted council state crashes initialization!"
        )