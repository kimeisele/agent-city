"""
INTENT EXECUTOR — Action Delegation for HEAL Missions
=======================================================

Maps contract failure names to concrete fix actions.
Successful fixes produce git branches + commits + PRs via subprocess.

Fix strategies:
- ruff_clean: run `ruff check --fix`, re-check. Escalate if still failing.
- no_slop:    Escalate (slop in source code needs human review).
- tests_pass: Escalate (cannot auto-fix test failures).
- unknown:    Escalate.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from config import get_config

logger = logging.getLogger("AGENT_CITY.EXECUTOR")

# Git identity — sourced from config/city.yaml
_exec_cfg = get_config().get("executor", {})
GIT_AUTHOR_NAME: str = _exec_cfg.get("git_author_name", "Mayor Agent")
GIT_AUTHOR_EMAIL: str = _exec_cfg.get("git_author_email", "mayor@agent-city.dev")


@dataclass
class FixResult:
    """Outcome of attempting to fix a contract failure."""

    contract_name: str
    success: bool
    action_taken: str  # "ruff_fix", "escalate"
    files_changed: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class PRResult:
    """Outcome of creating a fix PR."""

    success: bool
    branch: str = ""
    commit_hash: str = ""
    pr_url: str = ""
    message: str = ""


@dataclass
class IntentExecutor:
    """Executes HEAL intents by mapping contract names to fix actions.

    _dry_run: When True, skips all subprocess/git calls (for tests).
    """

    _cwd: Path
    _dry_run: bool = False

    def execute_heal(self, contract_name: str, details: list[str]) -> FixResult:
        """Attempt to fix a failing contract.

        Returns FixResult with success=True if the fix resolved the issue,
        or success=False with action_taken="escalate" if it cannot be auto-fixed.
        """
        if contract_name == "ruff_clean":
            return self._fix_ruff(details)

        # no_slop, tests_pass, unknown — all escalate
        return self._escalate(contract_name, details)

    def _fix_ruff(self, details: list[str]) -> FixResult:
        """Run ruff --fix, then re-check. Escalate if still failing."""
        if self._dry_run:
            return FixResult(
                contract_name="ruff_clean",
                success=True,
                action_taken="ruff_fix",
                files_changed=["(dry_run)"],
                message="dry_run: ruff fix skipped",
            )

        # Step 1: Run ruff --fix
        try:
            subprocess.run(
                [
                    "python", "-m", "ruff", "check",
                    "--fix", "--select", "F821,F811",
                    str(self._cwd),
                ],
                capture_output=True, text=True,
                timeout=_exec_cfg.get("ruff_timeout_s", 60),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return FixResult(
                contract_name="ruff_clean",
                success=False,
                action_taken="escalate",
                message=f"ruff unavailable: {e}",
            )

        # Step 2: Re-check — did the fix work?
        try:
            recheck = subprocess.run(
                [
                    "python", "-m", "ruff", "check",
                    "--select", "F821,F811",
                    str(self._cwd),
                ],
                capture_output=True, text=True,
                timeout=_exec_cfg.get("ruff_timeout_s", 60),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return FixResult(
                contract_name="ruff_clean",
                success=False,
                action_taken="escalate",
                message=f"ruff re-check failed: {e}",
            )

        if recheck.returncode == 0:
            # Step 3: Find which files changed
            changed = self._git_changed_files()
            return FixResult(
                contract_name="ruff_clean",
                success=True,
                action_taken="ruff_fix",
                files_changed=changed,
                message="ruff --fix resolved all F821/F811 violations",
            )

        # Still failing — escalate the remainder
        remaining = recheck.stdout.strip().split("\n") if recheck.stdout.strip() else []
        return FixResult(
            contract_name="ruff_clean",
            success=False,
            action_taken="escalate",
            message=f"ruff --fix ran but {len(remaining)} violations remain",
        )

    def _escalate(self, contract_name: str, details: list[str]) -> FixResult:
        """Cannot auto-fix — log and return escalation."""
        detail_summary = "; ".join(details[:5]) if details else "no details"
        logger.warning(
            "ESCALATE %s: cannot auto-fix (%s)", contract_name, detail_summary,
        )
        return FixResult(
            contract_name=contract_name,
            success=False,
            action_taken="escalate",
            message=f"Cannot auto-fix {contract_name}: {detail_summary}",
        )

    # ── PR Workflow ──────────────────────────────────────────────────

    def create_fix_pr(self, fix: FixResult, heartbeat_count: int = 0) -> PRResult | None:
        """Create a git branch + commit + PR for a successful fix.

        Returns None if fix was not successful or no files changed.
        """
        if not fix.success or not fix.files_changed:
            return None

        branch = f"fix/{fix.contract_name}_{heartbeat_count}"

        if self._dry_run:
            return PRResult(
                success=True,
                branch=branch,
                commit_hash="(dry_run)",
                pr_url="(dry_run)",
                message="dry_run: PR creation skipped",
            )

        commit_msg = f"fix({fix.contract_name}): auto-heal from Mayor KARMA phase"

        try:
            # 1. Create branch
            self._run_git(["checkout", "-b", branch])

            # 2. Stage changes
            self._run_git(["add", "-A"])

            # 3. Check for staged changes
            diff_result = self._run_git(["diff", "--staged", "--quiet"], check=False)
            if diff_result.returncode == 0:
                # No changes staged — abort
                self._run_git(["checkout", "main"])
                self._run_git(["branch", "-D", branch], check=False)
                return PRResult(
                    success=False,
                    branch=branch,
                    message="No changes to commit",
                )

            # 4. Commit
            commit_result = self._run_git([
                "-c", f"user.name={GIT_AUTHOR_NAME}",
                "-c", f"user.email={GIT_AUTHOR_EMAIL}",
                "commit", "-m", commit_msg,
            ])
            # Extract commit hash
            commit_hash = ""
            if commit_result.stdout:
                parts = commit_result.stdout.strip().split()
                for part in parts:
                    if len(part) >= 7 and all(c in "0123456789abcdef" for c in part.strip("[]")):
                        commit_hash = part.strip("[]")
                        break

            # 5. Push
            self._run_git(["push", "-u", "origin", branch])

            # 6. Create PR
            pr_body = (
                f"## Auto-heal: {fix.contract_name}\n\n"
                f"**Action**: {fix.action_taken}\n"
                f"**Files changed**: {', '.join(fix.files_changed)}\n"
                f"**Message**: {fix.message}\n\n"
                f"Created by Mayor Agent during KARMA phase (heartbeat #{heartbeat_count})."
            )
            pr_result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", commit_msg,
                    "--body", pr_body,
                ],
                capture_output=True, text=True,
                timeout=_exec_cfg.get("subprocess_timeout_s", 30),
                cwd=str(self._cwd),
            )
            pr_url = pr_result.stdout.strip() if pr_result.returncode == 0 else ""

            # 7. Return to main
            self._run_git(["checkout", "main"])

            return PRResult(
                success=bool(pr_url),
                branch=branch,
                commit_hash=commit_hash,
                pr_url=pr_url,
                message=commit_msg,
            )

        except Exception as e:
            # Best-effort return to main
            self._run_git(["checkout", "main"], check=False)
            logger.warning("PR creation failed for %s: %s", fix.contract_name, e)
            return PRResult(
                success=False,
                branch=branch,
                message=f"PR creation failed: {e}",
            )

    # ── Git Helpers ──────────────────────────────────────────────────

    def _run_git(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command in _cwd."""
        return subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=_exec_cfg.get("subprocess_timeout_s", 30),
            cwd=str(self._cwd),
            check=check,
        )

    def _git_changed_files(self) -> list[str]:
        """Get list of files with unstaged changes."""
        try:
            result = self._run_git(["diff", "--name-only"], check=False)
            if result.stdout.strip():
                return result.stdout.strip().split("\n")
        except Exception:
            pass
        return []
