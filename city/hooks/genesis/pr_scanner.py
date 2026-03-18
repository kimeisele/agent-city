"""
GENESIS Hook: PR Scanner — Open PRs to NADI Review Requests.

Scans for open pull requests via GitHub API. Detects new PRs,
extracts metadata (author, files, core-file impact), and emits
OP_PR_REVIEW_REQUEST via Federation NADI for Steward evaluation.

Priority 56: after issue scanner (55), same band.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import TYPE_CHECKING

from city.federation_nadi import RAJAS
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.PR_SCANNER")

# Track processed PR numbers to avoid re-processing
_processed_prs: set[int] = set()

# Core files that require council vote even if Steward approves
CORE_FILES = frozenset({
    "city/services.py",
    "city/immune.py",
    "city/immigration.py",
    "city/governance_layer.py",
    "city/civic_protocol.py",
})

REPO = "kimeisele/agent-city"


class PRScannerHook(BasePhaseHook):
    """Scan GitHub for open PRs → emit NADI review requests to Steward."""

    @property
    def name(self) -> str:
        return "pr_scanner"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 56

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation_nadi is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        try:
            prs = self._fetch_open_prs()
        except Exception as e:
            logger.debug("PR scan failed (non-fatal): %s", e)
            return

        for pr in prs:
            number = pr.get("number", 0)
            if number in _processed_prs:
                continue

            _processed_prs.add(number)

            author = pr.get("author", {}).get("login", "unknown")
            title = pr.get("title", "")
            body = pr.get("body", "") or ""
            files_changed = [f.get("path", "") for f in pr.get("files", [])]

            # Check if author is a citizen
            is_citizen = ctx.pokedex.get(author) is not None

            # Check if PR touches core files
            core_files_touched = CORE_FILES & set(files_changed)

            # Emit NADI message for Steward review
            ctx.federation_nadi.emit(
                source="genesis",
                operation="pr_review_request",
                payload={
                    "repo": REPO,
                    "pr_number": number,
                    "author": author,
                    "title": title,
                    "body": body[:2000],
                    "files_changed": files_changed,
                    "is_citizen": is_citizen,
                    "touches_core": bool(core_files_touched),
                    "core_files": sorted(core_files_touched),
                },
                priority=RAJAS,
            )

            operations.append(f"pr_scanner:review_request:#{number}:{author}")
            logger.info(
                "PR_SCANNER: Emitted review request for PR #%d by %s (core=%s)",
                number, author, bool(core_files_touched),
            )

    def _fetch_open_prs(self) -> list[dict]:
        """Fetch open PRs via GitHub API with file info."""
        token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
        if not token:
            return []

        url = (
            f"https://api.github.com/repos/{REPO}/pulls"
            "?state=open&per_page=30&sort=created&direction=desc"
        )
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                prs_raw = json.loads(resp.read())
        except Exception:
            return []

        # Enrich each PR with file list
        result = []
        for pr_raw in prs_raw:
            pr = {
                "number": pr_raw["number"],
                "author": {"login": pr_raw.get("user", {}).get("login", "unknown")},
                "title": pr_raw.get("title", ""),
                "body": pr_raw.get("body", ""),
                "files": [],
            }

            # Fetch files for this PR
            files = self._fetch_pr_files(token, pr_raw["number"])
            pr["files"] = files
            result.append(pr)

        return result

    def _fetch_pr_files(self, token: str, pr_number: int) -> list[dict]:
        """Fetch the list of files changed in a PR."""
        url = f"https://api.github.com/repos/{REPO}/pulls/{pr_number}/files"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                files_raw = json.loads(resp.read())
            return [{"path": f.get("filename", "")} for f in files_raw]
        except Exception:
            return []
