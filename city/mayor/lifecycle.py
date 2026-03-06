from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from city.registry import SVC_CONVERSATION_TRACKER

if TYPE_CHECKING:
    from .kernel import Mayor

logger = logging.getLogger("AGENT_CITY.MAYOR.LIFECYCLE")


@dataclass(frozen=True)
class MayorLifecycleBridge:
    """Owns Mayor restart-state persistence at the runtime seam."""

    state_path: Path

    @property
    def tracker_path(self) -> Path:
        return self.state_path.parent / "conversation_tracker.json"

    def ensure_storage_dir(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def restore_mayor(self, mayor: Mayor) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
            mayor._heartbeat_count = data.get("heartbeat_count", 0)
            mayor._total_governance_actions = data.get("total_governance_actions", 0)
            mayor._total_operations = data.get("total_operations", 0)
        except (json.JSONDecodeError, KeyError, OSError, TypeError):
            return

    def restore_conversation_tracker(self, tracker: object) -> None:
        if not self.tracker_path.exists() or not hasattr(tracker, "restore"):
            return
        try:
            data = json.loads(self.tracker_path.read_text())
            if isinstance(data, list):
                tracker.restore(data)
        except (ValueError, OSError) as exc:
            logger.warning("ConversationTracker load failed: %s", exc)

    def persist_mayor(self, mayor: Mayor) -> None:
        state = {
            "heartbeat_count": mayor._heartbeat_count,
            "last_heartbeat": time.time(),
            "discovered_agents": [a["name"] for a in mayor._pokedex.list_all()],
            "archived_agents": [a["name"] for a in mayor._pokedex.list_by_status("archived")],
            "total_governance_actions": getattr(mayor, "_total_governance_actions", 0),
            "total_operations": getattr(mayor, "_total_operations", 0),
        }
        try:
            self.state_path.write_text(json.dumps(state, indent=2))
        except OSError as exc:
            logger.warning("Mayor state save failed: %s", exc)

        tracker = mayor._registry.get(SVC_CONVERSATION_TRACKER)
        if tracker is None or not hasattr(tracker, "snapshot"):
            return
        try:
            self.tracker_path.write_text(json.dumps(tracker.snapshot(), indent=2))
        except Exception as exc:
            logger.warning("ConversationTracker save failed: %s", exc)