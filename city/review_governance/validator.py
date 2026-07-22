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
    scope_entries: list[Mapping[str, Any]] | None = None,
    consumer_core: str | None = None,
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
        return ValidationResult(state, exc.code, "review verdict rejected")
    if verdict.repository != repository:
        return ValidationResult("rejected", "INVALID_REPOSITORY", "review verdict rejected")
    if scope_entries is not None:
        try:
            if scope_digest(scope_entries) != verdict.scope_digest:
                return ValidationResult(
                    "rejected", "SCOPE_DIGEST_MISMATCH", "review verdict rejected"
                )
            if {entry["path"] for entry in scope_entries} != set(verdict.reviewed_files):
                return ValidationResult(
                    "rejected", "SCOPE_DIGEST_MISMATCH", "review verdict rejected"
                )
        except ScopeError as exc:
            return ValidationResult("rejected", exc.code, "review verdict rejected")
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
        )
    if any(ref.provider != "reviewer" for ref in verdict.evidence_refs):
        # B1-S1 has no live GitHub evidence adapter.  A structurally valid
        # external reference remains unavailable and cannot authorize anything.
        return ValidationResult(
            "blocked",
            "EVIDENCE_UNAVAILABLE",
            "head evidence is not externally verified",
            verdict,
            "unavailable",
        )
    if now is None:
        now = datetime.now(timezone.utc)
    if now.strftime("%Y-%m-%dT%H:%M:%SZ") >= verdict.expires_at:
        return ValidationResult(
            "stale", "EXPIRED", "review verdict expired", verdict, "structurally_valid"
        )
    if consumer_core is not None:
        state, code = classify_core(verdict.core_classification, consumer_core)
        if code:
            return ValidationResult(
                "blocked",
                code,
                "core classification requires escalation",
                verdict,
                "structurally_valid",
            )
    return ValidationResult(
        "valid",
        None,
        "review verdict structurally and cryptographically valid",
        verdict,
        "structurally_valid",
    )
