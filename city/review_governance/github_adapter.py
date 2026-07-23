"""Read-only, injection-based GitHub evidence adapter boundary.

The production B1-S3A package does not invoke ``gh`` or the GitHub API.  A
future adapter can supply normalized records through this interface.  The
strict SHA checks here prevent a synthetic pull-request SHA from masquerading
as raw-head evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .evidence import HEAD_POLICY, MERGE_POLICY, HeadEvidenceResult, IntegrationEvidenceResult


@dataclass(frozen=True)
class CheckObservation:
    policy_name: str
    sha: str
    conclusion: str
    provider: str
    identity: str
    observed_at: str
    source_head_sha: str | None = None
    source_base_sha: str | None = None


class GitHubEvidenceAdapter:
    """Normalize caller-provided observations; never performs I/O itself."""

    def __init__(self, observations: Iterable[CheckObservation]):
        self._observations = tuple(observations)

    def head(self, *, reviewed_head_sha: str) -> HeadEvidenceResult:
        matches = [o for o in self._observations if o.policy_name == HEAD_POLICY]
        if len(matches) != 1:
            state = "unavailable" if not matches else "ambiguous"
            return HeadEvidenceResult(
                state,
                HEAD_POLICY,
                None,
                reviewed_head_sha,
                "unknown",
                "github",
                None,
                "1970-01-01T00:00:00Z",
                "EVIDENCE_UNAVAILABLE" if not matches else "AMBIGUOUS_EVIDENCE",
            )
        item = matches[0]
        state = (
            "verified"
            if item.sha == reviewed_head_sha and item.conclusion == "success"
            else "mismatched"
        )
        return HeadEvidenceResult(
            state,
            HEAD_POLICY,
            item.sha,
            reviewed_head_sha,
            item.conclusion,
            item.provider,
            item.identity,
            item.observed_at,
            None if state == "verified" else "EVIDENCE_SHA_MISMATCH",
        )

    def integration(
        self, *, reviewed_head_sha: str, current_base_sha: str, integration_sha: str
    ) -> IntegrationEvidenceResult:
        matches = [o for o in self._observations if o.policy_name == MERGE_POLICY]
        if len(matches) != 1:
            state = "unavailable" if not matches else "ambiguous"
            return IntegrationEvidenceResult(
                state,
                MERGE_POLICY,
                None,
                integration_sha,
                "unknown",
                "github",
                None,
                "1970-01-01T00:00:00Z",
                "EVIDENCE_UNAVAILABLE",
                reviewed_head_sha,
                current_base_sha,
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
            state,
            MERGE_POLICY,
            item.sha,
            integration_sha,
            item.conclusion,
            item.provider,
            item.identity,
            item.observed_at,
            None if valid else "EVIDENCE_SHA_MISMATCH",
            item.source_head_sha,
            item.source_base_sha,
        )
