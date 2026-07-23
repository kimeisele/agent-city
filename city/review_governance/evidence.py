"""Read-only, provenance-bound evidence boundaries for B1-S3A."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from .schema import EvidenceRefB1
from .canonical import canonical_bytes

HEAD_POLICY = "review-governance/head"
MERGE_POLICY = "review-governance/merge-result"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
EVIDENCE_STATES = frozenset(
    {"verified", "unavailable", "pending", "failed", "stale", "mismatched", "ambiguous"}
)
CONCLUSIONS = frozenset(
    {"success", "failure", "cancelled", "timed_out", "skipped", "neutral", "unknown"}
)
ALLOWED_PROVIDERS = frozenset({"github_check", "github_status"})


class EvidenceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def head_evidence_projection(result: "HeadEvidenceResult") -> dict[str, object]:
    return {
        "repository": result.repository,
        "pull_request_number": result.pull_request_number,
        "policy_name": result.policy_name,
        "observed_sha": result.observed_sha,
        "provider": result.provider,
        "producer_identity": result.producer_identity,
        "run_or_check_identity": result.run_or_check_identity,
        "conclusion": result.conclusion,
        "observed_at": result.observed_at,
    }


def head_evidence_digest(result: "HeadEvidenceResult") -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(head_evidence_projection(result))).hexdigest()


def _sha(value: str | None, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise EvidenceError("INVALID_SHA")
    return value


def _timestamp(value: str) -> str:
    if not isinstance(value, str) or not TIME_RE.fullmatch(value):
        raise EvidenceError("INVALID_TIMESTAMP")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise EvidenceError("INVALID_TIMESTAMP") from exc
    return value


def _identity(value: str | None, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > 256:
        raise EvidenceError("INVALID_IDENTITY")
    return value


@dataclass(frozen=True)
class HeadEvidenceResult:
    repository: str
    pull_request_number: int
    policy_name: str
    observed_sha: str | None
    expected_sha: str
    conclusion: str
    provider: str
    producer_identity: str
    run_or_check_identity: str | None
    observed_at: str
    state: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not REPOSITORY_RE.fullmatch(self.repository):
            raise EvidenceError("INVALID_REPOSITORY")
        if (
            isinstance(self.pull_request_number, bool)
            or not isinstance(self.pull_request_number, int)
            or self.pull_request_number <= 0
        ):
            raise EvidenceError("INVALID_PR_NUMBER")
        if self.policy_name != HEAD_POLICY:
            raise EvidenceError("INVALID_POLICY")
        if self.state not in EVIDENCE_STATES:
            raise EvidenceError("INVALID_STATE")
        _sha(self.expected_sha)
        _sha(self.observed_sha, optional=True)
        _identity(self.producer_identity)
        if self.producer_identity in {"unavailable", "unknown", ""}:
            raise EvidenceError("INVALID_IDENTITY")
        _identity(self.run_or_check_identity, optional=True)
        if self.provider not in ALLOWED_PROVIDERS:
            raise EvidenceError("INVALID_PROVIDER")
        if self.conclusion not in CONCLUSIONS:
            raise EvidenceError("INVALID_CONCLUSION")
        _timestamp(self.observed_at)
        if self.state == "verified" and (
            self.observed_sha != self.expected_sha
            or self.conclusion != "success"
            or not self.run_or_check_identity
            or self.error_code is not None
        ):
            raise EvidenceError("EVIDENCE_SHA_MISMATCH")
        if self.state != "verified" and self.conclusion == "success":
            raise EvidenceError("INCONSISTENT_EVIDENCE")


@dataclass(frozen=True)
class IntegrationEvidenceResult:
    repository: str
    pull_request_number: int
    policy_name: str
    observed_sha: str | None
    expected_sha: str
    source_head_sha: str | None
    source_base_sha: str | None
    conclusion: str
    provider: str
    producer_identity: str
    run_or_check_identity: str | None
    observed_at: str
    state: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not REPOSITORY_RE.fullmatch(self.repository):
            raise EvidenceError("INVALID_REPOSITORY")
        if (
            isinstance(self.pull_request_number, bool)
            or not isinstance(self.pull_request_number, int)
            or self.pull_request_number <= 0
        ):
            raise EvidenceError("INVALID_PR_NUMBER")
        if self.policy_name != MERGE_POLICY:
            raise EvidenceError("INVALID_POLICY")
        if self.state not in EVIDENCE_STATES:
            raise EvidenceError("INVALID_STATE")
        _sha(self.expected_sha)
        _sha(self.observed_sha, optional=True)
        _sha(self.source_head_sha, optional=True)
        _sha(self.source_base_sha, optional=True)
        _identity(self.producer_identity)
        if self.producer_identity in {"unavailable", "unknown", ""}:
            raise EvidenceError("INVALID_IDENTITY")
        _identity(self.run_or_check_identity, optional=True)
        if self.provider not in ALLOWED_PROVIDERS:
            raise EvidenceError("INVALID_PROVIDER")
        if self.conclusion not in CONCLUSIONS:
            raise EvidenceError("INVALID_CONCLUSION")
        _timestamp(self.observed_at)
        if self.state == "verified" and (
            self.observed_sha != self.expected_sha
            or self.source_head_sha is None
            or self.source_base_sha is None
            or self.conclusion != "success"
            or not self.run_or_check_identity
            or self.error_code is not None
        ):
            raise EvidenceError("EVIDENCE_SHA_MISMATCH")
        if self.state != "verified" and self.conclusion == "success":
            raise EvidenceError("INCONSISTENT_EVIDENCE")


class HeadEvidenceProvider(Protocol):
    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evidence_ref: EvidenceRefB1,
    ) -> HeadEvidenceResult: ...


class IntegrationEvidenceProvider(Protocol):
    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        current_base_sha: str,
    ) -> IntegrationEvidenceResult: ...


class EvidenceProducerTrust(Protocol):
    def is_trusted(
        self, *, repository: str, policy_name: str, provider: str, producer_identity: str
    ) -> bool: ...


class AllowlistEvidenceProducerTrust:
    def __init__(self, entries: set[tuple[str, str, str, str]]):
        self._entries = frozenset(entries)

    def is_trusted(
        self, *, repository: str, policy_name: str, provider: str, producer_identity: str
    ) -> bool:
        return (repository, policy_name, provider, producer_identity) in self._entries


class StaticHeadEvidenceProvider:
    """Deterministic test provider; no network or filesystem access."""

    def __init__(self, result: HeadEvidenceResult | None):
        self.result = result

    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evidence_ref: EvidenceRefB1,
    ) -> HeadEvidenceResult:
        if self.result is not None:
            return self.result
        return HeadEvidenceResult(
            repository,
            pull_request_number,
            HEAD_POLICY,
            None,
            reviewed_head_sha,
            "unknown",
            "github_check",
            "static",
            None,
            "1970-01-01T00:00:00Z",
            "static",
            "EVIDENCE_UNAVAILABLE",
        )


class StaticIntegrationEvidenceProvider:
    """Deterministic test provider; callers provide one exact H/base result."""

    def __init__(self, result: IntegrationEvidenceResult | None):
        self.result = result

    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        current_base_sha: str,
    ) -> IntegrationEvidenceResult:
        if self.result is not None:
            return self.result
        return IntegrationEvidenceResult(
            repository,
            pull_request_number,
            MERGE_POLICY,
            None,
            "0" * 40,
            reviewed_head_sha,
            current_base_sha,
            "unknown",
            "github_check",
            "unavailable",
            None,
            "1970-01-01T00:00:00Z",
            "unavailable",
            "EVIDENCE_UNAVAILABLE",
        )


class EvidenceReferenceVerifier:
    def __init__(self, results: Sequence[tuple[EvidenceRefB1, HeadEvidenceResult]]):
        self.results = {reference: result for reference, result in results}

    def verify(self, reference: EvidenceRefB1):
        from .schema import VerificationResult

        result = self.results.get(reference)
        if result is None:
            return VerificationResult("unavailable", "EVIDENCE_UNAVAILABLE")
        if (
            result.state == "verified"
            and reference.kind == "head_security_evidence"
            and reference.sha == result.observed_sha
            and reference.provider == result.provider
            and reference.name == result.policy_name
            and reference.evidence_digest == head_evidence_digest(result)
            and result.conclusion == "success"
        ):
            return VerificationResult("externally_verified")
        if result.state == "mismatched":
            return VerificationResult("mismatched", "EVIDENCE_SHA_MISMATCH")
        return VerificationResult("unavailable", result.error_code or "EVIDENCE_UNAVAILABLE")
