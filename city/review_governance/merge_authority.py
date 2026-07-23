"""Disabled-by-default, SHA-bound merge authority and audit reconciliation."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

from .ledger import LedgerError, ShadowLedger
from .schema import MergeReadinessEvaluationB1

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ACTOR_RE = re.compile(r"^[A-Za-z0-9_.@:/-]{1,256}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class MergeAuthorityError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _validate_identity(repository: str, pull_request_number: int) -> None:
    if not REPOSITORY_RE.fullmatch(repository) or (
        isinstance(pull_request_number, bool)
        or not isinstance(pull_request_number, int)
        or pull_request_number <= 0
    ):
        raise MergeAuthorityError("INVALID_PR_IDENTITY")


def _validate_sha(value: str) -> None:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise MergeAuthorityError("INVALID_SHA")


@dataclass(frozen=True)
class FinalMergeSnapshotB1:
    repository: str
    pull_request_number: int
    current_head_sha: str
    current_base_sha: str
    current_integration_check_sha: str
    pr_state: str
    mergeability_state: str
    head_evidence_state: str
    head_evidence_identity: str
    integration_evidence_state: str
    integration_evidence_identity: str
    council_state: str
    latest_readiness_evaluation_id: str | None
    readiness_invalidated: bool
    ledger_head_identity: str | None
    merged: bool = False
    final_merge_sha: str | None = None
    observed_at: str = ""

    def __post_init__(self) -> None:
        _validate_identity(self.repository, self.pull_request_number)
        for value in (
            self.current_head_sha,
            self.current_base_sha,
            self.current_integration_check_sha,
        ):
            _validate_sha(value)
        if self.final_merge_sha is not None:
            _validate_sha(self.final_merge_sha)
        if self.merged != (self.final_merge_sha is not None):
            raise MergeAuthorityError("INCONSISTENT_MERGE_STATE")
        if self.pr_state not in {"open", "closed"}:
            raise MergeAuthorityError("INVALID_PR_STATE")
        if self.mergeability_state not in {"mergeable", "conflicting", "unknown"}:
            raise MergeAuthorityError("INVALID_MERGEABILITY")
        if self.head_evidence_state not in {
            "verified",
            "unavailable",
            "failed",
            "stale",
            "ambiguous",
        }:
            raise MergeAuthorityError("INVALID_EVIDENCE_STATE")
        if self.integration_evidence_state not in {
            "verified",
            "unavailable",
            "failed",
            "stale",
            "ambiguous",
        }:
            raise MergeAuthorityError("INVALID_EVIDENCE_STATE")
        if not self.head_evidence_identity or not self.integration_evidence_identity:
            raise MergeAuthorityError("INVALID_EVIDENCE_IDENTITY")
        if self.council_state not in {"not_required", "approved", "pending", "rejected", "unknown"}:
            raise MergeAuthorityError("INVALID_COUNCIL_STATE")
        if not isinstance(self.readiness_invalidated, bool):
            raise MergeAuthorityError("INVALID_READINESS_STATE")
        if not TIME_RE.fullmatch(self.observed_at):
            raise MergeAuthorityError("INVALID_TIMESTAMP")


# Compatibility name for callers that used the pre-R1 state object.
CurrentMergeStateB1 = FinalMergeSnapshotB1


class MergeRunner(Protocol):
    def run(self, args: list[str]) -> str | None: ...


class FinalMergeStateResolver(Protocol):
    """Production boundary for a fresh GitHub/evidence/ledger observation."""

    def resolve(self) -> FinalMergeSnapshotB1: ...


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


def _timestamp() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    def _validate_final_state(
        self,
        evaluation: MergeReadinessEvaluationB1,
        state: FinalMergeSnapshotB1,
        *,
        allow_merged_confirmation: bool = False,
    ) -> None:
        if (
            state.repository != evaluation.repository
            or state.pull_request_number != evaluation.pull_request_number
        ):
            raise MergeAuthorityError("PR_IDENTITY_CHANGED")
        if not (state.pr_state == "open" and state.mergeability_state == "mergeable") and not (
            allow_merged_confirmation and state.merged and state.pr_state == "closed"
        ):
            raise MergeAuthorityError("PR_NOT_MERGEABLE")
        if state.current_head_sha != evaluation.merge_expected_head_sha:
            raise MergeAuthorityError("HEAD_CHANGED")
        if state.current_base_sha != evaluation.validated_current_base_sha:
            raise MergeAuthorityError("BASE_CHANGED")
        if state.current_integration_check_sha != evaluation.integration_check_sha:
            raise MergeAuthorityError("INTEGRATION_CHANGED")
        if (
            state.head_evidence_state != "verified"
            or state.integration_evidence_state != "verified"
        ):
            raise MergeAuthorityError("EVIDENCE_NOT_VERIFIED")
        if evaluation.core_gate_state == "core_approved" and state.council_state != "approved":
            raise MergeAuthorityError("COUNCIL_REQUIRED")
        if evaluation.core_gate_state == "non_core" and state.council_state != "not_required":
            raise MergeAuthorityError("COUNCIL_STATE_CHANGED")
        if state.latest_readiness_evaluation_id != evaluation.evaluation_id:
            raise MergeAuthorityError("READINESS_SUPERSEDED")
        if state.readiness_invalidated:
            raise MergeAuthorityError("READINESS_INVALIDATED")
        if self.ledger is None:
            raise MergeAuthorityError("LEDGER_REQUIRED")
        latest, invalidated, ledger_head = self.ledger.readiness_lineage(
            repository=evaluation.repository,
            pull_request_number=evaluation.pull_request_number,
            reviewed_head_sha=evaluation.reviewed_head_sha,
            evaluation_id=evaluation.evaluation_id,
        )
        if (
            latest != evaluation.evaluation_id
            or invalidated
            or ledger_head != state.ledger_head_identity
        ):
            raise MergeAuthorityError("READINESS_LINEAGE_INVALID")

    def merge(
        self,
        *,
        evaluation: MergeReadinessEvaluationB1,
        final_resolver: FinalMergeStateResolver,
        actor: str,
        request_base_sha: str,
        reason: str = "",
    ) -> FinalMergeSnapshotB1:
        if not self.enabled:
            raise MergeAuthorityError("MERGE_AUTHORITY_DISABLED")
        if not isinstance(actor, str) or not ACTOR_RE.fullmatch(actor):
            raise MergeAuthorityError("INVALID_ACTOR")
        if not isinstance(reason, str) or len(reason) > 2000:
            raise MergeAuthorityError("INVALID_REASON")
        _validate_sha(request_base_sha)
        if evaluation.readiness_state != "ready":
            raise MergeAuthorityError("READINESS_NOT_READY")
        if self.ledger is None:
            raise MergeAuthorityError("LEDGER_REQUIRED")
        state = final_resolver.resolve()
        if not isinstance(state, FinalMergeSnapshotB1):
            raise MergeAuthorityError("FINAL_RESOLVER_INVALID")
        self._validate_final_state(evaluation, state)
        attempt_id = f"merge-attempt:{evaluation.evaluation_id}"
        completion_id = f"merge:{evaluation.evaluation_id}"
        completion = self.ledger.find_event(completion_id)
        if completion is not None:
            if not state.merged or state.final_merge_sha != completion["payload"].get(
                "final_merge_sha"
            ):
                raise MergeAuthorityError("MERGE_CONFIRMATION_MISMATCH")
            return state
        reservation = self.ledger.find_event(attempt_id)
        if reservation is None:
            try:
                self.ledger.append(
                    "merge_attempt_reserved",
                    attempt_id,
                    {
                        "attempt_id": attempt_id,
                        "repository": evaluation.repository,
                        "pull_request_number": evaluation.pull_request_number,
                        "evaluation_id": evaluation.evaluation_id,
                        "verdict_id": evaluation.verdict_id,
                        "reviewed_head_sha": evaluation.reviewed_head_sha,
                        "validated_current_base_sha": evaluation.validated_current_base_sha,
                        "integration_check_sha": evaluation.integration_check_sha,
                        "merge_expected_head_sha": evaluation.merge_expected_head_sha,
                        "actor": actor,
                        "reason": reason,
                        "timestamp": _timestamp(),
                        "state": "reserved",
                    },
                )
            except LedgerError as exc:
                raise MergeAuthorityError("LEDGER_RESERVATION_FAILED") from exc
        elif (
            reservation["payload"].get("merge_expected_head_sha")
            != evaluation.merge_expected_head_sha
        ):
            raise MergeAuthorityError("MERGE_ATTEMPT_CONFLICT")
        # Re-resolve after reservation so state changes during the append
        # cannot reach GitHub without a final predicate check.
        state = final_resolver.resolve()
        self._validate_final_state(evaluation, state)
        if state.merged:
            return self.reconcile(
                evaluation=evaluation,
                final_resolver=final_resolver,
                request_base_sha=request_base_sha,
                actor=actor,
                reason=reason,
            )
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
        confirmed = final_resolver.resolve()
        self._validate_final_state(evaluation, confirmed, allow_merged_confirmation=True)
        if not confirmed.merged or not confirmed.final_merge_sha:
            raise MergeAuthorityError("MERGE_CONFIRMATION_UNAVAILABLE")
        try:
            self.ledger.append(
                "merge_completed",
                completion_id,
                {
                    "attempt_id": attempt_id,
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
                    "timestamp": _timestamp(),
                },
            )
        except LedgerError as exc:
            raise MergeAuthorityError("MERGE_SUCCEEDED_AUDIT_PENDING") from exc
        return confirmed

    def reconcile(
        self,
        *,
        evaluation: MergeReadinessEvaluationB1,
        final_resolver: FinalMergeStateResolver,
        request_base_sha: str,
        actor: str,
        reason: str = "",
    ) -> FinalMergeSnapshotB1:
        if self.ledger is None:
            raise MergeAuthorityError("LEDGER_REQUIRED")
        attempt_id = f"merge-attempt:{evaluation.evaluation_id}"
        if self.ledger.find_event(attempt_id) is None:
            raise MergeAuthorityError("NO_MERGE_RESERVATION")
        state = final_resolver.resolve()
        if not state.merged or not state.final_merge_sha:
            raise MergeAuthorityError("MERGE_NOT_CONFIRMED")
        if (
            state.repository != evaluation.repository
            or state.pull_request_number != evaluation.pull_request_number
            or state.current_head_sha != evaluation.merge_expected_head_sha
            or state.current_base_sha != evaluation.validated_current_base_sha
            or state.current_integration_check_sha != evaluation.integration_check_sha
        ):
            raise MergeAuthorityError("MERGE_CONFIRMATION_MISMATCH")
        _validate_sha(state.final_merge_sha)
        existing = self.ledger.find_event(f"merge:{evaluation.evaluation_id}")
        if existing is not None:
            if existing["payload"].get("final_merge_sha") != state.final_merge_sha:
                raise MergeAuthorityError("MERGE_CONFIRMATION_MISMATCH")
            return state
        try:
            self.ledger.append(
                "merge_completed",
                f"merge:{evaluation.evaluation_id}",
                {
                    "attempt_id": attempt_id,
                    "repository": evaluation.repository,
                    "pull_request_number": evaluation.pull_request_number,
                    "verdict_id": evaluation.verdict_id,
                    "evaluation_id": evaluation.evaluation_id,
                    "reviewed_head_sha": evaluation.reviewed_head_sha,
                    "review_request_base_sha": request_base_sha,
                    "validated_current_base_sha": evaluation.validated_current_base_sha,
                    "integration_check_sha": evaluation.integration_check_sha,
                    "merge_expected_head_sha": evaluation.merge_expected_head_sha,
                    "final_merge_sha": state.final_merge_sha,
                    "actor": actor,
                    "reason": reason,
                    "timestamp": _timestamp(),
                },
            )
        except LedgerError as exc:
            raise MergeAuthorityError("MERGE_SUCCEEDED_AUDIT_PENDING") from exc
        return state


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
        _validate_identity(repository, pull_request_number)
        _validate_sha(observed_head_sha)
        _validate_sha(final_merge_sha)
        if actor is not None and not ACTOR_RE.fullmatch(actor):
            raise MergeAuthorityError("INVALID_ACTOR")
        if not isinstance(readiness_current, bool):
            raise MergeAuthorityError("INVALID_READINESS_STATE")
        if reason is not None and (not isinstance(reason, str) or len(reason) > 2000):
            raise MergeAuthorityError("INVALID_REASON")
        payload = {
            "repository": repository,
            "pull_request_number": pull_request_number,
            "observed_head_sha": observed_head_sha,
            "final_merge_sha": final_merge_sha,
            "actor": actor,
            "readiness_current": readiness_current,
            "reason": reason,
            "observed_at": _timestamp(),
        }
        return self.ledger.append(
            "external_merge_observed",
            f"external:{repository}:{pull_request_number}:{final_merge_sha}",
            payload,
        )


class DisabledBreakGlass:
    def invoke(self, **_: Any) -> None:
        raise MergeAuthorityError("BREAK_GLASS_DISABLED")
