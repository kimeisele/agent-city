from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from city.mayor.observation import MayorObservationBridge
from city.registry import CityServiceRegistry, SVC_REFLECTION


def test_observation_bridge_records_execution():
    reflection = MagicMock()
    registry = CityServiceRegistry()
    registry.register(SVC_REFLECTION, reflection)
    mayor = SimpleNamespace(_registry=registry)

    MayorObservationBridge().record_execution(mayor, "DHARMA", 12.5)

    reflection.record_execution.assert_called_once()
    record = reflection.record_execution.call_args.args[0]
    assert record.command == "mayor.heartbeat.DHARMA"
    assert record.success is True
    assert record.duration_ms == 12.5


def test_observation_bridge_buffers_and_trims_events(monkeypatch):
    monkeypatch.setattr(
        "city.mayor.observation.get_config",
        lambda: {"mayor": {"event_buffer_max": 2, "event_buffer_trim": 1}},
    )
    mayor = SimpleNamespace(_recent_events=[])
    bridge = MayorObservationBridge()

    bridge.on_city_event(
        mayor,
        SimpleNamespace(event_type="A", data={"n": 1}, timestamp=datetime(2024, 1, 1, tzinfo=UTC)),
    )
    bridge.on_city_event(
        mayor,
        SimpleNamespace(event_type="B", data={"n": 2}, timestamp=datetime(2024, 1, 2, tzinfo=UTC)),
    )
    bridge.on_city_event(
        mayor,
        SimpleNamespace(event_type="C", data={"n": 3}, timestamp=datetime(2024, 1, 3, tzinfo=UTC)),
    )

    assert len(mayor._recent_events) == 1
    assert mayor._recent_events[0]["type"] == "C"


def test_observation_bridge_wires_anchor_handlers(monkeypatch):
    calls: list[tuple[str, object]] = []
    anchor = SimpleNamespace(
        add_handler=lambda event_type, handler: calls.append((event_type, handler))
    )
    monkeypatch.setattr("vibe_core.ouroboros.ananta_shesha.get_system_anchor", lambda: anchor)
    mayor = SimpleNamespace(_on_city_event=object())

    MayorObservationBridge().wire_event_handlers(mayor)

    assert [event_type for event_type, _ in calls] == [
        "AGENT_REGISTERED",
        "AGENT_UNREGISTERED",
        "AGENT_MESSAGE",
        "AGENT_BROADCAST",
    ]
    assert all(handler is mayor._on_city_event for _, handler in calls)