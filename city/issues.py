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
from enum import Enum

from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

from config import get_config

logger = logging.getLogger("AGENT_CITY.ISSUES")

# Low prana threshold — sourced from config/city.yaml
_issues_cfg = get_config().get("issues", {})
LOW_PRANA_THRESHOLD: int = _issues_cfg.get("low_prana_threshold", 1000)

# Ashrama lifecycle — graceful fallback if steward-protocol module unavailable
try:
    from vibe_core.plugins.vedic_governance.ashrama import Ashrama

    _ASHRAMA_AVAILABLE = True
except Exception:
    _ASHRAMA_AVAILABLE = False


def _classify_ashrama(cell: "MahaCellUnified") -> str:
    """Map cell state to Ashrama lifecycle stage.

    BRAHMACHARI: Young cell (low cycle count) — learning, gets energy bonus.
    GRIHASTHA:   Active cell, healthy prana — normal metabolism.
    VANAPRASTHA: Active but low prana — winding down, generates intents.
    SANNYASA:    Dead cell — auto-close.

    Returns Ashrama value string or "" if unavailable.
    """
    if not _ASHRAMA_AVAILABLE:
        return ""

    if not cell.is_alive:
        return Ashrama.SANNYASA.value

    cycle = getattr(cell, "age", 0)
    if cycle < 10:
        return Ashrama.BRAHMACHARI.value

    if cell.prana > LOW_PRANA_THRESHOLD:
        return Ashrama.GRIHASTHA.value

    return Ashrama.VANAPRASTHA.value


class IssueType(str, Enum):
    """Issue lifecycle types.

    EPHEMERAL: Fire-and-forget. Auto-closes when prana hits 0.
    ITERATIVE: Multi-sprint work. Never auto-closes. Signals "needs attention" on low prana.
    CONTRACT:  Quality contract. Never auto-closes. Signals "audit needed" on low prana.
    """

    EPHEMERAL = "ephemeral"
    ITERATIVE = "iterative"
    CONTRACT = "contract"


def _gh_run(args: list[str]) -> str | None:
    """Run a gh CLI command. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=get_config().get("issues", {}).get("gh_timeout_s", 30),
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
    _issue_types: dict[int, IssueType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._repo:
            # Auto-detect from git remote
            out = _gh_run(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
            self._repo = out or ""

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
        issue_type: IssueType = IssueType.EPHEMERAL,
    ) -> dict | None:
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
        self._issue_types[issue_number] = issue_type

        logger.info(
            "Created issue #%d (%s) with MahaCell (prana=%d)",
            issue_number,
            issue_type.value,
            cell.prana,
        )
        return {
            "number": issue_number,
            "url": url,
            "title": title,
            "prana": cell.prana,
            "integrity": cell.membrane_integrity,
            "issue_type": issue_type.value,
        }

    def set_issue_type(self, issue_number: int, issue_type: IssueType) -> None:
        """Set the lifecycle type for a tracked issue."""
        self._issue_types[issue_number] = issue_type

    def get_issue_type(self, issue_number: int) -> IssueType:
        """Get the lifecycle type for an issue (default: EPHEMERAL)."""
        return self._issue_types.get(issue_number, IssueType.EPHEMERAL)

    def metabolize_issues(self) -> list[str]:
        """DHARMA phase: prana decay, activity check, Ashrama lifecycle.

        Ashrama stages modify behavior:
        - BRAHMACHARI: energy += 2 (grace period for young issues)
        - GRIHASTHA:   normal metabolism
        - VANAPRASTHA: generate intent_needed (winding down)
        - SANNYASA:    auto-close (dead cell)

        Returns list of actions taken:
        - "closed:#42:prana_exhaustion" — dead issue auto-closed
        - "intent_needed:#42:low_prana" — issue needs attention
        - "contract_check:#42:audit_needed" — contract issue needs audit
        - "ashrama:#42:brahmachari" — lifecycle stage logged
        """
        actions: list[str] = []

        # Get open issues
        out = _gh_run(
            [
                "issue",
                "list",
                "--state",
                "open",
                "--json",
                "number,title,updatedAt,comments",
                "--limit",
                str(get_config().get("issues", {}).get("list_limit", 100)),
            ]
        )
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
            issue_type = self.get_issue_type(number)

            # Activity = number of recent comments (proxy for engagement)
            comments = issue.get("comments", [])
            _mult = get_config().get("issues", {}).get("comment_energy_multiplier", 5)
            energy = len(comments) * _mult if isinstance(comments, list) else 0

            # Ashrama lifecycle modulation
            ashrama = _classify_ashrama(cell)
            if ashrama == "brahmachari":
                energy += 2  # Grace period — bonus energy for young issues
                actions.append(f"ashrama:#{number}:brahmachari")

            # All types decay prana (signals urgency)
            cell.metabolize(energy)

            # Ashrama-driven lifecycle (overrides type-only logic when available)
            if ashrama == "sannyasa":
                # SANNYASA: dead cell → auto-close regardless of type
                if issue_type == IssueType.EPHEMERAL:
                    close_result = _gh_run(
                        [
                            "issue",
                            "close",
                            str(number),
                            "--comment",
                            "Auto-closed: issue cell prana exhausted (no activity).",
                        ]
                    )
                    if close_result is not None:
                        actions.append(f"closed:#{number}:prana_exhaustion")
                        logger.info("Auto-closed issue #%d (prana exhausted)", number)
                    del self._issue_cells[number]
                    self._issue_types.pop(number, None)
                elif issue_type == IssueType.ITERATIVE:
                    actions.append(f"intent_needed:#{number}:low_prana")
                    logger.info("Iterative issue #%d low prana (%d)", number, cell.prana)
                elif issue_type == IssueType.CONTRACT:
                    actions.append(f"contract_check:#{number}:audit_needed")
                    logger.info("Contract issue #%d needs audit (prana=%d)", number, cell.prana)

            elif ashrama == "vanaprastha":
                # VANAPRASTHA: winding down → signal intent needed
                if issue_type == IssueType.ITERATIVE:
                    actions.append(f"intent_needed:#{number}:low_prana")
                    logger.info("Iterative issue #%d low prana (%d)", number, cell.prana)
                elif issue_type == IssueType.CONTRACT:
                    actions.append(f"contract_check:#{number}:audit_needed")
                    logger.info("Contract issue #%d needs audit (prana=%d)", number, cell.prana)

            else:
                # GRIHASTHA or no Ashrama: original type-based logic
                if issue_type == IssueType.EPHEMERAL:
                    if not cell.is_alive:
                        close_result = _gh_run(
                            [
                                "issue",
                                "close",
                                str(number),
                                "--comment",
                                "Auto-closed: issue cell prana exhausted (no activity).",
                            ]
                        )
                        if close_result is not None:
                            actions.append(f"closed:#{number}:prana_exhaustion")
                            logger.info("Auto-closed issue #%d (prana exhausted)", number)
                        del self._issue_cells[number]
                        self._issue_types.pop(number, None)

                elif issue_type == IssueType.ITERATIVE:
                    if cell.prana < LOW_PRANA_THRESHOLD:
                        actions.append(f"intent_needed:#{number}:low_prana")
                        logger.info("Iterative issue #%d low prana (%d)", number, cell.prana)

                elif issue_type == IssueType.CONTRACT:
                    if cell.prana < LOW_PRANA_THRESHOLD:
                        actions.append(f"contract_check:#{number}:audit_needed")
                        logger.info("Contract issue #%d needs audit (prana=%d)", number, cell.prana)

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
