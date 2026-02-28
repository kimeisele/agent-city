"""
GITHUB ISSUES — Living Cells for Issues
==========================================

Each GitHub Issue gets a MahaCell. Prana decays. Activity feeds energy.
Dead issues auto-close.

Uses `gh` CLI (already available on GitHub Actions, no library needed).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

logger = logging.getLogger("AGENT_CITY.ISSUES")

# Prana constants from MahaCellUnified
GENESIS_PRANA = 13700
METABOLIC_COST = 3


def _gh_run(args: list[str]) -> str | None:
    """Run a gh CLI command. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("gh %s failed: %s", " ".join(args[:3]), result.stderr.strip())
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("gh CLI unavailable or timed out: %s", e)
        return None


@dataclass
class CityIssueManager:
    """GitHub Issues <-> MahaCell bridge.

    Each issue gets a living cell. Prana decays per metabolism cycle.
    Activity on the issue feeds energy. Dead issues get auto-closed.
    """

    _repo: str = ""
    _issue_cells: dict[int, MahaCellUnified] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._repo:
            # Auto-detect from git remote
            out = _gh_run(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
            self._repo = out or ""

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict | None:
        """Create a GitHub Issue and bind a MahaCell to it.

        Returns issue metadata or None on failure.
        """
        args = ["issue", "create", "--title", title, "--body", body]
        if labels:
            for label in labels:
                args.extend(["--label", label])

        url = _gh_run(args)
        if not url:
            return None

        # Extract issue number from URL
        try:
            issue_number = int(url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            logger.warning("Could not parse issue number from: %s", url)
            return None

        # Create living cell from issue title
        cell = MahaCellUnified.from_content(title, register=False)
        self._issue_cells[issue_number] = cell

        logger.info("Created issue #%d with MahaCell (prana=%d)", issue_number, cell.prana)
        return {
            "number": issue_number,
            "url": url,
            "title": title,
            "prana": cell.prana,
            "integrity": cell.membrane_integrity,
        }

    def metabolize_issues(self) -> list[str]:
        """DHARMA phase: prana decay, activity check, auto-close dead issues.

        Returns list of actions taken (e.g. "closed:#42:prana_exhaustion").
        """
        actions: list[str] = []

        # Get open issues
        out = _gh_run([
            "issue", "list", "--state", "open",
            "--json", "number,title,updatedAt,comments",
            "--limit", "100",
        ])
        if not out:
            return actions

        try:
            issues = json.loads(out)
        except json.JSONDecodeError:
            return actions

        for issue in issues:
            number = issue["number"]
            title = issue["title"]

            # Get or create cell for this issue
            if number not in self._issue_cells:
                self._issue_cells[number] = MahaCellUnified.from_content(title, register=False)

            cell = self._issue_cells[number]

            # Activity = number of recent comments (proxy for engagement)
            comments = issue.get("comments", [])
            energy = len(comments) * 5 if isinstance(comments, list) else 0

            cell.metabolize(energy)

            if not cell.is_alive:
                # Auto-close dead issues
                close_result = _gh_run([
                    "issue", "close", str(number),
                    "--comment", "Auto-closed: issue cell prana exhausted (no activity).",
                ])
                if close_result is not None:
                    actions.append(f"closed:#{number}:prana_exhaustion")
                    logger.info("Auto-closed issue #%d (prana exhausted)", number)
                del self._issue_cells[number]

        return actions

    def get_issue_health(self, issue_number: int) -> dict | None:
        """Get health metrics for an issue's cell."""
        cell = self._issue_cells.get(issue_number)
        if cell is None:
            return None
        return {
            "issue_number": issue_number,
            "prana": cell.prana,
            "integrity": cell.membrane_integrity,
            "is_alive": cell.is_alive,
            "age": cell.age,
        }

    def stats(self) -> dict:
        """Issue manager statistics."""
        alive = sum(1 for c in self._issue_cells.values() if c.is_alive)
        return {
            "tracked_issues": len(self._issue_cells),
            "alive": alive,
            "dead": len(self._issue_cells) - alive,
            "repo": self._repo,
        }
