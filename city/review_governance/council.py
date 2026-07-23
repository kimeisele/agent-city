"""Minimal exact-head Council gate boundary for shadow evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COUNCIL_STATES = frozenset({"not_required", "pending", "approved", "rejected", "unknown"})


@dataclass(frozen=True)
class CouncilGateB1:
    review_head_sha: str
    state: str
    approval_id: str | None = None

    def __post_init__(self) -> None:
        if not SHA_RE.fullmatch(self.review_head_sha) or self.state not in COUNCIL_STATES:
            raise ValueError("INVALID_COUNCIL_RECORD")


def council_allows(*, core_classification: str, gate: CouncilGateB1) -> bool:
    if core_classification == "non_core":
        return gate.state == "not_required"
    return gate.state == "approved"
