"""Single SHA-bound normal merge authority for B1-S3B.

The authority is disabled by default.  It accepts only a final revalidation
callback and executes a structured ``gh pr merge --match-head-commit`` array.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .ledger import LedgerError, ShadowLedger
from .schema import MergeReadinessEvaluationB1

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class MergeAuthorityError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CurrentMergeStateB1:
    repository: str
    pull_request_number: int
    current_head_sha: str
    current_base_sha: str
    integration_check_sha: str
    merged: bool = False
    final_merge_sha: str | None = None

    def __post_init__(self) -> None:
        if not REPOSITORY_RE.fullmatch(self.repository) or self.pull_request_number <= 0:
            raise MergeAuthorityError("INVALID_PR_IDENTITY")
        for value in (self.current_head_sha, self.current_base_sha, self.integration_check_sha):
            if not SHA_RE.fullmatch(value):
                raise MergeAuthorityError("INVALID_SHA")
        if self.final_merge_sha is not None and not SHA_RE.fullmatch(self.final_merge_sha):
            raise MergeAuthorityError("INVALID_SHA")


class MergeRunner(Protocol):
    def run(self, args: list[str]) -> str | None: ...


class SubprocessGitHubRunner:
    def __init__(self, *, timeout: float = 30.0):
        self.timeout = timeout

    def run(self, args: list[str]) -> str | None:
        try:
            result = subprocess.run(
                ["gh", *args], capture_output=True, text=True, timeout=self.timeout
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None


class ReviewGovernanceMergeAuthority:
    def __init__(
        self,
        *,
        enabled: bool = False,
        runner: MergeRunner | None = None,
        ledger: ShadowLedger | None = None,
    ):
        self.enabled = enabled
        self.runner = runner or SubprocessGitHubRunner()
        self.ledger = ledger

    def merge(
        self,
        *,
        evaluation: MergeReadinessEvaluationB1,
        current_state: Callable[[], CurrentMergeStateB1],
        actor: str,
        request_base_sha: str,
        reason: str = "",
    ) -> CurrentMergeStateB1:
        if not self.enabled:
            raise MergeAuthorityError("MERGE_AUTHORITY_DISABLED")
        if evaluation.readiness_state != "ready":
            raise MergeAuthorityError("READINESS_NOT_READY")
        state = current_state()
        if (
            state.repository != evaluation.repository
            or state.pull_request_number != evaluation.pull_request_number
        ):
            raise MergeAuthorityError("PR_IDENTITY_CHANGED")
        if state.current_head_sha != evaluation.merge_expected_head_sha:
            raise MergeAuthorityError("HEAD_CHANGED")
        if state.current_base_sha != evaluation.validated_current_base_sha:
            raise MergeAuthorityError("BASE_CHANGED")
        if state.integration_check_sha != evaluation.integration_check_sha:
            raise MergeAuthorityError("INTEGRATION_CHANGED")
        if state.merged:
            return state
        if self.ledger is not None:
            # Validate the append boundary before invoking GitHub. A corrupt
            # or unreadable ledger must not permit an irreversible merge.
            try:
                self.ledger.read()
            except LedgerError as exc:
                raise MergeAuthorityError("LEDGER_APPEND_FAILED") from exc
        args = [
            "pr",
            "merge",
            str(evaluation.pull_request_number),
            "--repo",
            evaluation.repository,
            "--squash",
            "--match-head-commit",
            evaluation.merge_expected_head_sha,
        ]
        if self.runner.run(args) is None:
            raise MergeAuthorityError("MERGE_FAILED")
        confirmed = current_state()
        if (
            confirmed.repository != evaluation.repository
            or confirmed.pull_request_number != evaluation.pull_request_number
            or confirmed.current_head_sha != evaluation.merge_expected_head_sha
        ):
            raise MergeAuthorityError("MERGE_CONFIRMATION_MISMATCH")
        if not confirmed.merged or not confirmed.final_merge_sha:
            raise MergeAuthorityError("MERGE_CONFIRMATION_UNAVAILABLE")
        if self.ledger is not None:
            try:
                self.ledger.append(
                    "merge_completed",
                    f"merge:{evaluation.evaluation_id}",
                    {
                        "repository": evaluation.repository,
                        "pull_request_number": evaluation.pull_request_number,
                        "verdict_id": evaluation.verdict_id,
                        "evaluation_id": evaluation.evaluation_id,
                        "reviewed_head_sha": evaluation.reviewed_head_sha,
                        "review_request_base_sha": request_base_sha,
                        "validated_current_base_sha": evaluation.validated_current_base_sha,
                        "integration_check_sha": evaluation.integration_check_sha,
                        "merge_expected_head_sha": evaluation.merge_expected_head_sha,
                        "final_merge_sha": confirmed.final_merge_sha,
                        "actor": actor,
                        "reason": reason,
                        "timestamp": dt.datetime.now(dt.UTC)
                        .replace(microsecond=0)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                )
            except LedgerError as exc:
                raise MergeAuthorityError("LEDGER_APPEND_FAILED") from exc
        return confirmed


class ExternalMergeObserver:
    def __init__(self, ledger: ShadowLedger):
        self.ledger = ledger

    def observe(
        self,
        *,
        repository: str,
        pull_request_number: int,
        observed_head_sha: str,
        final_merge_sha: str,
        actor: str | None,
        readiness_current: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "repository": repository,
            "pull_request_number": pull_request_number,
            "observed_head_sha": observed_head_sha,
            "final_merge_sha": final_merge_sha,
            "actor": actor,
            "readiness_current": readiness_current,
            "reason": reason,
            "observed_at": dt.datetime.now(dt.UTC)
            .replace(microsecond=0)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        return self.ledger.append(
            "external_merge_observed",
            f"external:{repository}:{pull_request_number}:{final_merge_sha}",
            payload,
        )


class DisabledBreakGlass:
    def invoke(self, **_: Any) -> None:
        raise MergeAuthorityError("BREAK_GLASS_DISABLED")
