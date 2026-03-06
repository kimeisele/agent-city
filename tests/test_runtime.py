from __future__ import annotations

import json
import logging
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.runtime import (
    CityRuntime,
    RuntimeStatePaths,
    bootstrap_steward_substrate,
    build_daemon_service,
    persist_city_runtime,
)
from city.mayor_lifecycle import MayorLifecycleBridge
from city.supervision import CitySupervisionBridge


def test_runtime_state_paths_from_db_path(tmp_path):
    paths = RuntimeStatePaths.from_db_path(tmp_path / "city.db")

    assert paths.mayor_state_path == tmp_path / "mayor_state.json"
    assert paths.bridge_state_path == tmp_path / "bridge_state.json"
    assert paths.assistant_state_path == tmp_path / "assistant_state.json"
    assert paths.discussions_state_path == tmp_path / "discussions_state.json"
    assert paths.venu_state_path == tmp_path / "venu_state.bin"
    assert paths.city_registry_state_path == tmp_path / "city_registry_state.json"


def test_bootstrap_steward_substrate_calls_mahamantra_bootstrap(monkeypatch):
    calls: list[dict] = []

    class FakeBootMode(Enum):
        FULL = "full"
        MINIMAL = "minimal"

    fake_pkg = ModuleType("vibe_core")
    fake_pkg.__path__ = []
    fake_mod = ModuleType("vibe_core.mahamantra")
    fake_mod.BootMode = FakeBootMode
    fake_mod.mahamantra = SimpleNamespace(
        bootstrap=lambda **kwargs: calls.append(kwargs),
    )

    monkeypatch.setitem(sys.modules, "vibe_core", fake_pkg)
    monkeypatch.setitem(sys.modules, "vibe_core.mahamantra", fake_mod)

    bootstrap_steward_substrate(logging.getLogger("test.runtime"), silent=True, lazy=False)

    assert calls == [{"silent": True, "lazy": False}]


def test_persist_city_runtime_saves_snapshots_and_checkpoints(tmp_path, monkeypatch):
    fake_pkg = ModuleType("vibe_core")
    fake_pkg.__path__ = []
    fake_mod = ModuleType("vibe_core.mahamantra")

    class FakeVenu:
        tick = 7

        def to_bytes(self):
            return b"venu-state"

    fake_mod.BootMode = Enum("FakeBootMode", {"FULL": "full"})
    fake_mod.mahamantra = SimpleNamespace(venu=FakeVenu())
    monkeypatch.setitem(sys.modules, "vibe_core", fake_pkg)
    monkeypatch.setitem(sys.modules, "vibe_core.mahamantra", fake_mod)

    saved_city_registry = {"entities": ["sys_mayor"]}
    monkeypatch.setattr(
        "city.city_registry.get_city_registry",
        lambda: SimpleNamespace(snapshot=lambda: saved_city_registry),
    )

    checkpoint_calls: list[str] = []
    fake_conn = SimpleNamespace(
        execute=lambda sql: checkpoint_calls.append(sql),
        close=lambda: checkpoint_calls.append("close"),
    )
    fake_pokedex = SimpleNamespace(_conn=fake_conn)

    bridge = SimpleNamespace(snapshot=lambda: {"bridge": True})
    assistant = SimpleNamespace(snapshot=lambda: {"assistant": 1})
    discussions = SimpleNamespace(snapshot=lambda: {"discussions": [1, 2]})
    runtime = CityRuntime(
        db_path=tmp_path / "city.db",
        registry=SimpleNamespace(),
        mayor=SimpleNamespace(_moltbook_bridge=bridge),
        pokedex=fake_pokedex,
        factory_stats={},
        state_paths=RuntimeStatePaths.from_db_path(tmp_path / "city.db"),
        assistant=assistant,
        discussions=discussions,
    )

    persist_city_runtime(runtime, logging.getLogger("test.runtime"))

    assert json.loads(runtime.state_paths.bridge_state_path.read_text()) == {"bridge": True}
    assert json.loads(runtime.state_paths.assistant_state_path.read_text()) == {"assistant": 1}
    assert json.loads(runtime.state_paths.discussions_state_path.read_text()) == {
        "discussions": [1, 2]
    }
    assert runtime.state_paths.venu_state_path.read_bytes() == b"venu-state"
    assert (
        json.loads(runtime.state_paths.city_registry_state_path.read_text())
        == saved_city_registry
    )
    assert checkpoint_calls == ["PRAGMA wal_checkpoint(TRUNCATE)", "close"]


def test_build_daemon_service_reuses_runtime_supervision():
    mayor = SimpleNamespace()
    supervision = CitySupervisionBridge(mayor=mayor, frequency_hz=2.0)
    lifecycle = MayorLifecycleBridge(state_path=Path("data/mayor_state.json"))
    runtime = SimpleNamespace(mayor=mayor, supervision=supervision, mayor_lifecycle=lifecycle)

    daemon = build_daemon_service(runtime)

    assert daemon.supervision is supervision
    assert daemon.mayor is mayor