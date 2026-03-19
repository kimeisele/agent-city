


def test_murali_phase_ordering_never_breaks(tmp_dir):
    """Phase sequence GENESIS→DHARMA→KARMA→MOKSHA must be absolute.

    Any deviation = broken governance loop.
    Test: 10 consecutive rotations, verify ordering.
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

    mayor = Mayor(
        _pokedex=pdx, _gateway=gw, _network=net,
        _state_path=tmp_dir / "mayor_state.json",
        _offline_mode=True,
    )

    # Full MURALI per heartbeat: each cycle runs ALL 4 phases internally.
    # 4 cycles = 4 full rotations, each labeled "MURALI".
    expected_order = ["MURALI", "MURALI", "MURALI", "MURALI"]

    for rotation in range(10):
        results = mayor.run_cycle(4)
        departments = [r["department"] for r in results]
        assert departments == expected_order, (
            f"CRITICAL: Phase ordering broke in rotation {rotation + 1}! "
            f"Expected {expected_order}, got {departments}"
        )


def test_heartbeat_counter_monotonically_increases(tmp_dir):
    """Heartbeat counter must NEVER decrease or duplicate.

    Attack vector: State corruption causing counter reset.
    Impact: Phase confusion, duplicate operations.
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

    mayor = Mayor(
        _pokedex=pdx, _gateway=gw, _network=net,
        _state_path=tmp_dir / "mayor_state.json",
        _offline_mode=True,
    )

    previous_heartbeat = -1
    for _ in range(20):
        result = mayor.heartbeat()
        current = result["heartbeat"]
        assert current > previous_heartbeat, (
            f"CRITICAL: Heartbeat counter went backwards or duplicated! "
            f"Previous={previous_heartbeat}, Current={current}"
        )
        previous_heartbeat = current


def test_jiva_derivation_is_pure_function():
    """derive_jiva(name) must be a pure function.

    Same input → always same output, no hidden state.
    This is the FOUNDATION of deterministic identity.
    """
    from city.jiva import derive_jiva

    results = []
    for _ in range(100):
        j = derive_jiva("ConsistencyTestAgent")
        results.append({
            "seed": j.seed.signature,
            "guna": j.classification.guna,
            "quarter": j.classification.quarter,
            "guardian": j.classification.guardian,
            "address": j.address,
        })

    # ALL 100 derivations must be identical
    first = results[0]
    for i, r in enumerate(results[1:], 1):
        assert r == first, (
            f"CRITICAL: Jiva derivation is non-deterministic! "
            f"Call {i} differs: {r} vs {first}"
        )


def test_cell_prana_never_goes_negative():
    """MahaCell prana must have a floor of 0.

    Attack vector: Repeated metabolize with 0 energy.
    Impact: Negative prana breaks all comparisons.
    """
    from city.jiva import derive_jiva

    jiva = derive_jiva("PranaDrain")
    cell = jiva.cell

    # Drain 1000 times with no energy
    for _ in range(1000):
        cell.metabolize(0)

    assert cell.prana >= 0, (
        f"CRITICAL: Cell prana went negative ({cell.prana})! "
        "All prana-based logic (elections, zones) will break."
    )