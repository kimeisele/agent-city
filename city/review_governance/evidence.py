"""Read-only evidence boundaries for B1-S3A shadow evaluation.

This module deliberately contains no GitHub client and no subprocess calls.  A
deployment adapter may implement the protocols, while tests use the static
providers below.  Results are closed records so an absent or ambiguous check
cannot be represented as a successful boolean.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from .schema import EvidenceRefB1

HEAD_POLICY = "review-governance/head"
MERGE_POLICY = "review-governance/merge-result"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
EVIDENCE_STATES = frozenset(
    {"verified", "unavailable", "pending", "failed", "stale", "mismatched", "ambiguous"}
)


class EvidenceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sha(value: str) -> str:
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


@dataclass(frozen=True)
class HeadEvidenceResult:
    state: str
    policy_name: str
    observed_sha: str | None
    expected_sha: str
    conclusion: str
    provider: str
    run_or_check_identity: str | None
    observed_at: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise EvidenceError("INVALID_STATE")
        if self.policy_name != HEAD_POLICY:
            raise EvidenceError("INVALID_POLICY")
        _sha(self.expected_sha)
        if self.observed_sha is not None:
            _sha(self.observed_sha)
        _timestamp(self.observed_at)
        if not isinstance(self.provider, str) or not self.provider:
            raise EvidenceError("INVALID_PROVIDER")
        if self.state == "verified" and self.observed_sha != self.expected_sha:
            raise EvidenceError("EVIDENCE_SHA_MISMATCH")


@dataclass(frozen=True)
class IntegrationEvidenceResult:
    state: str
    policy_name: str
    observed_sha: str | None
    expected_sha: str
    conclusion: str
    provider: str
    run_or_check_identity: str | None
    observed_at: str
    error_code: str | None = None
    source_head_sha: str | None = None
    source_base_sha: str | None = None

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise EvidenceError("INVALID_STATE")
        if self.policy_name != MERGE_POLICY:
            raise EvidenceError("INVALID_POLICY")
        _sha(self.expected_sha)
        if self.observed_sha is not None:
            _sha(self.observed_sha)
        if self.source_head_sha is not None:
            _sha(self.source_head_sha)
        if self.source_base_sha is not None:
            _sha(self.source_base_sha)
        _timestamp(self.observed_at)
        if not isinstance(self.provider, str) or not self.provider:
            raise EvidenceError("INVALID_PROVIDER")
        if self.state == "verified" and self.observed_sha != self.expected_sha:
            raise EvidenceError("EVIDENCE_SHA_MISMATCH")


class HeadEvidenceProvider(Protocol):
    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evidence_refs: Sequence[EvidenceRefB1],
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
        evidence_refs: Sequence[EvidenceRefB1],
    ) -> HeadEvidenceResult:
        if self.result is None:
            return HeadEvidenceResult(
                "unavailable",
                HEAD_POLICY,
                None,
                reviewed_head_sha,
                "unknown",
                "static",
                None,
                "1970-01-01T00:00:00Z",
                "EVIDENCE_UNAVAILABLE",
            )
        return self.result


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
        if self.result is None:
            return IntegrationEvidenceResult(
                "unavailable",
                MERGE_POLICY,
                None,
                "0" * 40,
                "unknown",
                "static",
                None,
                "1970-01-01T00:00:00Z",
                "EVIDENCE_UNAVAILABLE",
                reviewed_head_sha,
                current_base_sha,
            )
        return self.result


class EvidenceReferenceVerifier:
    """Adapter used by the legacy verdict validator for one resolved result."""

    def __init__(self, result: HeadEvidenceResult):
        self.result = result

    def verify(self, reference: EvidenceRefB1):
        from .schema import VerificationResult

        if self.result.state == "verified":
            if self.result.policy_name == HEAD_POLICY and self.result.observed_sha == reference.sha:
                return VerificationResult("externally_verified")
            return VerificationResult("mismatched", "EVIDENCE_SHA_MISMATCH")
        if self.result.state == "mismatched":
            return VerificationResult("mismatched", "EVIDENCE_SHA_MISMATCH")
        return VerificationResult("unavailable", self.result.error_code or "EVIDENCE_UNAVAILABLE")
