from __future__ import annotations

import datetime as dt

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from city.review_governance import (
    AllowlistEvidenceProducerTrust,
    CouncilGateB1,
    CurrentPRSnapshotB1,
    Ed25519ReviewerKeyVerifier,
    evaluate_base_drift,
    evaluate_shadow_readiness,
)
from city.review_governance.evidence import (
    HEAD_POLICY,
    MERGE_POLICY,
    HeadEvidenceResult,
    IntegrationEvidenceResult,
    StaticHeadEvidenceProvider,
    StaticIntegrationEvidenceProvider,
)
from city.review_governance.github_adapter import CheckObservation, GitHubEvidenceAdapter
from city.review_governance.policy import BaseDriftEvaluation
from city.review_governance.emitter import emit_verdict
from city.review_governance.request import build_review_request
from city.review_governance.signer import Ed25519ReviewerSigner

REPOSITORY = "kimeisele/agent-city"
HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40
OTHER = "d" * 40
OBSERVED = "2026-07-23T12:00:00Z"
SCOPE = [
    {
        "path": "city/review_governance/policy.py",
        "change_type": "modified",
        "previous_path": None,
        "base_blob_sha": "1" * 40,
        "head_blob_sha": "2" * 40,
    }
]


class RequestIds:
    def create(self, **_: object) -> str:
        return "request-1"


def _fixture():
    request = build_review_request(
        repository=REPOSITORY,
        pull_request_number=42,
        reviewed_head_sha=HEAD,
        review_request_base_sha=BASE,
        scope_entries=SCOPE,
        requested_reviewer_identity="reviewer-1",
        requester_identity="builder-1",
        requested_at=dt.datetime(2026, 7, 23, tzinfo=dt.UTC),
        expires_at=dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
        reason="review",
        id_factory=RequestIds(),
    )
    key = Ed25519PrivateKey.generate()
    signer = Ed25519ReviewerSigner(
        reviewer_identity="reviewer-1", reviewer_key_id="key-1", private_key=key
    )
    ref = {
        "kind": "head_security_evidence",
        "sha": HEAD,
        "provider": "github_check",
        "name": HEAD_POLICY,
        "evidence_digest": "sha256:" + "e" * 64,
    }
    verdict, _ = emit_verdict(
        request,
        decision="approve",
        review_reason="ok",
        producer_core_classification="non_core",
        evidence_refs=[ref],
        reviewer_identity="reviewer-1",
        reviewer_key_id="key-1",
        signer=signer,
        issued_at=dt.datetime(2026, 7, 23, tzinfo=dt.UTC),
        expires_at=dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
        verdict_id="verdict-1",
    )
    snapshot = CurrentPRSnapshotB1(REPOSITORY, 42, HEAD, BASE, tuple(SCOPE), MERGE, OBSERVED)
    head = HeadEvidenceResult(
        REPOSITORY,
        42,
        HEAD_POLICY,
        HEAD,
        HEAD,
        "success",
        "github_check",
        "producer-1",
        "check-1",
        OBSERVED,
        "verified",
    )
    integration = IntegrationEvidenceResult(
        REPOSITORY,
        42,
        MERGE_POLICY,
        MERGE,
        MERGE,
        HEAD,
        BASE,
        "success",
        "github_check",
        "producer-1",
        "check-2",
        OBSERVED,
        "verified",
    )
    verifier = Ed25519ReviewerKeyVerifier(
        {("reviewer-1", "key-1"): key.public_key().public_bytes_raw()}
    )
    trust = AllowlistEvidenceProducerTrust(
        {
            (REPOSITORY, HEAD_POLICY, "github_check", "producer-1"),
            (REPOSITORY, MERGE_POLICY, "github_check", "producer-1"),
        }
    )
    return request, verdict, snapshot, head, integration, verifier, trust


def _run(request, verdict, snapshot, head, integration, verifier, trust, **overrides):
    values = {
        "request": request,
        "verdict": verdict,
        "snapshot": snapshot,
        "verifier": verifier,
        "head_provider": StaticHeadEvidenceProvider(head),
        "integration_provider": StaticIntegrationEvidenceProvider(integration),
        "base_delta_scope": None,
        "ancestry_available": True,
        "consumer_core_classifier": lambda _: "non_core",
        "council_gate": None,
        "producer_trust": trust,
        "evaluation_id": "evaluation-1",
        "evaluated_at": OBSERVED,
    }
    values.update(overrides)
    return evaluate_shadow_readiness(**values)


def test_exact_provenance_yields_shadow_ready_without_merge_authority():
    args = _fixture()
    result = _run(*args)
    assert result.decision.state == "shadow_ready"
    assert result.decision.merge_authorized is False
    assert result.evaluation.readiness_state == "ready"


def test_cross_repository_evidence_blocks_and_is_not_replayed():
    request, verdict, snapshot, _, integration, verifier, trust = _fixture()
    wrong = HeadEvidenceResult(
        "other/repository",
        42,
        HEAD_POLICY,
        HEAD,
        HEAD,
        "success",
        "github_check",
        "producer-1",
        "check-1",
        OBSERVED,
        "verified",
    )
    result = _run(request, verdict, snapshot, wrong, integration, verifier, trust)
    assert result.decision.state == "blocked"
    assert result.decision.reason_code == "EVIDENCE_UNAVAILABLE"


def test_cross_pr_and_unknown_producer_block():
    request, verdict, snapshot, head, integration, verifier, trust = _fixture()
    wrong_pr = HeadEvidenceResult(
        REPOSITORY,
        99,
        HEAD_POLICY,
        HEAD,
        HEAD,
        "success",
        "github_check",
        "producer-1",
        "check-1",
        OBSERVED,
        "verified",
    )
    assert (
        _run(request, verdict, snapshot, wrong_pr, integration, verifier, trust).decision.state
        == "blocked"
    )
    unknown = HeadEvidenceResult(
        REPOSITORY,
        42,
        HEAD_POLICY,
        HEAD,
        HEAD,
        "success",
        "github_check",
        "unknown-producer",
        "check-1",
        OBSERVED,
        "verified",
    )
    assert (
        _run(request, verdict, snapshot, unknown, integration, verifier, trust).decision.state
        == "blocked"
    )


def test_integration_binds_repository_pr_head_base_and_merge():
    request, verdict, snapshot, head, _, verifier, trust = _fixture()
    wrong = IntegrationEvidenceResult(
        "other/repository",
        42,
        MERGE_POLICY,
        MERGE,
        MERGE,
        HEAD,
        BASE,
        "success",
        "github_check",
        "producer-1",
        "check-2",
        OBSERVED,
        "verified",
    )
    result = _run(request, verdict, snapshot, head, wrong, verifier, trust)
    assert result.decision.state == "blocked"


def test_mismatched_request_snapshot_skips_provider_resolution():
    request, verdict, snapshot, head, integration, verifier, trust = _fixture()
    wrong_snapshot = CurrentPRSnapshotB1(
        "other/repository", 42, HEAD, BASE, tuple(SCOPE), MERGE, OBSERVED
    )

    class ExplodingProvider:
        def resolve(self, **_: object):
            raise AssertionError("provider must not run")

    result = _run(
        request,
        verdict,
        wrong_snapshot,
        head,
        integration,
        verifier,
        trust,
        head_provider=ExplodingProvider(),
        integration_provider=ExplodingProvider(),
    )
    assert result.decision.reason_code == "REQUEST_LINEAGE_MISMATCH"


def test_wrong_head_is_stale_and_old_verdict_is_not_rewritten():
    request, verdict, snapshot, head, integration, verifier, trust = _fixture()
    moved = CurrentPRSnapshotB1(REPOSITORY, 42, OTHER, BASE, tuple(SCOPE), MERGE, OBSERVED)
    result = _run(request, verdict, moved, head, integration, verifier, trust)
    assert result.decision.state == "stale_head"
    assert verdict.reviewed_head_sha == HEAD


def test_non_core_non_overlap_preserves_verdict_but_requires_new_integration():
    request, verdict, _, head, _, verifier, trust = _fixture()
    current = CurrentPRSnapshotB1(REPOSITORY, 42, HEAD, OTHER, tuple(SCOPE), MERGE, OBSERVED)
    delta = [
        {
            "path": "README.md",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": "3" * 40,
            "head_blob_sha": "4" * 40,
        }
    ]
    old_integration = IntegrationEvidenceResult(
        REPOSITORY,
        42,
        MERGE_POLICY,
        MERGE,
        MERGE,
        HEAD,
        BASE,
        "success",
        "github_check",
        "producer-1",
        "old",
        OBSERVED,
        "mismatched",
        "EVIDENCE_SHA_MISMATCH",
    )
    result = _run(
        request, verdict, current, head, old_integration, verifier, trust, base_delta_scope=delta
    )
    assert result.decision.state == "blocked"
    assert result.evaluation.base_drift_classification == "non_core_non_overlap"
    assert verdict.canonical_bytes() == verdict.canonical_bytes()


def test_core_drift_requires_exact_head_council_approval():
    request, verdict, _, head, integration, verifier, trust = _fixture()
    current = CurrentPRSnapshotB1(REPOSITORY, 42, HEAD, OTHER, tuple(SCOPE), MERGE, OBSERVED)
    delta = [
        {
            "path": "city/pr_lifecycle.py",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": "3" * 40,
            "head_blob_sha": "4" * 40,
        }
    ]
    pending = CouncilGateB1(REPOSITORY, 42, HEAD, "pending")
    result = _run(
        request,
        verdict,
        current,
        head,
        integration,
        verifier,
        trust,
        base_delta_scope=delta,
        consumer_core_classifier=lambda _: "core",
        council_gate=pending,
    )
    assert result.decision.state in {"fresh_review_required", "blocked"}


def test_drift_is_computed_and_contradictory_assertions_are_impossible():
    none = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=BASE,
        reviewed_scope=SCOPE,
        base_delta_scope=None,
        consumer_core_classifier=lambda _: "non_core",
    )
    assert none.classification == "none" and not none.base_moved
    unknown = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=OTHER,
        reviewed_scope=SCOPE,
        base_delta_scope=None,
        consumer_core_classifier=lambda _: "non_core",
        ancestry_available=False,
    )
    assert unknown.classification == "unknown"


def test_closed_drift_and_council_records_reject_contradictions():
    with pytest.raises(ValueError):
        BaseDriftEvaluation("none", True, "none", (), ())
    with pytest.raises(ValueError):
        CouncilGateB1(REPOSITORY, 42, HEAD, "approved")
    with pytest.raises(ValueError):
        CouncilGateB1(REPOSITORY, 42, HEAD, "not_required", "approval-1")


def test_github_observations_bind_complete_identity_and_duplicates_ambiguous():
    observation = CheckObservation(
        REPOSITORY,
        42,
        HEAD_POLICY,
        HEAD,
        "success",
        "github_check",
        "producer-1",
        "run-1",
        OBSERVED,
    )
    adapter = GitHubEvidenceAdapter([observation, observation])
    result = adapter.head(repository=REPOSITORY, pull_request_number=42, reviewed_head_sha=HEAD)
    assert result.state == "ambiguous"
    other = CheckObservation(
        "other/repository",
        42,
        HEAD_POLICY,
        HEAD,
        "success",
        "github_check",
        "producer-1",
        "run-2",
        OBSERVED,
    )
    isolated = GitHubEvidenceAdapter([other])
    assert (
        isolated.head(repository=REPOSITORY, pull_request_number=42, reviewed_head_sha=HEAD).state
        == "unavailable"
    )
