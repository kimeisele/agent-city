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
    EvidenceReferenceVerifier,
    HeadEvidenceProvider,
    IntegrationEvidenceProvider,
    IntegrationEvidenceResult,
)
from .ledger import ShadowLedger
from .policy import BaseDriftEvaluation, PolicyCDecision, evaluate_policy_c
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
        if not isinstance(self.repository, str) or not REPOSITORY_RE.fullmatch(self.repository):
            raise ValueError("INVALID_REPOSITORY")
        if not isinstance(self.pull_request_number, int) or self.pull_request_number <= 0:
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
            tuple(MappingProxyType(dict(entry)) for entry in normalized),
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
        if self.merge_authorized:
            raise ValueError("SHADOW_DECISION_CANNOT_AUTHORIZE")


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
    core_state = "non_core"
    if council_state == "approved":
        core_state = "core_approved"
    elif council_state != "not_required":
        core_state = "core_pending_council"
    checks = _check_result(integration)
    value = {
        "schema": "merge-readiness-evaluation-b1.1",
        "evaluation_id": evaluation_id,
        "verdict_id": verdict.verdict_id,
        "repository": request.repository,
        "pull_request_number": request.pull_request_number,
        "reviewed_head_sha": request.reviewed_head_sha,
        "validated_current_base_sha": snapshot.current_base_sha,
        "integration_check_sha": snapshot.integration_identity,
        "required_check_results": checks,
        "base_drift_classification": drift.classification,
        "scope_overlap_result": drift.overlap,
        "core_gate_state": core_state,
        "council_state": council_state,
        "merge_expected_head_sha": request.reviewed_head_sha,
        "readiness_state": state,
        "evaluated_at": evaluated_at,
    }
    return MergeReadinessEvaluationB1.from_mapping(value)


def evaluate_shadow_readiness(
    *,
    request: ReviewRequestB1,
    verdict: ReviewVerdictB1 | Mapping[str, Any] | bytes,
    snapshot: CurrentPRSnapshotB1,
    verifier: Any,
    head_provider: HeadEvidenceProvider,
    integration_provider: IntegrationEvidenceProvider,
    drift: BaseDriftEvaluation,
    consumer_core_classifier: Callable[[str], str],
    council_gate: CouncilGateB1 | None,
    evaluation_id: str,
    evaluated_at: str,
    ledger: ShadowLedger | None = None,
) -> ShadowReadinessResult:
    """Evaluate B1-S3A predicates and optionally append shadow evidence only."""
    if isinstance(verdict, ReviewVerdictB1):
        verdict_obj = verdict
    else:
        verdict_obj = (
            ReviewVerdictB1.from_canonical(verdict)
            if isinstance(verdict, bytes)
            else ReviewVerdictB1.from_mapping(verdict)
        )
    integration = integration_provider.resolve(
        repository=request.repository,
        pull_request_number=request.pull_request_number,
        reviewed_head_sha=request.reviewed_head_sha,
        current_base_sha=snapshot.current_base_sha,
    )
    head = head_provider.resolve(
        repository=request.repository,
        pull_request_number=request.pull_request_number,
        reviewed_head_sha=request.reviewed_head_sha,
        evidence_refs=verdict_obj.evidence_refs,
    )
    refs_are_h_policy = all(
        ref.kind == "head_security_evidence"
        and ref.name == HEAD_POLICY
        and ref.provider in {"github_check", "github_status"}
        and ref.sha == snapshot.current_head_sha
        for ref in verdict_obj.evidence_refs
    )
    if (
        snapshot.repository != request.repository
        or snapshot.pull_request_number != request.pull_request_number
    ):
        verdict_state, reason = "rejected", "PR_IDENTITY_MISMATCH"
    elif snapshot.current_head_sha != verdict_obj.reviewed_head_sha:
        verdict_state, reason = "stale", "REVIEWED_HEAD_STALE"
    elif (
        verdict_obj.review_request_id != request.review_request_id
        or verdict_obj.scope_digest != request.scope_digest
    ):
        verdict_state, reason = "rejected", "REQUEST_LINEAGE_MISMATCH"
    elif not refs_are_h_policy:
        verdict_state, reason = "blocked", "EVIDENCE_UNAVAILABLE"
    elif (
        head.policy_name != HEAD_POLICY
        or head.state != "verified"
        or head.conclusion != "success"
        or head.provider == "reviewer"
        or head.observed_sha != snapshot.current_head_sha
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
            evidence_verifier=EvidenceReferenceVerifier(head),
            scope_entries=[dict(item) for item in snapshot.current_scope_entries],
            consumer_core=_consumer_core(request.scope_entries, consumer_core_classifier),
            current_head_sha=snapshot.current_head_sha,
            expected_evidence_policy=HEAD_POLICY,
            now=dt.datetime.strptime(snapshot.observed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.UTC
            ),
        )
        verdict_state, reason = verification.state, verification.error_code or "OK"
    consumer_core = _consumer_core(request.scope_entries, consumer_core_classifier)
    effective_core = verdict_obj.core_classification == "core" or consumer_core == "core"
    council = council_gate or CouncilGateB1(snapshot.current_head_sha, "not_required")
    council_state = (
        council.state if council.review_head_sha == snapshot.current_head_sha else "unknown"
    )
    integration_ready = (
        integration.state == "verified"
        and integration.policy_name == MERGE_POLICY
        and integration.observed_sha == snapshot.integration_identity
        and integration.source_head_sha == snapshot.current_head_sha
        and integration.source_base_sha == snapshot.current_base_sha
        and integration.conclusion == "success"
    )
    decision = evaluate_policy_c(
        verdict_valid=verdict_state == "valid",
        drift=drift,
        integration_ready=integration_ready,
    )
    if effective_core and not council_allows(core_classification="core", gate=council):
        decision = PolicyCDecision(
            "blocked", "COUNCIL_REQUIRED", False, False, drift.classification
        )
    if verdict_state == "stale":
        decision = PolicyCDecision("blocked", reason, False, False, drift.classification)
    if verdict_state == "rejected":
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
            head.state,
            integration.state,
            drift.classification,
            False,
        ),
    )
