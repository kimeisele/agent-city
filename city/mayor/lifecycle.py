from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from city.registry import SVC_CONVERSATION_TRACKER

if TYPE_CHECKING:
    from .kernel import Mayor

logger = logging.getLogger("AGENT_CITY.MAYOR.LIFECYCLE")

# Bounded .bak rotation retained alongside the live state files (Issue #14 Area 1).
STATE_BACKUPS: int = 5


def _backup_paths(path: Path) -> list[Path]:
    """Newest-first backup candidates for `path` (.bak, .bak.1, .bak.2, ...)."""
    backups = [Path(f"{path}.bak")]
    backups.extend(Path(f"{path}.bak.{i}") for i in range(1, STATE_BACKUPS))
    return backups


def _rotate_backups(path: Path) -> None:
    """Best-effort shift of retained backups one slot older, dropping the oldest.

    The current primary file is copied to `.bak` so a corrupt primary can be
    recovered from the most recent valid backup on the next load.
    """
    try:
        for i in range(STATE_BACKUPS - 1, 1, -1):
            older = Path(f"{path}.bak.{i - 1}")
            if older.exists():
                older.replace(Path(f"{path}.bak.{i}"))
        latest = Path(f"{path}.bak")
        if latest.exists():
            latest.replace(Path(f"{path}.bak.1"))
        if path.exists():
            shutil.copy2(path, latest)
    except OSError as exc:
        logger.warning("Mayor state backup rotation for %s failed: %s", path, exc)


def _atomic_write_json(path: Path, data: object) -> None:
    """Persist JSON atomically: temp file in the same dir, fsync, then replace.

    Follows the temp+replace pattern already used by FederationNadi/
    FederationRelay, with backup rotation so a corrupt primary can be
    recovered on the next load.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_backups(path)
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    temp.replace(path)


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
        for candidate in [self.state_path, *_backup_paths(self.state_path)]:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text())
                mayor._heartbeat_count = data.get("heartbeat_count", 0)
                mayor._total_governance_actions = data.get("total_governance_actions", 0)
                mayor._total_operations = data.get("total_operations", 0)
            except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
                continue
            if candidate != self.state_path:
                logger.warning(
                    "Mayor state load failed; recovered from backup %s", candidate
                )
            return
        logger.warning("Mayor state load failed; no valid backup — starting fresh")

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
            _atomic_write_json(self.state_path, state)
        except OSError as exc:
            logger.warning("Mayor state save failed: %s", exc)

        tracker = mayor._registry.get(SVC_CONVERSATION_TRACKER)
        if tracker is None or not hasattr(tracker, "snapshot"):
            return
        try:
            _atomic_write_json(self.tracker_path, tracker.snapshot())
        except Exception as exc:
            logger.warning("ConversationTracker save failed: %s", exc)