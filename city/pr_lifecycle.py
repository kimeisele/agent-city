"""
PR LIFECYCLE MANAGER — Track, Check, Auto-Merge, Close Stale
==============================================================

PRs created by the executor are tracked. MOKSHA polls `gh pr checks`.
Passing PRs are auto-merged. Stale PRs are closed.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from config import get_config

logger = logging.getLogger("AGENT_CITY.PR_LIFECYCLE")

_pr_cfg = get_config().get("pr_lifecycle", {})
STALE_HEARTBEATS: int = _pr_cfg.get("stale_heartbeats", 40)
AUTO_MERGE: bool = _pr_cfg.get("auto_merge", True)


@dataclass
class PRRecord:
    """A tracked PR created by the city."""

    pr_url: str
    branch: str
    contract_name: str
    created_at_heartbeat: int
    status: str = "open"  # "open", "merged", "closed", "stale"
    checks_passed: bool = False
    last_checked_heartbeat: int = 0

    def to_dict(self) -> dict:
        return {
            "pr_url": self.pr_url,
            "branch": self.branch,
            "contract_name": self.contract_name,
            "created_at_heartbeat": self.created_at_heartbeat,
            "status": self.status,
            "checks_passed": self.checks_passed,
            "last_checked_heartbeat": self.last_checked_heartbeat,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PRRecord:
        return cls(
            pr_url=d["pr_url"],
            branch=d["branch"],
            contract_name=d["contract_name"],
            created_at_heartbeat=d["created_at_heartbeat"],
            status=d.get("status", "open"),
            checks_passed=d.get("checks_passed", False),
            last_checked_heartbeat=d.get("last_checked_heartbeat", 0),
        )


def _gh_run(args: list[str]) -> str | None:
    """Run a gh CLI command. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("gh %s failed: %s", " ".join(args[:3]), result.stderr.strip())
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("gh CLI unavailable or timed out: %s", e)
        return None


@dataclass
class PRLifecycleManager:
    """Tracks PRs, polls CI, auto-merges, closes stale."""

    _records: dict[str, PRRecord] = field(default_factory=dict)
    _state_path: Path | None = None
    _dry_run: bool = False

    def __post_init__(self) -> None:
        if self._state_path is not None and self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                for url, rd in data.items():
                    self._records[url] = PRRecord.from_dict(rd)
                logger.info("PR lifecycle: loaded %d records", len(self._records))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("PR lifecycle state load failed: %s", e)

    def _save(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps({url: r.to_dict() for url, r in self._records.items()}, indent=2)
        )

    def track(self, pr_url: str, branch: str, contract_name: str, heartbeat: int) -> PRRecord:
        """Track a new PR."""
        record = PRRecord(
            pr_url=pr_url,
            branch=branch,
            contract_name=contract_name,
            created_at_heartbeat=heartbeat,
        )
        self._records[pr_url] = record
        self._save()
        logger.info("Tracking PR: %s (%s)", pr_url, contract_name)
        return record

    def check_all(self, current_heartbeat: int) -> list[dict]:
        """Check all open PRs. Returns list of status changes."""
        changes: list[dict] = []

        for url, record in list(self._records.items()):
            if record.status != "open":
                continue

            # Check for staleness
            age = current_heartbeat - record.created_at_heartbeat
            if age > STALE_HEARTBEATS:
                record.status = "stale"
                if not self._dry_run:
                    self._close_stale_pr(url)
                changes.append({"pr_url": url, "action": "closed_stale", "age": age})
                logger.info("Closed stale PR: %s (age=%d heartbeats)", url, age)
                continue

            # Poll CI checks
            if self._dry_run:
                continue

            checks_status = self._check_pr_status(url)
            record.last_checked_heartbeat = current_heartbeat

            if checks_status == "pass":
                record.checks_passed = True
                if AUTO_MERGE:
                    merged = self._auto_merge(url)
                    if merged:
                        record.status = "merged"
                        changes.append({"pr_url": url, "action": "merged"})
                        logger.info("Auto-merged PR: %s", url)
                    else:
                        changes.append({"pr_url": url, "action": "checks_passed"})
                else:
                    changes.append({"pr_url": url, "action": "checks_passed"})

            elif checks_status == "fail":
                changes.append({"pr_url": url, "action": "checks_failed"})
                logger.warning("PR checks failed: %s", url)

        self._save()
        return changes

    def _check_pr_status(self, pr_url: str) -> str:
        """Poll gh pr checks. Returns 'pass', 'fail', or 'pending'."""
        # Extract PR number from URL
        pr_ref = pr_url.rstrip("/").split("/")[-1]
        out = _gh_run(["pr", "checks", pr_ref, "--json", "state"])
        if out is None:
            return "pending"
        try:
            checks = json.loads(out)
            states = [c.get("state", "") for c in checks]
            if all(s == "SUCCESS" for s in states) and states:
                return "pass"
            if any(s == "FAILURE" for s in states):
                return "fail"
        except (json.JSONDecodeError, TypeError):
            pass
        return "pending"

    def _auto_merge(self, pr_url: str) -> bool:
        """Auto-merge a PR via gh."""
        pr_ref = pr_url.rstrip("/").split("/")[-1]
        result = _gh_run(["pr", "merge", pr_ref, "--merge", "--auto"])
        return result is not None

    def _close_stale_pr(self, pr_url: str) -> None:
        """Close a stale PR with comment."""
        pr_ref = pr_url.rstrip("/").split("/")[-1]
        _gh_run(
            [
                "pr",
                "close",
                pr_ref,
                "--comment",
                f"Auto-closed: PR stale after {STALE_HEARTBEATS} heartbeats with no merge.",
            ]
        )

    def stats(self) -> dict:
        """PR lifecycle stats for reflection."""
        by_status: dict[str, int] = {}
        for r in self._records.values():
            by_status[r.status] = by_status.get(r.status, 0) + 1
        return {
            "total_tracked": len(self._records),
            "by_status": by_status,
        }
