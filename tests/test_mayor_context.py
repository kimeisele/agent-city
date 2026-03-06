from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from city.mayor_context import MayorContextBridge
from city.mayor_services import MayorServiceBridge
from city.registry import SVC_COUNCIL, CityServiceRegistry


def test_context_bridge_builds_phase_context_and_syncs_services():
    registry = CityServiceRegistry()
    active_agents = {"Alpha"}
    gateway_queue = [{"source": "dm", "text": "hi"}]
    recent_events = [{"type": "AGENT_MESSAGE"}]
    council = object()
    mayor = SimpleNamespace(
        _pokedex=object(),
        _gateway=object(),
        _network=object(),
        _heartbeat_count=7,
        _offline_mode=True,
        _state_path=Path("data/mayor_state.json"),
        _active_agents=active_agents,
        _gateway_queue=gateway_queue,
        _registry=registry,
        _last_audit_time=12.5,
        _recent_events=recent_events,
        _service_bridge=MayorServiceBridge(),
        _council=council,
    )

    ctx = MayorContextBridge().build_phase_context(mayor)

    assert ctx.heartbeat_count == 7
    assert ctx.active_agents is active_agents
    assert ctx.gateway_queue is gateway_queue
    assert ctx.recent_events is recent_events
    assert ctx.last_audit_time == 12.5
    assert ctx.registry.get(SVC_COUNCIL) is council


def test_context_bridge_syncs_last_audit_time_back():
    mayor = SimpleNamespace(_last_audit_time=0.0)
    ctx = SimpleNamespace(last_audit_time=33.0)

    MayorContextBridge().sync_from_phase_context(mayor, ctx)

    assert mayor._last_audit_time == 33.0