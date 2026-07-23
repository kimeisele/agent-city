"""Pure Policy-C base-delta classification and decision functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .scope import ScopeError, canonical_scope

CLASSIFICATIONS = frozenset(
    {"none", "non_core_non_overlap", "core_or_overlap", "conflict", "unknown"}
)


@dataclass(frozen=True)
class BaseDriftEvaluation:
    classification: str
    base_moved: bool
    overlap: str
    core_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.classification not in CLASSIFICATIONS:
            raise ValueError("INVALID_DRIFT_CLASSIFICATION")
        if self.overlap not in {"none", "overlap", "unknown"}:
            raise ValueError("INVALID_DRIFT_OVERLAP")
        if not isinstance(self.base_moved, bool):
            raise ValueError("INVALID_DRIFT_STATE")
        if self.classification == "none" and (
            self.base_moved or self.overlap != "none" or self.core_paths or self.changed_paths
        ):
            raise ValueError("INCONSISTENT_DRIFT")
        if self.classification == "non_core_non_overlap" and (
            not self.base_moved
            or self.overlap != "none"
            or self.core_paths
            or not self.changed_paths
        ):
            raise ValueError("INCONSISTENT_DRIFT")
        if self.classification == "core_or_overlap" and (
            not self.base_moved
            or not self.changed_paths
            or (self.overlap != "overlap" and not self.core_paths)
            or not set(self.core_paths).issubset(self.changed_paths)
        ):
            raise ValueError("INCONSISTENT_DRIFT")
        if self.classification in {"unknown", "conflict"} and not self.base_moved:
            raise ValueError("INCONSISTENT_DRIFT")


@dataclass(frozen=True)
class PolicyCDecision:
    state: str
    reason_code: str
    verdict_usable: bool
    fresh_review_required: bool
    base_drift_classification: str

    def __post_init__(self) -> None:
        if self.state not in {"verdict_usable", "fresh_review_required", "blocked"}:
            raise ValueError("INVALID_POLICY_STATE")
        if self.base_drift_classification not in CLASSIFICATIONS:
            raise ValueError("INVALID_DRIFT_CLASSIFICATION")
        if not isinstance(self.reason_code, str) or not self.reason_code:
            raise ValueError("INVALID_REASON")
        if self.state == "verdict_usable" and not self.verdict_usable:
            raise ValueError("INCONSISTENT_POLICY")
        if self.state == "fresh_review_required" and not self.fresh_review_required:
            raise ValueError("INCONSISTENT_POLICY")
        if self.state == "blocked" and (self.verdict_usable or self.fresh_review_required):
            raise ValueError("INCONSISTENT_POLICY")


def _paths(entries: Iterable[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    for item in entries:
        result.add(item["path"])
        if item.get("previous_path"):
            result.add(item["previous_path"])
    return result


def evaluate_base_drift(
    *,
    request_base_sha: str,
    current_base_sha: str,
    reviewed_scope: Iterable[Mapping[str, Any]],
    base_delta_scope: Iterable[Mapping[str, Any]] | None,
    consumer_core_classifier: Callable[[str], str],
    ancestry_available: bool = True,
) -> BaseDriftEvaluation:
    """Classify only supplied, validated object identities; never fetches Git."""

    if request_base_sha == current_base_sha:
        return BaseDriftEvaluation("none", False, "none", (), ())
    if not ancestry_available or base_delta_scope is None:
        return BaseDriftEvaluation("unknown", True, "unknown", (), (), "BASE_DELTA_UNAVAILABLE")
    try:
        delta = canonical_scope(base_delta_scope)
        reviewed = canonical_scope(reviewed_scope)
    except ScopeError:
        return BaseDriftEvaluation("unknown", True, "unknown", (), (), "INVALID_SCOPE")
    if not delta:
        return BaseDriftEvaluation("unknown", True, "unknown", (), (), "BASE_DELTA_EMPTY")
    changed = _paths(delta)
    reviewed_paths = _paths(reviewed)
    overlap_paths = tuple(sorted(changed & reviewed_paths))
    core_paths: list[str] = []
    for entry in delta:
        for path in (entry["path"], entry.get("previous_path")):
            if path and consumer_core_classifier(path) == "core":
                core_paths.append(path)
            elif path and consumer_core_classifier(path) not in {"core", "non_core"}:
                return BaseDriftEvaluation(
                    "unknown", True, "unknown", (), tuple(sorted(changed)), "CORE_UNKNOWN"
                )
    if overlap_paths or core_paths:
        return BaseDriftEvaluation(
            "core_or_overlap",
            True,
            "overlap" if overlap_paths else "none",
            tuple(sorted(set(core_paths))),
            tuple(sorted(changed)),
        )
    return BaseDriftEvaluation("non_core_non_overlap", True, "none", (), tuple(sorted(changed)))


def evaluate_policy_c(
    *, verdict_valid: bool, drift: BaseDriftEvaluation, integration_ready: bool
) -> PolicyCDecision:
    if drift.classification in {"unknown", "conflict"}:
        return PolicyCDecision(
            "blocked", "BASE_DRIFT_UNCERTAIN", False, False, drift.classification
        )
    if drift.classification == "core_or_overlap":
        return PolicyCDecision(
            "fresh_review_required", "CORE_OR_OVERLAP_BASE_DRIFT", False, True, drift.classification
        )
    if not verdict_valid:
        return PolicyCDecision("blocked", "VERDICT_NOT_USABLE", False, False, drift.classification)
    if not integration_ready:
        return PolicyCDecision(
            "blocked", "INTEGRATION_EVIDENCE_UNAVAILABLE", False, False, drift.classification
        )
    return PolicyCDecision(
        "verdict_usable", "READY_FOR_SHADOW_MERGE", True, False, drift.classification
    )
