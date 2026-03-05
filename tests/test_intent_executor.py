"""
Tests for CityIntentExecutor — Schritt 5: Reactor→Attention→Executor loop.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from city.intent_executor import CityIntentExecutor
from city.reactor import CityIntent


def _intent(signal: str = "zone_empty", priority: str = "high", **ctx) -> CityIntent:
    return CityIntent(signal=signal, priority=priority, context=ctx)


def _mock_ctx(**overrides):
    ctx = MagicMock()
    ctx.registry = MagicMock()
    ctx.registry.get = MagicMock(return_value=None)
    ctx.pokedex = MagicMock()
    ctx.brain = None
    ctx.heartbeat = 42
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


# ── Registration ─────────────────────────────────────────────────────


class TestRegistration:
    def test_builtins_registered(self):
        ex = CityIntentExecutor()
        s = ex.stats()
        assert "spawn_agents" in s["handlers"]
        assert "upgrade_prana_engine" in s["handlers"]
        assert "investigate_prana_drain" in s["handlers"]
        assert "create_healing_mission" in s["handlers"]
        assert "scale_down_cycles" in s["handlers"]
        assert "emergency_energy_injection" in s["handlers"]

    def test_custom_handler(self):
        ex = CityIntentExecutor()
        ex.register("custom", lambda ctx, intent: "ok")
        result = ex.execute(MagicMock(), _intent("x"), "custom")
        assert result == "ok"


# ── Dispatch ─────────────────────────────────────────────────────────


class TestDispatch:
    def test_none_handler(self):
        ex = CityIntentExecutor()
        result = ex.execute(MagicMock(), _intent(), None)
        assert result.startswith("unhandled:")
        assert ex.stats()["unhandled"] == 1

    def test_missing_handler(self):
        ex = CityIntentExecutor()
        result = ex.execute(MagicMock(), _intent(), "nonexistent")
        assert result.startswith("missing_handler:")
        assert ex.stats()["unhandled"] == 1

    def test_handler_error(self):
        ex = CityIntentExecutor()
        ex.register("boom", lambda ctx, i: 1 / 0)
        result = ex.execute(MagicMock(), _intent(), "boom")
        assert result.startswith("error:")
        assert ex.stats()["failed"] == 1

    def test_execute_batch(self):
        ex = CityIntentExecutor()
        ex.register("ok1", lambda c, i: "r1")
        ex.register("ok2", lambda c, i: "r2")
        results = ex.execute_batch(MagicMock(), [
            (_intent("a"), "ok1"),
            (_intent("b"), "ok2"),
            (_intent("c"), None),
        ])
        assert results == ["r1", "r2", "unhandled:c"]


# ── Built-in Handlers ───────────────────────────────────────────────


class TestSpawnHandler:
    def test_spawn_with_spawner(self):
        spawner = MagicMock()
        spawner.promote_eligible.return_value = ["new_agent"]
        ctx = _mock_ctx()
        ctx.registry.get = lambda name: spawner if name == "spawner" else None

        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("zone_empty", zone="ENGINEERING"), "spawn_agents")
        assert "spawned:1" in result
        spawner.promote_eligible.assert_called_once()

    def test_spawn_no_spawner(self):
        ctx = _mock_ctx()
        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("zone_empty"), "spawn_agents")
        assert result == "skip:no_spawner"


class TestInvestigateHandler:
    def test_investigate_with_brain(self):
        ctx = _mock_ctx(brain=MagicMock())
        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("agent_death_spike", deaths=7), "investigate_prana_drain")
        assert "brain_investigate" in result

    def test_investigate_no_brain(self):
        ctx = _mock_ctx(brain=None)
        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("agent_death_spike", deaths=3), "investigate_prana_drain")
        assert "logged:" in result


class TestHealingMissionHandler:
    def test_healing_with_sankalpa(self):
        sankalpa = MagicMock()
        mission = MagicMock()
        mission.id = "heal_contract_abc"
        sankalpa.create_mission.return_value = mission
        ctx = _mock_ctx()
        ctx.registry.get = lambda name: sankalpa if name == "sankalpa" else None

        ex = CityIntentExecutor()
        result = ex.execute(
            ctx, _intent("contract_failing", contract_id="abc"), "create_healing_mission",
        )
        assert "mission_created" in result

    def test_healing_no_sankalpa(self):
        ctx = _mock_ctx()
        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("contract_failing"), "create_healing_mission")
        assert result == "skip:no_sankalpa"


class TestUpgradeHandler:
    def test_upgrade_recommended(self):
        ex = CityIntentExecutor()
        result = ex.execute(
            MagicMock(), _intent("metabolize_slow", avg_ms=650.0, consecutive=3),
            "upgrade_prana_engine",
        )
        assert "upgrade_recommended" in result


class TestScaleDownHandler:
    def test_scale_down(self):
        ex = CityIntentExecutor()
        result = ex.execute(MagicMock(), _intent("heartbeat_timeout"), "scale_down_cycles")
        assert "scale_down_recommended" in result


class TestEnergyInjectionHandler:
    def test_injection(self):
        agent = {"name": "low_agent"}
        cell = MagicMock()
        cell.is_alive = True
        cell.prana = 50
        ctx = _mock_ctx()
        ctx.pokedex.list_citizens.return_value = [agent]
        ctx.pokedex.get_cell.return_value = cell

        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("prana_underflow"), "emergency_energy_injection")
        assert "injected:1" in result
        ctx.pokedex.add_prana.assert_called_once()

    def test_injection_no_pokedex(self):
        ctx = _mock_ctx(pokedex=None)
        ex = CityIntentExecutor()
        result = ex.execute(ctx, _intent("prana_underflow"), "emergency_energy_injection")
        assert result == "skip:no_pokedex"


# ── Router Deindex on Freeze ─────────────────────────────────────────


class TestRouterDeindex:
    def test_router_remove_concept(self):
        """CityRouter.remove() is called when agent is frozen — verify concept."""
        from city.router import CityRouter

        r = CityRouter()
        r.register("agent_a", {
            "capabilities": ["execute"],
            "domain": "ENG",
            "capability_tier": "contributor",
        })
        assert "agent_a" in r.agents_with_capability("execute")

        r.remove("agent_a")
        assert "agent_a" not in r.agents_with_capability("execute")
        assert r.stats()["registered_agents"] == 0
