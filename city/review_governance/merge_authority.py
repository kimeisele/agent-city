"""Disabled-by-default, SHA-bound merge authority and audit reconciliation."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

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
    merged_by: str | None = None
    merged_at: str | None = None

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
        if self.merged and (
            not self.merged_by
            or not ACTOR_RE.fullmatch(self.merged_by)
            or not self.merged_at
            or not TIME_RE.fullmatch(self.merged_at)
        ):
            raise MergeAuthorityError("MERGE_CAUSALITY_UNAVAILABLE")
        if not self.merged and (self.merged_by is not None or self.merged_at is not None):
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
    def run(self, args: list[str]) -> "MergeRunResult | str | None": ...


class FinalMergeStateResolver(Protocol):
    """Production boundary for a fresh GitHub/evidence/ledger observation."""

    def resolve(self) -> FinalMergeSnapshotB1: ...


@dataclass(frozen=True)
class MergeRunResult:
    attempt_id: str
    runner_started_at: str
    runner_completed_at: str
    expected_head_sha: str
    command_succeeded: bool
    output: str = ""

    def __post_init__(self) -> None:
        _validate_sha(self.expected_head_sha)
        if not TIME_RE.fullmatch(self.runner_started_at) or not TIME_RE.fullmatch(
            self.runner_completed_at
        ):
            raise MergeAuthorityError("INVALID_TIMESTAMP")
        if self.runner_completed_at < self.runner_started_at:
            raise MergeAuthorityError("INVALID_TIMESTAMP")


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
        resolver_factory: Callable[[], FinalMergeStateResolver] | None = None,
    ):
        self.enabled = enabled
        self.runner = runner or SubprocessGitHubRunner()
        self.ledger = ledger
        self.resolver_factory = resolver_factory

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
        actor: str,
        request_base_sha: str,
        reason: str = "",
    ) -> FinalMergeSnapshotB1:
        if self.resolver_factory is None:
            raise MergeAuthorityError("FINAL_RESOLVER_UNAVAILABLE")
        return self._merge(
            evaluation=evaluation,
            final_resolver=self.resolver_factory(),
            actor=actor,
            request_base_sha=request_base_sha,
            reason=reason,
        )

    def merge_with_test_resolver(
        self,
        *,
        evaluation: MergeReadinessEvaluationB1,
        final_resolver: FinalMergeStateResolver,
        actor: str,
        request_base_sha: str,
        reason: str = "",
    ) -> FinalMergeSnapshotB1:
        """Explicit test-only injection boundary; never used by production callers."""
        return self._merge(
            evaluation=evaluation,
            final_resolver=final_resolver,
            actor=actor,
            request_base_sha=request_base_sha,
            reason=reason,
        )

    def _merge(
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
        self._validate_final_state(evaluation, state, allow_merged_confirmation=True)
        reservation = self.ledger.find_event_by_payload(
            "merge_attempt_reserved", "evaluation_id", evaluation.evaluation_id
        )
        attempt_id = (
            reservation["payload"]["attempt_id"]
            if reservation is not None
            else f"merge-attempt:{evaluation.evaluation_id}:{uuid.uuid4().hex}"
        )
        completion = self.ledger.find_event_by_payload(
            "merge_completed", "evaluation_id", evaluation.evaluation_id
        )
        completion_id = completion["event_id"] if completion is not None else f"merge:{attempt_id}"
        if completion is not None:
            if not state.merged or state.final_merge_sha != completion["payload"].get(
                "final_merge_sha"
            ):
                raise MergeAuthorityError("MERGE_CONFIRMATION_MISMATCH")
            return state
        if state.merged and reservation is None:
            raise MergeAuthorityError("EXTERNAL_MERGE_REQUIRES_OBSERVATION")
        if reservation is None:
            try:
                self.ledger.append(
                    "merge_attempt_reserved",
                    attempt_id,
                    {
                        "attempt_id": attempt_id,
                        "attempt_nonce": attempt_id.rsplit(":", 1)[-1],
                        "worker_identity": actor,
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
        self._validate_final_state(evaluation, state, allow_merged_confirmation=state.merged)
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
        runner_started_at = _timestamp()
        raw_result = self.runner.run(args)
        runner_completed_at = _timestamp()
        if raw_result is None:
            raise MergeAuthorityError("MERGE_FAILED")
        run_result = (
            raw_result
            if isinstance(raw_result, MergeRunResult)
            else MergeRunResult(
                attempt_id,
                runner_started_at,
                runner_completed_at,
                evaluation.merge_expected_head_sha,
                True,
                str(raw_result),
            )
        )
        if (
            not run_result.command_succeeded
            or run_result.attempt_id != attempt_id
            or run_result.expected_head_sha != evaluation.merge_expected_head_sha
        ):
            raise MergeAuthorityError("MERGE_RUN_UNATTRIBUTABLE")
        try:
            self.ledger.append(
                "merge_attempt_succeeded",
                f"merge-success:{attempt_id}",
                {
                    "attempt_id": attempt_id,
                    "attempt_nonce": attempt_id.rsplit(":", 1)[-1],
                    "evaluation_id": evaluation.evaluation_id,
                    "repository": evaluation.repository,
                    "pull_request_number": evaluation.pull_request_number,
                    "expected_head_sha": run_result.expected_head_sha,
                    "actor": actor,
                    "runner_started_at": run_result.runner_started_at,
                    "runner_completed_at": run_result.runner_completed_at,
                },
            )
        except LedgerError as exc:
            raise MergeAuthorityError("MERGE_SUCCEEDED_AUDIT_PENDING") from exc
        confirmed = final_resolver.resolve()
        self._validate_final_state(evaluation, confirmed, allow_merged_confirmation=True)
        if not confirmed.merged or not confirmed.final_merge_sha:
            raise MergeAuthorityError("MERGE_CONFIRMATION_UNAVAILABLE")
        if (
            confirmed.merged_by != actor
            or confirmed.merged_at is None
            or not (
                run_result.runner_started_at
                <= confirmed.merged_at
                <= run_result.runner_completed_at
            )
        ):
            self._record_external_merge(confirmed, reason="MERGE_CAUSALITY_MISMATCH")
            raise MergeAuthorityError("EXTERNAL_MERGE_OBSERVED")
        try:
            self.ledger.append(
                "merge_completed",
                completion_id,
                {
                    "attempt_id": attempt_id,
                    "attempt_nonce": attempt_id.rsplit(":", 1)[-1],
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

    def _record_external_merge(self, state: FinalMergeSnapshotB1, *, reason: str) -> None:
        if self.ledger is None or state.final_merge_sha is None:
            return
        event_id = (
            f"external:{state.repository}:{state.pull_request_number}:{state.final_merge_sha}"
        )
        if self.ledger.find_event(event_id) is None:
            self.ledger.append(
                "external_merge_observed",
                event_id,
                {
                    "repository": state.repository,
                    "pull_request_number": state.pull_request_number,
                    "observed_head_sha": state.current_head_sha,
                    "final_merge_sha": state.final_merge_sha,
                    "actor": state.merged_by,
                    "readiness_current": not state.readiness_invalidated,
                    "reason": reason,
                    "observed_at": _timestamp(),
                },
            )

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
        reservation = self.ledger.find_event_by_payload(
            "merge_attempt_reserved", "evaluation_id", evaluation.evaluation_id
        )
        if reservation is None:
            raise MergeAuthorityError("NO_MERGE_RESERVATION")
        attempt_id = reservation["payload"].get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise MergeAuthorityError("LEDGER_CORRUPTION")
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
        proof = self.ledger.find_event_by_payload(
            "merge_attempt_succeeded", "attempt_id", attempt_id
        )
        if proof is None:
            if state.merged_by != actor:
                self._record_external_merge(state, reason="INTERNAL_SUCCESS_PROOF_UNAVAILABLE")
                raise MergeAuthorityError("EXTERNAL_MERGE_OBSERVED")
            raise MergeAuthorityError("MERGE_CAUSALITY_INDETERMINATE")
        if (
            proof["payload"].get("actor") != state.merged_by
            or proof["payload"].get("expected_head_sha") != state.current_head_sha
            or not (
                proof["payload"].get("runner_started_at", "")
                <= (state.merged_at or "")
                <= proof["payload"].get("runner_completed_at", "")
            )
        ):
            self._record_external_merge(state, reason="MERGE_CAUSALITY_MISMATCH")
            raise MergeAuthorityError("EXTERNAL_MERGE_OBSERVED")
        existing = self.ledger.find_event_by_payload(
            "merge_completed", "evaluation_id", evaluation.evaluation_id
        )
        if existing is not None:
            if existing["payload"].get("final_merge_sha") != state.final_merge_sha:
                raise MergeAuthorityError("MERGE_CONFIRMATION_MISMATCH")
            return state
        try:
            self.ledger.append(
                "merge_completed",
                f"merge:{attempt_id}",
                {
                    "attempt_id": attempt_id,
                    "attempt_nonce": attempt_id.rsplit(":", 1)[-1],
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
