"""CityServiceRegistry Tests — Lightweight DI for Mayor Services."""

import shutil
import sys
import tempfile
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── CityServiceRegistry Unit Tests ─────────────────────────────────


def test_register_and_get():
    """register() stores, get() retrieves."""
    from city.registry import CityServiceRegistry

    reg = CityServiceRegistry()
    obj = object()
    reg.register("test_svc", obj)
    assert reg.get("test_svc") is obj


def test_get_unknown_returns_none():
    """get() on unknown name returns None."""
    from city.registry import CityServiceRegistry

    reg = CityServiceRegistry()
    assert reg.get("nonexistent") is None


def test_overwrite_service():
    """Second register() overwrites the first."""
    from city.registry import CityServiceRegistry

    reg = CityServiceRegistry()
    first = object()
    second = object()
    reg.register("svc", first)
    reg.register("svc", second)
    assert reg.get("svc") is second


def test_has_check():
    """has() returns correct boolean."""
    from city.registry import CityServiceRegistry

    reg = CityServiceRegistry()
    assert reg.has("missing") is False
    reg.register("present", object())
    assert reg.has("present") is True


def test_names_and_stats():
    """names() and stats() reflect registered services."""
    from city.registry import CityServiceRegistry

    reg = CityServiceRegistry()
    reg.register("a", 1)
    reg.register("b", 2)
    assert set(reg.names()) == {"a", "b"}
    stats = reg.stats()
    assert stats["registered"] == 2
    assert set(stats["services"]) == {"a", "b"}


def test_phase_context_property_access():
    """PhaseContext properties delegate to registry."""
    from city.phases import PhaseContext
    from city.registry import SVC_LEARNING, CityServiceRegistry

    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gw = CityGateway()
        net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

        reg = CityServiceRegistry()
        sentinel = object()
        reg.register(SVC_LEARNING, sentinel)

        ctx = PhaseContext(
            pokedex=pdx, gateway=gw, network=net,
            heartbeat_count=0, offline_mode=True,
            state_path=tmp / "state.json",
            registry=reg,
        )
        assert ctx.learning is sentinel
        assert ctx.contracts is None  # not registered
        assert ctx.immune is None
    finally:
        shutil.rmtree(tmp)


def test_phase_context_legacy_kwargs():
    """PhaseContext accepts legacy kwargs and migrates to registry."""
    from city.phases import PhaseContext
    from city.registry import SVC_SANKALPA

    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gw = CityGateway()
        net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

        sentinel = object()
        ctx = PhaseContext(
            pokedex=pdx, gateway=gw, network=net,
            heartbeat_count=0, offline_mode=True,
            state_path=tmp / "state.json",
            sankalpa=sentinel,  # legacy kwarg
        )
        assert ctx.sankalpa is sentinel
        assert ctx.registry.has(SVC_SANKALPA)
    finally:
        shutil.rmtree(tmp)


def test_mayor_with_registry():
    """Mayor boots with registry, runs full cycle."""
    from city.registry import SVC_IMMUNE, CityServiceRegistry

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gw = CityGateway()
        net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

        reg = CityServiceRegistry()
        # Register nothing — should still run

        mayor = Mayor(
            _pokedex=pdx, _gateway=gw, _network=net,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _registry=reg,
        )
        results = mayor.run_cycle(4)
        assert len(results) == 4
        assert not reg.has(SVC_IMMUNE)  # nothing registered
    finally:
        shutil.rmtree(tmp)


def test_mayor_legacy_kwargs_migrate():
    """Mayor legacy kwargs (_immune=...) get migrated to registry."""
    from city.immune import CityImmune
    from city.registry import SVC_IMMUNE

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gw = CityGateway()
        net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

        immune = CityImmune()

        mayor = Mayor(
            _pokedex=pdx, _gateway=gw, _network=net,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _immune=immune,  # legacy kwarg
        )
        # Should have been migrated to registry
        assert mayor._registry.has(SVC_IMMUNE)
        assert mayor._registry.get(SVC_IMMUNE) is immune
    finally:
        shutil.rmtree(tmp)


# ── Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import unittest

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
