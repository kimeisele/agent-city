from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.mayor_lifecycle import MayorLifecycleBridge
from city.registry import CityServiceRegistry, SVC_CONVERSATION_TRACKER


def test_restore_mayor_heartbeat_count(tmp_path):
    state_path = tmp_path / "mayor_state.json"
    state_path.write_text(json.dumps({"heartbeat_count": 7}))
    mayor = SimpleNamespace(_heartbeat_count=0)

    MayorLifecycleBridge(state_path=state_path).restore_mayor(mayor)

    assert mayor._heartbeat_count == 7


def test_persist_mayor_state_and_tracker(tmp_path):
    tracker = SimpleNamespace(snapshot=lambda: [{"discussion_number": 1}])
    registry = CityServiceRegistry()
    registry.register(SVC_CONVERSATION_TRACKER, tracker)
    mayor = SimpleNamespace(
        _heartbeat_count=3,
        _pokedex=SimpleNamespace(
            list_all=lambda: [{"name": "Alpha"}, {"name": "Beta"}],
            list_by_status=lambda status: [{"name": "Beta"}] if status == "archived" else [],
        ),
        _registry=registry,
    )
    bridge = MayorLifecycleBridge(state_path=tmp_path / "mayor_state.json")
    bridge.ensure_storage_dir()

    bridge.persist_mayor(mayor)

    state = json.loads((tmp_path / "mayor_state.json").read_text())
    assert state["heartbeat_count"] == 3
    assert state["discovered_agents"] == ["Alpha", "Beta"]
    assert state["archived_agents"] == ["Beta"]
    assert json.loads((tmp_path / "conversation_tracker.json").read_text()) == [
        {"discussion_number": 1}
    ]