"""
TODO SCANNER — Extract actionable TODOs from codebase for Brain consumption.

10D: TODO/FIXME/HACK comments become Brain-readable signals.
Deterministic scan — no AI. Pure grep + digest.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.TODO_SCANNER")

_TODO_PATTERN = re.compile(
    r"#\s*(TODO|FIXME|HACK|XXX)\s*:?\s*(.+)",
    re.IGNORECASE,
)

# Directories to skip
_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".benchmarks", ".vibe"}


@dataclass(frozen=True)
class TodoItem:
    """A single TODO/FIXME/HACK extracted from source code."""

    tag: str           # TODO, FIXME, HACK, XXX
    text: str          # The comment text
    file: str          # Relative file path
    line: int          # Line number
    priority: int      # 0=low (TODO), 1=medium (FIXME/HACK), 2=high (XXX)

    def render(self) -> str:
        return f"[{self.tag}] {self.file}:{self.line} — {self.text}"


_TAG_PRIORITY = {
    "TODO": 0,
    "FIXME": 1,
    "HACK": 1,
    "XXX": 2,
}


def scan_todos(root: Path, extensions: tuple[str, ...] = (".py",)) -> list[TodoItem]:
    """Scan source files for TODO/FIXME/HACK comments.

    Returns sorted list: highest priority first, then by file path.
    """
    items: list[TodoItem] = []

    for ext in extensions:
        for path in root.rglob(f"*{ext}"):
            # Skip ignored directories
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            # Skip test files (they may have TODOs that are test-specific)
            if "test" in path.name and path.name != "conftest.py":
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for i, line in enumerate(text.split("\n"), start=1):
                match = _TODO_PATTERN.search(line)
                if match:
                    tag = match.group(1).upper()
                    comment = match.group(2).strip()
                    if len(comment) < 3:
                        continue  # Skip empty TODOs
                    rel_path = str(path.relative_to(root))
                    items.append(TodoItem(
                        tag=tag,
                        text=comment[:120],
                        file=rel_path,
                        line=i,
                        priority=_TAG_PRIORITY.get(tag, 0),
                    ))

    # Sort: highest priority first, then by file
    items.sort(key=lambda t: (-t.priority, t.file, t.line))
    return items


def render_todo_digest(items: list[TodoItem]) -> str:
    """Render TODO items as Brain-readable digest block."""
    if not items:
        return "[TODO SCAN] 0 items — codebase is clean"

    high = sum(1 for t in items if t.priority >= 2)
    medium = sum(1 for t in items if t.priority == 1)
    low = sum(1 for t in items if t.priority == 0)

    parts = [f"[TODO SCAN] {len(items)} items | {high} high | {medium} medium | {low} low"]

    for item in items[:20]:  # Cap at 20 to avoid token bloat
        parts.append(f"  {item.render()}")

    if len(items) > 20:
        parts.append(f"  ... and {len(items) - 20} more")

    return "\n".join(parts)
