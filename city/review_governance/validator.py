"""Fail-closed B1 validator and explicit reviewer-key boundary."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .schema import ReviewVerdictB1, SchemaError, ValidationResult, VerificationResult
from .scope import ScopeError, scope_digest


class Ed25519ReviewerKeyVerifier:
    """Explicit allowlist verifier for tests or a configured local adapter."""

    def __init__(self, keys: Mapping[tuple[str, str], bytes]):
        self._keys = dict(keys)

    def verify(
        self, reviewer_identity: str, reviewer_key_id: str, payload: bytes, signature: str
    ) -> VerificationResult:
        key = self._keys.get((reviewer_identity, reviewer_key_id))
        if key is None:
            return VerificationResult("unavailable", "UNKNOWN_REVIEWER_KEY")
        try:
            raw_sig = base64.b64decode(signature, validate=True)
            Ed25519PublicKey.from_public_bytes(key).verify(raw_sig, payload)
        except (ValueError, TypeError, InvalidSignature):
            return VerificationResult("mismatched", "INVALID_SIGNATURE")
        return VerificationResult("externally_verified")


class DeterministicEvidenceVerifier:
    """Test-only evidence verifier; it has no GitHub or network access."""

    def __init__(self, references: set[tuple[str, str, str, str, str]]):
        self._references = set(references)

    def verify(self, reference: Any) -> VerificationResult:
        identity = (
            reference.kind,
            reference.sha,
            reference.provider,
            reference.name,
            reference.evidence_digest,
        )
        if identity in self._references:
            return VerificationResult("externally_verified")
        return VerificationResult("mismatched", "EVIDENCE_UNAVAILABLE")


def classify_core(producer: str, consumer: str) -> tuple[str, str | None]:
    if consumer == "unknown":
        return "blocked", "CORE_CLASSIFICATION_CONFLICT"
    if producer == "core" or consumer == "core":
        if producer == "non_core" and consumer == "core":
            return "blocked", "CORE_CLASSIFICATION_CONFLICT"
        return "core", None
    return "non_core", None


def validate_verdict(
    value: Mapping[str, Any] | bytes | str,
    *,
    repository: str,
    verifier: Any,
    evidence_verifier: Any | None = None,
    scope_entries: list[Mapping[str, Any]] | None = None,
    consumer_core: str | None = None,
    current_head_sha: str | None = None,
    expected_evidence_policy: str | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    try:
        verdict = (
            ReviewVerdictB1.from_canonical(value)
            if isinstance(value, (bytes, str))
            else ReviewVerdictB1.from_mapping(value)
        )
    except SchemaError as exc:
        state = "stale" if exc.code == "EXPIRED" else "rejected"
        return ValidationResult(state, exc.code, "review verdict rejected", schema_valid=False)
    if verdict.repository != repository:
        return ValidationResult(
            "rejected", "INVALID_REPOSITORY", "review verdict rejected", schema_valid=True
        )
    if current_head_sha is not None and current_head_sha != verdict.reviewed_head_sha:
        return ValidationResult(
            "stale", "REVIEWED_HEAD_STALE", "review verdict head is stale", schema_valid=True
        )
    if expected_evidence_policy is not None and any(
        reference.name != expected_evidence_policy for reference in verdict.evidence_refs
    ):
        return ValidationResult(
            "blocked",
            "EVIDENCE_UNAVAILABLE",
            "head evidence policy is unavailable",
            schema_valid=True,
        )
    if scope_entries is not None:
        try:
            if scope_digest(scope_entries) != verdict.scope_digest:
                return ValidationResult(
                    "rejected",
                    "SCOPE_DIGEST_MISMATCH",
                    "review verdict rejected",
                    schema_valid=True,
                )
            if {entry["path"] for entry in scope_entries} != set(verdict.reviewed_files):
                return ValidationResult(
                    "rejected",
                    "SCOPE_DIGEST_MISMATCH",
                    "review verdict rejected",
                    schema_valid=True,
                )
        except ScopeError as exc:
            return ValidationResult(
                "rejected", exc.code, "review verdict rejected", schema_valid=True
            )
    result = verifier.verify(
        verdict.reviewer_identity,
        verdict.reviewer_key_id,
        verdict.signature_input(),
        verdict.signature,
    )
    if result.state != "externally_verified":
        return ValidationResult(
            "blocked" if result.state == "unavailable" else "rejected",
            result.error_code or "INVALID_SIGNATURE",
            "review verdict not authorized",
            schema_valid=True,
            signature_valid=False,
        )
    if evidence_verifier is None:
        evidence_state = (
            "unavailable"
            if any(ref.provider != "reviewer" for ref in verdict.evidence_refs)
            else "structurally_valid"
        )
        return ValidationResult(
            "blocked",
            "EVIDENCE_UNAVAILABLE",
            "head evidence is not independently verified",
            validated_identity=verdict,
            evidence_state=evidence_state,
            schema_valid=True,
            signature_valid=True,
        )
    if any(ref.provider == "reviewer" for ref in verdict.evidence_refs):
        return ValidationResult(
            "blocked",
            "EVIDENCE_UNAVAILABLE",
            "reviewer self-reference is not independent evidence",
            validated_identity=verdict,
            evidence_state="structurally_valid",
            schema_valid=True,
            signature_valid=True,
        )
    for reference in verdict.evidence_refs:
        evidence_result = evidence_verifier.verify(reference)
        if evidence_result.state == "mismatched":
            return ValidationResult(
                "rejected",
                "EVIDENCE_SHA_MISMATCH",
                "head evidence does not match its verified identity",
                validated_identity=verdict,
                evidence_state="mismatched",
                schema_valid=True,
                signature_valid=True,
            )
        if evidence_result.state != "externally_verified":
            return ValidationResult(
                "blocked",
                "EVIDENCE_UNAVAILABLE",
                "head evidence is unavailable",
                validated_identity=verdict,
                evidence_state="unavailable",
                schema_valid=True,
                signature_valid=True,
            )
    if now is None:
        now = datetime.now(timezone.utc)
    if now.strftime("%Y-%m-%dT%H:%M:%SZ") >= verdict.expires_at:
        return ValidationResult(
            "stale", "EXPIRED", "review verdict expired", verdict, "externally_verified", True, True
        )
    if consumer_core is not None:
        state, code = classify_core(verdict.core_classification, consumer_core)
        if code:
            return ValidationResult(
                "blocked",
                code,
                "core classification requires escalation",
                validated_identity=verdict,
                evidence_state="externally_verified",
                schema_valid=True,
                signature_valid=True,
            )
    return ValidationResult(
        "valid",
        None,
        "review verdict structurally and cryptographically valid",
        validated_identity=verdict,
        evidence_state="externally_verified",
        schema_valid=True,
        signature_valid=True,
    )
