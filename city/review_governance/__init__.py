"""Pure, shadow-only B1 review-governance records and validation.

Importing this package does not start a runtime, invoke GitHub, or activate
Federation transport.  The package intentionally has no caller integration.
"""

from .schema import (
    EvidenceRefB1,
    MergeReadinessEvaluationB1,
    ReviewVerdictB1,
    ReviewerKeyVerifier,
    ValidationResult,
)
from .request import ReviewRequestB1, build_review_request
from .emitter import VerdictIdFactory, emit_verdict
from .artifacts import read_artifacts, write_artifacts
from .validator import DeterministicEvidenceVerifier, Ed25519ReviewerKeyVerifier, validate_verdict
from .evidence import (
    HEAD_POLICY,
    MERGE_POLICY,
    AllowlistEvidenceProducerTrust,
    EvidenceProducerTrust,
    head_evidence_digest,
    HeadEvidenceProvider,
    HeadEvidenceResult,
    IntegrationEvidenceProvider,
    IntegrationEvidenceResult,
    StaticHeadEvidenceProvider,
    StaticIntegrationEvidenceProvider,
)
from .policy import BaseDriftEvaluation, PolicyCDecision, evaluate_base_drift, evaluate_policy_c
from .council import CouncilGateB1
from .readiness import (
    CurrentPRSnapshotB1,
    ShadowGovernanceDecision,
    ShadowReadinessResult,
    evaluate_shadow_readiness,
)

__all__ = [
    "EvidenceRefB1",
    "ReviewRequestB1",
    "build_review_request",
    "emit_verdict",
    "VerdictIdFactory",
    "read_artifacts",
    "write_artifacts",
    "MergeReadinessEvaluationB1",
    "ReviewVerdictB1",
    "ReviewerKeyVerifier",
    "DeterministicEvidenceVerifier",
    "Ed25519ReviewerKeyVerifier",
    "ValidationResult",
    "validate_verdict",
    "HEAD_POLICY",
    "MERGE_POLICY",
    "AllowlistEvidenceProducerTrust",
    "EvidenceProducerTrust",
    "head_evidence_digest",
    "HeadEvidenceProvider",
    "HeadEvidenceResult",
    "IntegrationEvidenceProvider",
    "IntegrationEvidenceResult",
    "StaticHeadEvidenceProvider",
    "StaticIntegrationEvidenceProvider",
    "BaseDriftEvaluation",
    "PolicyCDecision",
    "evaluate_base_drift",
    "evaluate_policy_c",
    "CouncilGateB1",
    "CurrentPRSnapshotB1",
    "ShadowGovernanceDecision",
    "ShadowReadinessResult",
    "evaluate_shadow_readiness",
]
