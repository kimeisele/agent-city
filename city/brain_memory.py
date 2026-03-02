"""
BRAIN MEMORY — Persistent Bounded FIFO for Brain Thoughts.

Loaded at boot, flushed in MOKSHA. Same persistence pattern as mayor_state.json.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.BRAIN_MEMORY")

_DEFAULT_MAX_ENTRIES = 24  # ~6 hours at current heartbeat rate


class BrainMemory:
    """Bounded persistent memory for brain thoughts.

    Each entry: {thought: dict, heartbeat: int, posted: bool}.
    FIFO eviction when len > max_entries.
    """

    __slots__ = ("_entries", "_max_entries", "_path")

    def __init__(
        self,
        path: Path | None = None,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._entries: list[dict] = []
        self._max_entries = max_entries
        self._path = path or Path("data/brain_memory.json")

    def record(self, thought: object, heartbeat: int, *, posted: bool = False) -> None:
        """Record a thought. FIFO eviction if over capacity."""
        self._entries.append({
            "thought": thought.to_dict(),  # type: ignore[union-attr]
            "heartbeat": heartbeat,
            "posted": posted,
        })
        # FIFO eviction
        while len(self._entries) > self._max_entries:
            self._entries.pop(0)

    def recent(self, n: int = 6) -> list[dict]:
        """Return the N most recent entries (newest last)."""
        return self._entries[-n:]

    def pattern_summary(self) -> str:
        """Human-readable summary of recent thought patterns."""
        if not self._entries:
            return "No brain thoughts recorded yet."
        recent = self.recent(6)
        confidences = [
            e["thought"].get("confidence", 0.0) for e in recent
        ]
        avg = sum(confidences) / len(confidences) if confidences else 0.0
        high = sum(1 for c in confidences if c >= 0.7)
        return (
            f"{high}/{len(recent)} thoughts had high confidence, "
            f"avg {avg:.2f}"
        )

    def flush(self) -> None:
        """Persist to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._entries, indent=2))
            logger.debug("BrainMemory: flushed %d entries", len(self._entries))
        except Exception as e:
            logger.warning("BrainMemory: flush failed: %s", e)

    def load(self) -> None:
        """Load from disk. Silently starts empty if file missing."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            if isinstance(data, list):
                self._entries = data[-self._max_entries :]
                logger.info(
                    "BrainMemory: loaded %d entries from %s",
                    len(self._entries),
                    self._path,
                )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("BrainMemory: load failed: %s", e)
