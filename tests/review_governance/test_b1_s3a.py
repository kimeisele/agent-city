from __future__ import annotations

import datetime as dt

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from city.review_governance import (
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
from city.review_governance.emitter import emit_verdict
from city.review_governance.request import build_review_request
from city.review_governance.signer import Ed25519ReviewerSigner


HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40
OTHER = "d" * 40
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
        repository="kimeisele/agent-city",
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
    snapshot = CurrentPRSnapshotB1(
        "kimeisele/agent-city",
        42,
        HEAD,
        BASE,
        tuple(SCOPE),
        MERGE,
        "2026-07-23T12:00:00Z",
    )
    head = HeadEvidenceResult(
        "verified", HEAD_POLICY, HEAD, HEAD, "success", "github", "check-1", "2026-07-23T12:00:00Z"
    )
    integration = IntegrationEvidenceResult(
        "verified",
        MERGE_POLICY,
        MERGE,
        MERGE,
        "success",
        "github",
        "check-2",
        "2026-07-23T12:00:00Z",
        source_head_sha=HEAD,
        source_base_sha=BASE,
    )
    verifier = Ed25519ReviewerKeyVerifier(
        {("reviewer-1", "key-1"): key.public_key().public_bytes_raw()}
    )
    return request, verdict, snapshot, head, integration, verifier


def test_h_and_merge_evidence_yield_shadow_ready_without_merge_authority():
    request, verdict, snapshot, head, integration, verifier = _fixture()
    drift = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=BASE,
        reviewed_scope=SCOPE,
        base_delta_scope=None,
        consumer_core_classifier=lambda _: "non_core",
    )
    result = evaluate_shadow_readiness(
        request=request,
        verdict=verdict,
        snapshot=snapshot,
        verifier=verifier,
        head_provider=StaticHeadEvidenceProvider(head),
        integration_provider=StaticIntegrationEvidenceProvider(integration),
        drift=drift,
        consumer_core_classifier=lambda _: "non_core",
        council_gate=None,
        evaluation_id="evaluation-1",
        evaluated_at="2026-07-23T12:00:00Z",
    )
    assert result.decision.state == "shadow_ready"
    assert result.decision.merge_authorized is False
    assert result.evaluation.readiness_state == "ready"


def test_wrong_head_is_stale_and_old_verdict_is_not_rewritten():
    request, verdict, snapshot, head, integration, verifier = _fixture()
    moved = CurrentPRSnapshotB1(
        "kimeisele/agent-city", 42, OTHER, BASE, tuple(SCOPE), MERGE, "2026-07-23T12:00:00Z"
    )
    drift = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=BASE,
        reviewed_scope=SCOPE,
        base_delta_scope=None,
        consumer_core_classifier=lambda _: "non_core",
    )
    result = evaluate_shadow_readiness(
        request=request,
        verdict=verdict,
        snapshot=moved,
        verifier=verifier,
        head_provider=StaticHeadEvidenceProvider(head),
        integration_provider=StaticIntegrationEvidenceProvider(integration),
        drift=drift,
        consumer_core_classifier=lambda _: "non_core",
        council_gate=None,
        evaluation_id="evaluation-2",
        evaluated_at="2026-07-23T12:00:00Z",
    )
    assert result.decision.state == "stale_head"
    assert verdict.reviewed_head_sha == HEAD


def test_missing_head_evidence_blocks_and_synthetic_sha_cannot_be_head():
    request, verdict, snapshot, _, integration, verifier = _fixture()
    unavailable = StaticHeadEvidenceProvider(None)
    drift = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=BASE,
        reviewed_scope=SCOPE,
        base_delta_scope=None,
        consumer_core_classifier=lambda _: "non_core",
    )
    result = evaluate_shadow_readiness(
        request=request,
        verdict=verdict,
        snapshot=snapshot,
        verifier=verifier,
        head_provider=unavailable,
        integration_provider=StaticIntegrationEvidenceProvider(integration),
        drift=drift,
        consumer_core_classifier=lambda _: "non_core",
        council_gate=None,
        evaluation_id="evaluation-3",
        evaluated_at="2026-07-23T12:00:00Z",
    )
    assert result.decision.state == "blocked"
    wrong = HeadEvidenceResult(
        "mismatched",
        HEAD_POLICY,
        MERGE,
        HEAD,
        "success",
        "github",
        "check-wrong",
        "2026-07-23T12:00:00Z",
        "EVIDENCE_SHA_MISMATCH",
    )
    result = evaluate_shadow_readiness(
        request=request,
        verdict=verdict,
        snapshot=snapshot,
        verifier=verifier,
        head_provider=StaticHeadEvidenceProvider(wrong),
        integration_provider=StaticIntegrationEvidenceProvider(integration),
        drift=drift,
        consumer_core_classifier=lambda _: "non_core",
        council_gate=None,
        evaluation_id="evaluation-4",
        evaluated_at="2026-07-23T12:00:00Z",
    )
    assert result.decision.state == "blocked"


def test_non_core_non_overlap_requires_new_current_base_integration():
    request, verdict, snapshot, head, integration, verifier = _fixture()
    current = CurrentPRSnapshotB1(
        "kimeisele/agent-city", 42, HEAD, OTHER, tuple(SCOPE), MERGE, "2026-07-23T12:00:00Z"
    )
    delta = [
        {
            "path": "README.md",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": "3" * 40,
            "head_blob_sha": "4" * 40,
        }
    ]
    drift = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=OTHER,
        reviewed_scope=SCOPE,
        base_delta_scope=delta,
        consumer_core_classifier=lambda _: "non_core",
    )
    old = IntegrationEvidenceResult(
        "mismatched",
        MERGE_POLICY,
        MERGE,
        MERGE,
        "success",
        "github",
        "old",
        "2026-07-23T12:00:00Z",
        "EVIDENCE_SHA_MISMATCH",
        source_head_sha=HEAD,
        source_base_sha=BASE,
    )
    result = evaluate_shadow_readiness(
        request=request,
        verdict=verdict,
        snapshot=current,
        verifier=verifier,
        head_provider=StaticHeadEvidenceProvider(head),
        integration_provider=StaticIntegrationEvidenceProvider(old),
        drift=drift,
        consumer_core_classifier=lambda _: "non_core",
        council_gate=None,
        evaluation_id="evaluation-5",
        evaluated_at="2026-07-23T12:00:00Z",
    )
    assert result.decision.state == "blocked"
    assert result.evaluation.base_drift_classification == "non_core_non_overlap"


def test_core_drift_requires_exact_head_council_approval():
    delta = [
        {
            "path": "city/pr_lifecycle.py",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": "3" * 40,
            "head_blob_sha": "4" * 40,
        }
    ]
    drift = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=OTHER,
        reviewed_scope=SCOPE,
        base_delta_scope=delta,
        consumer_core_classifier=lambda path: "core"
        if path == "city/pr_lifecycle.py"
        else "non_core",
    )
    assert drift.classification == "core_or_overlap"
    request, verdict, snapshot, head, integration, verifier = _fixture()
    current = CurrentPRSnapshotB1(
        "kimeisele/agent-city", 42, HEAD, OTHER, tuple(SCOPE), MERGE, "2026-07-23T12:00:00Z"
    )
    result = evaluate_shadow_readiness(
        request=request,
        verdict=verdict,
        snapshot=current,
        verifier=verifier,
        head_provider=StaticHeadEvidenceProvider(head),
        integration_provider=StaticIntegrationEvidenceProvider(integration),
        drift=drift,
        consumer_core_classifier=lambda _: "core",
        council_gate=CouncilGateB1(HEAD, "pending"),
        evaluation_id="evaluation-6",
        evaluated_at="2026-07-23T12:00:00Z",
    )
    assert result.decision.state in {"fresh_review_required", "blocked"}


def test_unknown_base_ancestry_blocks_fail_closed():
    drift = evaluate_base_drift(
        request_base_sha=BASE,
        current_base_sha=OTHER,
        reviewed_scope=SCOPE,
        base_delta_scope=None,
        consumer_core_classifier=lambda _: "non_core",
        ancestry_available=False,
    )
    assert drift.classification == "unknown"
