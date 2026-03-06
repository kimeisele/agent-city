from __future__ import annotations

from types import SimpleNamespace

from city.mayor_services import MayorServiceBridge
from city.registry import SVC_COUNCIL, SVC_IMMUNE, CityServiceRegistry


def test_service_bridge_migrates_legacy_field():
    immune = object()
    registry = CityServiceRegistry()
    mayor = SimpleNamespace(_registry=registry, _immune=immune)

    MayorServiceBridge().sync_legacy_services(mayor)

    assert registry.get(SVC_IMMUNE) is immune


def test_service_bridge_preserves_existing_registry_service():
    existing = object()
    replacement = object()
    registry = CityServiceRegistry()
    registry.register(SVC_IMMUNE, existing)
    mayor = SimpleNamespace(_registry=registry, _immune=replacement)

    MayorServiceBridge().sync_legacy_services(mayor)

    assert registry.get(SVC_IMMUNE) is existing


def test_mayor_picks_up_post_init_service_mutation(tmp_path):
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp_path / "economy.db"))
    pokedex = Pokedex(db_path=str(tmp_path / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)
    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _state_path=tmp_path / "mayor_state.json",
        _offline_mode=True,
    )
    council = object()

    mayor._council = council
    mayor._build_ctx()

    assert mayor._registry.get(SVC_COUNCIL) is council