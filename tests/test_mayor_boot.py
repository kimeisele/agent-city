from __future__ import annotations

from types import SimpleNamespace

from city.mayor_boot import MayorBootBridge
from city.registry import (
    SVC_BRAIN,
    SVC_BRAIN_MEMORY,
    SVC_CONVERSATION_TRACKER,
    CityServiceRegistry,
)


def test_boot_bridge_initializes_defaults_and_restore(monkeypatch, tmp_path):
    calls: list[str] = []

    class FakeExecution:
        pass

    class FakeContext:
        pass

    class FakeObservation:
        def wire_event_handlers(self, mayor):
            calls.append("wire")

    class FakeLifecycle:
        def __init__(self, state_path):
            self.state_path = state_path

        def ensure_storage_dir(self):
            calls.append("ensure")

        def restore_conversation_tracker(self, tracker):
            calls.append("restore_tracker")

        def restore_mayor(self, mayor):
            calls.append("restore_mayor")

    class FakeBrain:
        pass

    class FakeBrainMemory:
        def __init__(self, path):
            self.path = path

        def load(self):
            calls.append(f"brain_memory:{self.path.name}")

    class FakeTracker:
        pass

    monkeypatch.setattr("city.mayor_boot.MayorContextBridge", FakeContext)
    monkeypatch.setattr("city.mayor_boot.MayorExecutionBridge", FakeExecution)
    monkeypatch.setattr("city.mayor_boot.MayorObservationBridge", FakeObservation)
    monkeypatch.setattr("city.mayor_boot.MayorLifecycleBridge", FakeLifecycle)
    monkeypatch.setattr("city.brain.CityBrain", FakeBrain)
    monkeypatch.setattr("city.brain_memory.BrainMemory", FakeBrainMemory)
    monkeypatch.setattr("city.discussions_commands.ConversationTracker", FakeTracker)

    registry = CityServiceRegistry()
    mayor = SimpleNamespace(
        _registry=registry,
        _state_path=tmp_path / "mayor_state.json",
        _context=None,
        _execution=None,
        _observation=None,
        _lifecycle=None,
    )

    MayorBootBridge().bootstrap(mayor)

    assert isinstance(mayor._context, FakeContext)
    assert isinstance(mayor._execution, FakeExecution)
    assert isinstance(mayor._observation, FakeObservation)
    assert isinstance(mayor._lifecycle, FakeLifecycle)
    assert isinstance(registry.get(SVC_BRAIN), FakeBrain)
    brain_memory = registry.get(SVC_BRAIN_MEMORY)
    assert isinstance(brain_memory, FakeBrainMemory)
    assert brain_memory.path == tmp_path / "brain_memory.json"
    assert isinstance(registry.get(SVC_CONVERSATION_TRACKER), FakeTracker)
    assert calls == [
        "ensure",
        "brain_memory:brain_memory.json",
        "restore_tracker",
        "restore_mayor",
        "wire",
    ]


def test_boot_bridge_preserves_preconfigured_services(tmp_path):
    existing_execution = object()
    existing_observation = SimpleNamespace(wire_event_handlers=lambda mayor: None)
    existing_lifecycle = SimpleNamespace(
        ensure_storage_dir=lambda: None,
        restore_conversation_tracker=lambda tracker: None,
        restore_mayor=lambda mayor: None,
    )
    brain = object()
    brain_memory = object()
    tracker = object()
    registry = CityServiceRegistry()
    registry.register_all(
        {
            SVC_BRAIN: brain,
            SVC_BRAIN_MEMORY: brain_memory,
            SVC_CONVERSATION_TRACKER: tracker,
        }
    )
    mayor = SimpleNamespace(
        _registry=registry,
        _state_path=tmp_path / "mayor_state.json",
        _context=object(),
        _execution=existing_execution,
        _observation=existing_observation,
        _lifecycle=existing_lifecycle,
    )

    MayorBootBridge().bootstrap(mayor)

    assert mayor._context is not None
    assert mayor._execution is existing_execution
    assert mayor._observation is existing_observation
    assert mayor._lifecycle is existing_lifecycle
    assert registry.get(SVC_BRAIN) is brain
    assert registry.get(SVC_BRAIN_MEMORY) is brain_memory
    assert registry.get(SVC_CONVERSATION_TRACKER) is tracker


def test_mayor_bootstraps_registry_services(tmp_path):
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

    assert mayor._registry.has(SVC_BRAIN)
    assert mayor._registry.has(SVC_BRAIN_MEMORY)
    assert mayor._registry.has(SVC_CONVERSATION_TRACKER)