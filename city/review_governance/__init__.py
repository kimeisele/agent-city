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
from .emitter import emit_verdict
from .validator import DeterministicEvidenceVerifier, validate_verdict

__all__ = [
    "EvidenceRefB1",
    "ReviewRequestB1",
    "build_review_request",
    "emit_verdict",
    "MergeReadinessEvaluationB1",
    "ReviewVerdictB1",
    "ReviewerKeyVerifier",
    "DeterministicEvidenceVerifier",
    "ValidationResult",
    "validate_verdict",
]
