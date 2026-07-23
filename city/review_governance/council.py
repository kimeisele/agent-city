"""Minimal exact-head Council gate boundary for shadow evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COUNCIL_STATES = frozenset({"not_required", "pending", "approved", "rejected", "unknown"})


@dataclass(frozen=True)
class CouncilGateB1:
    repository: str
    pull_request_number: int
    review_head_sha: str
    state: str
    approval_id: str | None = None

    def __post_init__(self) -> None:
        if not REPOSITORY_RE.fullmatch(self.repository):
            raise ValueError("INVALID_REPOSITORY")
        if (
            isinstance(self.pull_request_number, bool)
            or not isinstance(self.pull_request_number, int)
            or self.pull_request_number <= 0
        ):
            raise ValueError("INVALID_PR_NUMBER")
        if not SHA_RE.fullmatch(self.review_head_sha) or self.state not in COUNCIL_STATES:
            raise ValueError("INVALID_COUNCIL_RECORD")
        if self.state == "approved" and (
            not self.approval_id or not ID_RE.fullmatch(self.approval_id)
        ):
            raise ValueError("INVALID_APPROVAL_ID")
        if self.state == "not_required" and self.approval_id is not None:
            raise ValueError("INVALID_APPROVAL_ID")


def council_allows(
    *,
    core_classification: str,
    gate: CouncilGateB1,
    repository: str | None = None,
    pull_request_number: int | None = None,
    review_head_sha: str | None = None,
) -> bool:
    if repository is not None and gate.repository != repository:
        return False
    if pull_request_number is not None and gate.pull_request_number != pull_request_number:
        return False
    if review_head_sha is not None and gate.review_head_sha != review_head_sha:
        return False
    if core_classification == "non_core":
        return gate.state == "not_required"
    return gate.state == "approved"
