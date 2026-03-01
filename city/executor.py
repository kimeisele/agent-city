"""
INTENT EXECUTOR — Action Delegation for HEAL Missions
=======================================================

Maps contract failure names to concrete fix actions.
Successful fixes produce git branches + commits + PRs via subprocess.

Fix strategies:
- ruff_clean:   run `ruff check --fix`, re-check. Escalate if still failing.
- audit_clean:  CellularHealer structural CST remedies. Escalate if no remedy matches.
- tests_pass:   Escalate (cannot auto-fix test failures).
- unknown:      Escalate.

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

# Map audit finding keywords to CellularHealer remedy rule_ids.
# Keys are lowercase substrings matched against audit detail text.
_AUDIT_TO_REMEDY: dict[str, str] = {
    "any_type": "any_type_usage",
    ": any": "any_type_usage",
    "hardcoded": "hardcoded_constants",
    "magic number": "hardcoded_constants",
    "subprocess": "subprocess_timeout",
    "f811": "f811_redefinition",
    "redefinition": "f811_redefinition",
    "mahajana": "missing_mahajana",
    "unsafe io": "unsafe_io_write",
    "unsafe_io": "unsafe_io_write",
    "get_instance": "get_instance",
    "null signature": "null_signature",
    "null_signature": "null_signature",
}


def _extract_rule_id(detail: str) -> str | None:
    """Try to map an audit finding detail to a CellularHealer remedy rule_id."""
    detail_lower = detail.lower()
    for keyword, rule_id in _AUDIT_TO_REMEDY.items():
        if keyword in detail_lower:
            return rule_id
    return None


def _extract_file_path(detail: str) -> Path | None:
    """Try to extract a .py file path from an audit detail string."""
    import re
    match = re.search(r'([\w/.]+\.py)', detail)
    if match:
        candidate = Path(match.group(1))
        if candidate.exists():
            return candidate
    return None

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

        if contract_name == "audit_clean":
            return self._fix_audit(details)

        # tests_pass, unknown — escalate
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

    def _fix_audit(self, details: list[str]) -> FixResult:
        """Attempt structural code healing via CellularHealer.

        Matches audit finding details to available CST remedies.
        Falls back to escalation if healer unavailable or no remedies match.
        """
        if self._dry_run:
            try:
                from vibe_core.mahamantra.dharma.kumaras.healing_intent import get_cellular_healer
                healer = get_cellular_healer()
                return FixResult(
                    contract_name="audit_clean",
                    success=True,
                    action_taken="cellular_heal",
                    files_changed=["(dry_run)"],
                    message=f"dry_run: {len(healer.list_remedies())} remedies available",
                )
            except Exception:
                return self._escalate("audit_clean", details)

        try:
            from vibe_core.mahamantra.dharma.kumaras.healing_intent import get_cellular_healer
            healer = get_cellular_healer()
        except Exception as e:
            logger.warning("CellularHealer unavailable: %s", e)
            return self._escalate("audit_clean", details)

        available = set(healer.list_remedies())
        healed_files: list[str] = []

        for detail in details:
            rule_id = _extract_rule_id(detail)
            if rule_id and rule_id in available:
                file_path = _extract_file_path(detail)
                if file_path is not None:
                    try:
                        results = healer.heal_file(
                            file_path, rule_id, dry_run=False,
                        )
                        for r in results:
                            if r.success:
                                healed_files.append(str(file_path))
                    except Exception as e:
                        logger.warning(
                            "Heal %s (%s) failed: %s", file_path, rule_id, e,
                        )

        if healed_files:
            unique = list(set(healed_files))
            return FixResult(
                contract_name="audit_clean",
                success=True,
                action_taken="cellular_heal",
                files_changed=unique,
                message=f"CellularHealer fixed {len(unique)} files",
            )

        # No healable findings — escalate
        return self._escalate("audit_clean", details)

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
