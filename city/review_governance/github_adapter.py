"""Read-only normalization boundary for caller-supplied GitHub observations."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Iterable

from .evidence import (
    ALLOWED_PROVIDERS,
    CONCLUSIONS,
    HEAD_POLICY,
    MERGE_POLICY,
    HeadEvidenceResult,
    IntegrationEvidenceResult,
)
from .schema import EvidenceRefB1

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


@dataclass(frozen=True)
class CheckObservation:
    repository: str
    pull_request_number: int
    policy_name: str
    sha: str
    conclusion: str
    provider: str
    producer_identity: str
    run_or_check_identity: str
    observed_at: str
    source_head_sha: str | None = None
    source_base_sha: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or self.repository.count("/") != 1:
            raise ValueError("INVALID_REPOSITORY")
        if (
            isinstance(self.pull_request_number, bool)
            or not isinstance(self.pull_request_number, int)
            or self.pull_request_number <= 0
        ):
            raise ValueError("INVALID_PR_NUMBER")
        if self.policy_name not in {HEAD_POLICY, MERGE_POLICY} or not SHA_RE.fullmatch(self.sha):
            raise ValueError("INVALID_OBSERVATION")
        if self.conclusion not in CONCLUSIONS or self.provider not in ALLOWED_PROVIDERS:
            raise ValueError("INVALID_OBSERVATION")
        if not self.producer_identity or not self.run_or_check_identity:
            raise ValueError("INVALID_OBSERVATION")
        try:
            dt.datetime.strptime(self.observed_at, "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            raise ValueError("INVALID_TIMESTAMP") from None
        if self.policy_name == MERGE_POLICY:
            if self.source_head_sha is None or self.source_base_sha is None:
                raise ValueError("INVALID_OBSERVATION")
            if not SHA_RE.fullmatch(self.source_head_sha) or not SHA_RE.fullmatch(
                self.source_base_sha
            ):
                raise ValueError("INVALID_OBSERVATION")

    @property
    def identity(self) -> str:
        """Compatibility alias; the closed field is run_or_check_identity."""
        return self.run_or_check_identity


class GitHubEvidenceAdapter:
    """Normalize observations after complete repository/PR identity filtering."""

    def __init__(self, observations: Iterable[CheckObservation]):
        self._observations = tuple(observations)

    def head(
        self, *, repository: str, pull_request_number: int, reviewed_head_sha: str
    ) -> HeadEvidenceResult:
        matches = [
            o
            for o in self._observations
            if o.repository == repository
            and o.pull_request_number == pull_request_number
            and o.policy_name == HEAD_POLICY
        ]
        if len(matches) != 1:
            state = "unavailable" if not matches else "ambiguous"
            return HeadEvidenceResult(
                repository,
                pull_request_number,
                HEAD_POLICY,
                None,
                reviewed_head_sha,
                "unknown",
                "github_check",
                "adapter",
                None,
                "1970-01-01T00:00:00Z",
                state,
                "EVIDENCE_UNAVAILABLE" if not matches else "AMBIGUOUS_EVIDENCE",
            )
        item = matches[0]
        state = (
            "verified"
            if item.sha == reviewed_head_sha and item.conclusion == "success"
            else "mismatched"
        )
        return HeadEvidenceResult(
            repository,
            pull_request_number,
            HEAD_POLICY,
            item.sha,
            reviewed_head_sha,
            item.conclusion,
            item.provider,
            item.producer_identity,
            item.run_or_check_identity,
            item.observed_at,
            state,
            None if state == "verified" else "EVIDENCE_SHA_MISMATCH",
        )

    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evidence_ref: EvidenceRefB1,
    ) -> HeadEvidenceResult:
        matches = [
            item
            for item in self._observations
            if item.repository == repository
            and item.pull_request_number == pull_request_number
            and item.policy_name == HEAD_POLICY
            and item.sha == evidence_ref.sha
            and item.provider == evidence_ref.provider
        ]
        if len(matches) != 1:
            state = "unavailable" if not matches else "ambiguous"
            return HeadEvidenceResult(
                repository,
                pull_request_number,
                HEAD_POLICY,
                None,
                reviewed_head_sha,
                "unknown",
                "github_check",
                "adapter",
                None,
                "1970-01-01T00:00:00Z",
                state,
                "EVIDENCE_UNAVAILABLE" if not matches else "AMBIGUOUS_EVIDENCE",
            )
        item = matches[0]
        state = (
            "verified"
            if item.sha == reviewed_head_sha and item.conclusion == "success"
            else "mismatched"
        )
        return HeadEvidenceResult(
            repository,
            pull_request_number,
            HEAD_POLICY,
            item.sha,
            reviewed_head_sha,
            item.conclusion,
            item.provider,
            item.producer_identity,
            item.run_or_check_identity,
            item.observed_at,
            state,
            None if state == "verified" else "EVIDENCE_SHA_MISMATCH",
        )

    def integration(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        current_base_sha: str,
        integration_sha: str,
    ) -> IntegrationEvidenceResult:
        matches = [
            o
            for o in self._observations
            if o.repository == repository
            and o.pull_request_number == pull_request_number
            and o.policy_name == MERGE_POLICY
        ]
        if len(matches) != 1:
            state = "unavailable" if not matches else "ambiguous"
            return IntegrationEvidenceResult(
                repository,
                pull_request_number,
                MERGE_POLICY,
                None,
                integration_sha,
                reviewed_head_sha,
                current_base_sha,
                "unknown",
                "github_check",
                "adapter",
                None,
                "1970-01-01T00:00:00Z",
                state,
                "EVIDENCE_UNAVAILABLE" if not matches else "AMBIGUOUS_EVIDENCE",
            )
        item = matches[0]
        valid = (
            item.sha == integration_sha
            and item.conclusion == "success"
            and item.source_head_sha == reviewed_head_sha
            and item.source_base_sha == current_base_sha
        )
        state = "verified" if valid else "mismatched"
        return IntegrationEvidenceResult(
            repository,
            pull_request_number,
            MERGE_POLICY,
            item.sha,
            integration_sha,
            item.source_head_sha,
            item.source_base_sha,
            item.conclusion,
            item.provider,
            item.producer_identity,
            item.run_or_check_identity,
            item.observed_at,
            state,
            None if valid else "EVIDENCE_SHA_MISMATCH",
        )
