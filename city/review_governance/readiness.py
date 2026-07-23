"""Shadow-only consumer orchestration for B1-S3A."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from .council import CouncilGateB1, council_allows
from .evidence import (
    HEAD_POLICY,
    MERGE_POLICY,
    EvidenceProducerTrust,
    EvidenceReferenceVerifier,
    HeadEvidenceProvider,
    HeadEvidenceResult,
    IntegrationEvidenceProvider,
    IntegrationEvidenceResult,
)
from .ledger import ShadowLedger
from .policy import BaseDriftEvaluation, PolicyCDecision, evaluate_base_drift, evaluate_policy_c
from .request import ReviewRequestB1
from .schema import MergeReadinessEvaluationB1, ReviewVerdictB1
from .scope import ScopeError, canonical_scope
from .validator import validate_verdict

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


@dataclass(frozen=True)
class CurrentPRSnapshotB1:
    repository: str
    pull_request_number: int
    current_head_sha: str
    current_base_sha: str
    current_scope_entries: tuple[Mapping[str, Any], ...]
    integration_identity: str
    observed_at: str

    def __post_init__(self) -> None:
        if not REPOSITORY_RE.fullmatch(self.repository):
            raise ValueError("INVALID_REPOSITORY")
        if (
            isinstance(self.pull_request_number, bool)
            or not isinstance(self.pull_request_number, int)
            or self.pull_request_number <= 0
        ):
            raise ValueError("INVALID_PR_NUMBER")
        for value in (self.current_head_sha, self.current_base_sha, self.integration_identity):
            if not isinstance(value, str) or not SHA_RE.fullmatch(value):
                raise ValueError("INVALID_SHA")
        if not TIME_RE.fullmatch(self.observed_at):
            raise ValueError("INVALID_TIMESTAMP")
        try:
            normalized = canonical_scope(self.current_scope_entries)
        except ScopeError as exc:
            raise ValueError(exc.code) from exc
        object.__setattr__(
            self,
            "current_scope_entries",
            tuple(MappingProxyType(dict(item)) for item in normalized),
        )


@dataclass(frozen=True)
class ShadowGovernanceDecision:
    state: str
    reason_code: str
    verdict_state: str
    head_evidence_state: str
    integration_evidence_state: str
    base_drift_classification: str
    merge_authorized: bool = False

    def __post_init__(self) -> None:
        if self.state not in {
            "shadow_ready",
            "blocked",
            "stale_head",
            "fresh_review_required",
            "pending_evidence",
            "invalid_verdict",
        }:
            raise ValueError("INVALID_DECISION_STATE")
        if self.verdict_state not in {"valid", "blocked", "stale", "rejected"}:
            raise ValueError("INVALID_VERDICT_STATE")
        if self.head_evidence_state not in {
            "verified",
            "unavailable",
            "pending",
            "failed",
            "stale",
            "mismatched",
            "ambiguous",
        }:
            raise ValueError("INVALID_EVIDENCE_STATE")
        if self.integration_evidence_state not in {
            "verified",
            "unavailable",
            "pending",
            "failed",
            "stale",
            "mismatched",
            "ambiguous",
        }:
            raise ValueError("INVALID_EVIDENCE_STATE")
        if self.base_drift_classification not in {
            "none",
            "non_core_non_overlap",
            "core_or_overlap",
            "conflict",
            "unknown",
        }:
            raise ValueError("INVALID_DRIFT_CLASSIFICATION")
        if self.merge_authorized:
            raise ValueError("SHADOW_DECISION_CANNOT_AUTHORIZE")
        if self.state == "shadow_ready" and (
            self.verdict_state != "valid"
            or self.head_evidence_state != "verified"
            or self.integration_evidence_state != "verified"
            or self.base_drift_classification not in {"none", "non_core_non_overlap"}
        ):
            raise ValueError("INCONSISTENT_DECISION")
        if self.state == "stale_head" and self.verdict_state != "stale":
            raise ValueError("INCONSISTENT_DECISION")


@dataclass(frozen=True)
class ShadowReadinessResult:
    evaluation: MergeReadinessEvaluationB1
    decision: ShadowGovernanceDecision


def _consumer_core(
    scope_entries: Iterable[Mapping[str, Any]], classifier: Callable[[str], str]
) -> str:
    values = [classifier(entry["path"]) for entry in scope_entries]
    if any(value == "unknown" for value in values):
        return "unknown"
    return "core" if any(value == "core" for value in values) else "non_core"


def _check_result(integration: IntegrationEvidenceResult) -> list[dict[str, str]]:
    if integration.run_or_check_identity is None or integration.observed_sha is None:
        return []
    return [
        {
            "name": MERGE_POLICY,
            "head_sha": integration.observed_sha,
            "conclusion": integration.conclusion,
            "run_id": integration.run_or_check_identity,
        }
    ]


def _evaluation(
    *,
    request: ReviewRequestB1,
    verdict: ReviewVerdictB1,
    snapshot: CurrentPRSnapshotB1,
    drift: BaseDriftEvaluation,
    decision: PolicyCDecision,
    council_state: str,
    integration: IntegrationEvidenceResult,
    evaluation_id: str,
    evaluated_at: str,
) -> MergeReadinessEvaluationB1:
    state = (
        "ready"
        if decision.state == "verdict_usable"
        else ("invalidated" if decision.state == "fresh_review_required" else "blocked")
    )
    core_state = (
        "non_core"
        if council_state == "not_required"
        else ("core_approved" if council_state == "approved" else "core_pending_council")
    )
    value = {
        "schema": "merge-readiness-evaluation-b1.1",
        "evaluation_id": evaluation_id,
        "verdict_id": verdict.verdict_id,
        "repository": request.repository,
        "pull_request_number": request.pull_request_number,
        "reviewed_head_sha": request.reviewed_head_sha,
        "validated_current_base_sha": snapshot.current_base_sha,
        "integration_check_sha": snapshot.integration_identity,
        "required_check_results": _check_result(integration),
        "base_drift_classification": drift.classification,
        "scope_overlap_result": drift.overlap,
        "core_gate_state": core_state,
        "council_state": council_state,
        "merge_expected_head_sha": request.reviewed_head_sha,
        "readiness_state": state,
        "evaluated_at": evaluated_at,
    }
    return MergeReadinessEvaluationB1.from_mapping(value)


def _unavailable_results(
    request: ReviewRequestB1, snapshot: CurrentPRSnapshotB1
) -> tuple[HeadEvidenceResult, IntegrationEvidenceResult]:
    head = HeadEvidenceResult(
        request.repository,
        request.pull_request_number,
        HEAD_POLICY,
        None,
        snapshot.current_head_sha,
        "unknown",
        "github_check",
        "adapter",
        None,
        snapshot.observed_at,
        "unavailable",
        "REQUEST_LINEAGE_MISMATCH",
    )
    integration = IntegrationEvidenceResult(
        request.repository,
        request.pull_request_number,
        MERGE_POLICY,
        None,
        snapshot.integration_identity,
        snapshot.current_head_sha,
        snapshot.current_base_sha,
        "unknown",
        "github_check",
        "adapter",
        None,
        snapshot.observed_at,
        "unavailable",
        "REQUEST_LINEAGE_MISMATCH",
    )
    return head, integration


def evaluate_shadow_readiness(
    *,
    request: ReviewRequestB1,
    verdict: ReviewVerdictB1 | Mapping[str, Any] | bytes,
    snapshot: CurrentPRSnapshotB1,
    verifier: Any,
    head_provider: HeadEvidenceProvider,
    integration_provider: IntegrationEvidenceProvider,
    base_delta_scope: Iterable[Mapping[str, Any]] | None,
    ancestry_available: bool,
    consumer_core_classifier: Callable[[str], str],
    council_gate: CouncilGateB1 | None,
    producer_trust: EvidenceProducerTrust | None,
    evaluation_id: str,
    evaluated_at: str,
    ledger: ShadowLedger | None = None,
) -> ShadowReadinessResult:
    """Compute all S3A predicates.  No caller-supplied drift is authoritative."""
    verdict_obj = (
        verdict
        if isinstance(verdict, ReviewVerdictB1)
        else (
            ReviewVerdictB1.from_canonical(verdict)
            if isinstance(verdict, bytes)
            else ReviewVerdictB1.from_mapping(verdict)
        )
    )
    drift = evaluate_base_drift(
        request_base_sha=request.review_request_base_sha,
        current_base_sha=snapshot.current_base_sha,
        reviewed_scope=request.scope_entries,
        base_delta_scope=base_delta_scope,
        consumer_core_classifier=consumer_core_classifier,
        ancestry_available=ancestry_available,
    )
    binding_ok = (
        request.repository == snapshot.repository
        and request.pull_request_number == snapshot.pull_request_number
        and verdict_obj.repository == request.repository
        and verdict_obj.pull_request_number == request.pull_request_number
        and verdict_obj.review_request_id == request.review_request_id
        and verdict_obj.reviewed_head_sha == request.reviewed_head_sha
        and verdict_obj.review_request_base_sha == request.review_request_base_sha
        and verdict_obj.scope_digest == request.scope_digest
        and verdict_obj.reviewed_files == request.reviewed_files
    )
    head_refs = tuple(
        ref for ref in verdict_obj.evidence_refs if ref.kind == "head_security_evidence"
    )
    if not binding_ok:
        head, integration = _unavailable_results(request, snapshot)
        head_state = head.state
        verdict_state, reason = "rejected", "REQUEST_LINEAGE_MISMATCH"
    elif not head_refs:
        head, integration = _unavailable_results(request, snapshot)
        head_state = head.state
        verdict_state, reason = "blocked", "EVIDENCE_UNAVAILABLE"
    else:
        head_pairs = tuple(
            (
                ref,
                head_provider.resolve(
                    repository=request.repository,
                    pull_request_number=request.pull_request_number,
                    reviewed_head_sha=request.reviewed_head_sha,
                    evidence_ref=ref,
                ),
            )
            for ref in head_refs
        )
        head = head_pairs[0][1]
        head_state = (
            "verified"
            if all(result.state == "verified" for _, result in head_pairs)
            else next(result.state for _, result in head_pairs if result.state != "verified")
        )
        refs_are_h_policy = bool(head_refs) and all(
            ref.kind == "head_security_evidence"
            and ref.name == HEAD_POLICY
            and ref.provider in {"github_check", "github_status"}
            and ref.sha == snapshot.current_head_sha
            for ref in head_refs
        )
        if snapshot.current_head_sha != verdict_obj.reviewed_head_sha:
            verdict_state, reason = "stale", "REVIEWED_HEAD_STALE"
        elif not refs_are_h_policy:
            verdict_state, reason = "blocked", "EVIDENCE_UNAVAILABLE"
        elif any(
            result.repository != request.repository
            or result.pull_request_number != request.pull_request_number
            or result.policy_name != HEAD_POLICY
            or result.state != "verified"
            or result.conclusion != "success"
            or result.provider not in {"github_check", "github_status"}
            or producer_trust is None
            or not producer_trust.is_trusted(
                repository=request.repository,
                policy_name=HEAD_POLICY,
                provider=result.provider,
                producer_identity=result.producer_identity,
            )
            or result.observed_sha != snapshot.current_head_sha
            for _, result in head_pairs
        ):
            verdict_state = "blocked" if head.state != "mismatched" else "rejected"
            reason = head.error_code or (
                "EVIDENCE_SHA_MISMATCH"
                if head.observed_sha != snapshot.current_head_sha
                else "EVIDENCE_UNAVAILABLE"
            )
        else:
            verification = validate_verdict(
                verdict_obj.to_mapping(),
                repository=request.repository,
                verifier=verifier,
                evidence_verifier=EvidenceReferenceVerifier(head_pairs),
                scope_entries=[dict(item) for item in request.scope_entries],
                consumer_core=_consumer_core(request.scope_entries, consumer_core_classifier),
                current_head_sha=snapshot.current_head_sha,
                expected_evidence_policy=HEAD_POLICY,
                now=dt.datetime.strptime(snapshot.observed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=dt.UTC
                ),
            )
            verdict_state, reason = verification.state, verification.error_code or "OK"
        if verdict_state == "valid":
            integration = integration_provider.resolve(
                repository=request.repository,
                pull_request_number=request.pull_request_number,
                reviewed_head_sha=request.reviewed_head_sha,
                current_base_sha=snapshot.current_base_sha,
                integration_sha=snapshot.integration_identity,
            )
        else:
            _, integration = _unavailable_results(request, snapshot)
    consumer_core = _consumer_core(request.scope_entries, consumer_core_classifier)
    effective_core = verdict_obj.core_classification == "core" or consumer_core == "core"
    council = council_gate or CouncilGateB1(
        request.repository, request.pull_request_number, snapshot.current_head_sha, "not_required"
    )
    council_state = (
        council.state
        if council_allows(
            core_classification="core" if effective_core else "non_core",
            gate=council,
            repository=request.repository,
            pull_request_number=request.pull_request_number,
            review_head_sha=snapshot.current_head_sha,
        )
        or (not effective_core and council.review_head_sha == snapshot.current_head_sha)
        else "unknown"
    )
    integration_ready = (
        integration.repository == request.repository
        and integration.pull_request_number == request.pull_request_number
        and integration.state == "verified"
        and integration.policy_name == MERGE_POLICY
        and integration.observed_sha == snapshot.integration_identity
        and integration.source_head_sha == snapshot.current_head_sha
        and integration.source_base_sha == snapshot.current_base_sha
        and integration.conclusion == "success"
        and producer_trust is not None
        and producer_trust.is_trusted(
            repository=request.repository,
            policy_name=MERGE_POLICY,
            provider=integration.provider,
            producer_identity=integration.producer_identity,
        )
    )
    decision = evaluate_policy_c(
        verdict_valid=verdict_state == "valid", drift=drift, integration_ready=integration_ready
    )
    if effective_core and not council_allows(
        core_classification="core",
        gate=council,
        repository=request.repository,
        pull_request_number=request.pull_request_number,
        review_head_sha=snapshot.current_head_sha,
    ):
        decision = PolicyCDecision(
            "blocked", "COUNCIL_REQUIRED", False, False, drift.classification
        )
    if verdict_state in {"stale", "rejected", "blocked"}:
        decision = PolicyCDecision("blocked", reason, False, False, drift.classification)
    evaluation = _evaluation(
        request=request,
        verdict=verdict_obj,
        snapshot=snapshot,
        drift=drift,
        decision=decision,
        council_state=council_state if effective_core else "not_required",
        integration=integration,
        evaluation_id=evaluation_id,
        evaluated_at=evaluated_at,
    )
    if ledger is not None:
        ledger.append(
            "merge_readiness_evaluated",
            evaluation_id,
            {
                "verdict_id": verdict_obj.verdict_id,
                "reviewed_head_sha": verdict_obj.reviewed_head_sha,
                "review_request_base_sha": request.review_request_base_sha,
                "validated_current_base_sha": snapshot.current_base_sha,
                "integration_check_sha": snapshot.integration_identity,
                "merge_expected_head_sha": verdict_obj.reviewed_head_sha,
                "readiness_state": evaluation.readiness_state,
            },
        )
    outcome = (
        "shadow_ready"
        if decision.state == "verdict_usable"
        else (
            "stale_head"
            if verdict_state == "stale"
            else (
                "fresh_review_required" if decision.state == "fresh_review_required" else "blocked"
            )
        )
    )
    return ShadowReadinessResult(
        evaluation,
        ShadowGovernanceDecision(
            outcome,
            decision.reason_code,
            verdict_state,
            head_state,
            integration.state,
            drift.classification,
            False,
        ),
    )
