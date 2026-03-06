from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from city.mayor.execution import MayorExecutionBridge
from city.registry import CityServiceRegistry


def test_execution_bridge_routes_genesis(monkeypatch):
    from city.phases import genesis

    monkeypatch.setattr(genesis, "execute", lambda ctx: ["AgentA"])
    ctx = SimpleNamespace(last_audit_time=0.0)
    synced = []
    mayor = SimpleNamespace(
        _heartbeat_count=0,
        _registry=CityServiceRegistry(),
        _build_ctx=lambda: ctx,
        _sync_from_ctx=lambda phase_ctx: synced.append(phase_ctx),
        _offline_mode=True,
        _immune=None,
    )

    result = MayorExecutionBridge().run_heartbeat(mayor)

    assert result["department"] == "GENESIS"
    assert result["department_idx"] == 0
    assert result["discovered"] == ["AgentA"]
    assert synced == [ctx]


def test_execution_bridge_runs_moksha_self_diagnostics(monkeypatch):
    from city.phases import moksha

    monkeypatch.setattr(moksha, "execute", lambda ctx: {"chain_valid": True})
    immune = MagicMock()
    immune.run_self_diagnostics.return_value = ["heal-1", "heal-2"]
    mayor = SimpleNamespace(
        _heartbeat_count=3,
        _registry=CityServiceRegistry(),
        _build_ctx=lambda: SimpleNamespace(last_audit_time=0.0),
        _sync_from_ctx=lambda phase_ctx: None,
        _offline_mode=False,
        _immune=immune,
    )

    result = MayorExecutionBridge().run_heartbeat(mayor)

    assert result["department"] == "MOKSHA"
    assert result["reflection"]["chain_valid"] is True
    assert result["reflection"]["immune_heals"] == 2
    immune.run_self_diagnostics.assert_called_once()