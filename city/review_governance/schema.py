"""Closed B1 records.  These classes are immutable after construction."""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import re
from dataclasses import dataclass
import unicodedata
from typing import Any, Literal, Mapping, Protocol

from .canonical import canonical_bytes, parse_canonical, verdict_signature_input

SCHEMA = "review-verdict-b1.1"
READINESS_SCHEMA = "merge-readiness-evaluation-b1.1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

VERDICT_FIELDS = frozenset(
    {
        "schema",
        "verdict_id",
        "repository",
        "pull_request_number",
        "review_request_id",
        "reviewed_head_sha",
        "review_request_base_sha",
        "scope_digest",
        "reviewed_files",
        "core_classification",
        "decision",
        "reason",
        "evidence_refs",
        "reviewer_identity",
        "reviewer_key_id",
        "issued_at",
        "expires_at",
        "signature",
    }
)
EVIDENCE_FIELDS = frozenset({"kind", "sha", "provider", "name", "evidence_digest"})
CHECK_RESULT_FIELDS = frozenset({"name", "head_sha", "conclusion", "run_id"})
READINESS_FIELDS = frozenset(
    {
        "schema",
        "evaluation_id",
        "verdict_id",
        "repository",
        "pull_request_number",
        "reviewed_head_sha",
        "validated_current_base_sha",
        "integration_check_sha",
        "required_check_results",
        "base_drift_classification",
        "scope_overlap_result",
        "core_gate_state",
        "council_state",
        "merge_expected_head_sha",
        "readiness_state",
        "evaluated_at",
    }
)
ENUMS = {
    "core_classification": {"core", "non_core", "unknown"},
    "decision": {"approve", "request_changes", "reject"},
}


class SchemaError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


VALIDATION_STATES = frozenset({"valid", "rejected", "stale", "blocked"})
EVIDENCE_STATES = frozenset(
    {"structurally_valid", "externally_verified", "unavailable", "mismatched"}
)


def _str(value: Any, field: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise SchemaError("INVALID_TYPE")
    return value


def _id(value: Any, field: str) -> str:
    value = _str(value, field, max_len=128)
    if not ID_RE.fullmatch(value):
        raise SchemaError("INVALID_TYPE")
    return value


def _sha(value: Any) -> str:
    value = _str(value, "sha", max_len=40)
    if not SHA_RE.fullmatch(value):
        raise SchemaError("INVALID_SHA")
    return value


def _digest(value: Any) -> str:
    value = _str(value, "digest", max_len=71)
    if not HASH_RE.fullmatch(value):
        raise SchemaError("INVALID_TYPE")
    return value


def _repo_path(value: Any) -> str:
    value = _str(value, "reviewed_files", max_len=1024)
    if unicodedata.normalize("NFC", value) != value:
        raise SchemaError("INVALID_SCOPE")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise SchemaError("INVALID_SCOPE")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SchemaError("INVALID_SCOPE")
    return value


def _time(value: Any) -> str:
    value = _str(value, "timestamp", max_len=20)
    if not TIME_RE.fullmatch(value):
        raise SchemaError("INVALID_TIMESTAMP")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise SchemaError("INVALID_TIMESTAMP") from exc
    return value


def _closed(value: Mapping[str, Any], fields: frozenset[str]) -> None:
    unknown = set(value) - fields
    if unknown:
        raise SchemaError("UNKNOWN_FIELD")
    if set(value) != fields:
        raise SchemaError("MISSING_FIELD")


@dataclass(frozen=True)
class EvidenceRefB1:
    kind: str
    sha: str
    provider: str
    name: str
    evidence_digest: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRefB1":
        if not isinstance(value, Mapping):
            raise SchemaError("INVALID_TYPE")
        _closed(value, EVIDENCE_FIELDS)
        kind = _str(value["kind"], "kind", max_len=64)
        if kind != "head_security_evidence":
            raise SchemaError("INVALID_ENUM")
        provider = _str(value["provider"], "provider", max_len=32)
        if provider not in {"reviewer", "github_check", "github_status"}:
            raise SchemaError("INVALID_ENUM")
        return cls(
            kind,
            _sha(value["sha"]),
            provider,
            _str(value["name"], "name", max_len=128),
            _digest(value["evidence_digest"]),
        )

    def to_mapping(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ReviewVerdictB1:
    schema: str
    verdict_id: str
    repository: str
    pull_request_number: int
    review_request_id: str
    reviewed_head_sha: str
    review_request_base_sha: str
    scope_digest: str
    reviewed_files: tuple[str, ...]
    core_classification: str
    decision: str
    reason: str
    evidence_refs: tuple[EvidenceRefB1, ...]
    reviewer_identity: str
    reviewer_key_id: str
    issued_at: str
    expires_at: str
    signature: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewVerdictB1":
        if not isinstance(value, Mapping):
            raise SchemaError("INVALID_TYPE")
        _closed(value, VERDICT_FIELDS)
        if value["schema"] != SCHEMA:
            raise SchemaError("INVALID_SCHEMA")
        repository = _str(value["repository"], "repository", max_len=255)
        if not REPOSITORY_RE.fullmatch(repository):
            raise SchemaError("INVALID_REPOSITORY")
        number = value["pull_request_number"]
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or number <= 0
            or number > 2**31 - 1
        ):
            raise SchemaError("INVALID_PR_NUMBER")
        reviewed_files = value["reviewed_files"]
        if not isinstance(reviewed_files, list) or not reviewed_files or len(reviewed_files) > 2048:
            raise SchemaError("INVALID_SCOPE")
        reviewed_files = [_repo_path(path) for path in reviewed_files]
        if len(set(reviewed_files)) != len(reviewed_files):
            raise SchemaError("INVALID_SCOPE")
        core = _str(value["core_classification"], "core_classification", max_len=16)
        decision = _str(value["decision"], "decision", max_len=32)
        if core not in ENUMS["core_classification"] or decision not in ENUMS["decision"]:
            raise SchemaError("INVALID_ENUM")
        reason = _str(value["reason"], "reason", max_len=4096)
        refs = value["evidence_refs"]
        if not isinstance(refs, list) or not refs or len(refs) > 32:
            raise SchemaError("INVALID_TYPE")
        evidence = tuple(EvidenceRefB1.from_mapping(ref) for ref in refs)
        identities = [(ref.kind, ref.provider, ref.name) for ref in evidence]
        if len(set(identities)) != len(identities):
            raise SchemaError("INVALID_TYPE")
        head = _sha(value["reviewed_head_sha"])
        if any(ref.sha != head for ref in evidence):
            raise SchemaError("EVIDENCE_SHA_MISMATCH")
        issued, expires = _time(value["issued_at"]), _time(value["expires_at"])
        if expires <= issued:
            raise SchemaError("INVALID_TIMESTAMP")
        signature = _str(value["signature"], "signature", max_len=256)
        try:
            decoded = base64.b64decode(signature, validate=True)
        except Exception as exc:
            raise SchemaError("INVALID_SIGNATURE") from exc
        if len(decoded) != 64:
            raise SchemaError("INVALID_SIGNATURE")
        return cls(
            SCHEMA,
            _id(value["verdict_id"], "verdict_id"),
            repository,
            number,
            _id(value["review_request_id"], "review_request_id"),
            head,
            _sha(value["review_request_base_sha"]),
            _digest(value["scope_digest"]),
            tuple(reviewed_files),
            core,
            decision,
            reason,
            evidence,
            _id(value["reviewer_identity"], "reviewer_identity"),
            _id(value["reviewer_key_id"], "reviewer_key_id"),
            issued,
            expires,
            signature,
        )

    @classmethod
    def from_canonical(cls, raw: bytes | str) -> "ReviewVerdictB1":
        try:
            value = parse_canonical(raw)
        except Exception as exc:
            raise SchemaError(getattr(exc, "code", "INVALID_SCHEMA")) from exc
        return cls.from_mapping(value)

    def to_mapping(self, *, include_signature: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema": self.schema,
            "verdict_id": self.verdict_id,
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "review_request_id": self.review_request_id,
            "reviewed_head_sha": self.reviewed_head_sha,
            "review_request_base_sha": self.review_request_base_sha,
            "scope_digest": self.scope_digest,
            "reviewed_files": list(self.reviewed_files),
            "core_classification": self.core_classification,
            "decision": self.decision,
            "reason": self.reason,
            "evidence_refs": [ref.to_mapping() for ref in self.evidence_refs],
            "reviewer_identity": self.reviewer_identity,
            "reviewer_key_id": self.reviewer_key_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }
        if include_signature:
            value["signature"] = self.signature
        return value

    def unsigned_bytes(self) -> bytes:
        return canonical_bytes(self.to_mapping(include_signature=False))

    def signature_input(self) -> bytes:
        return verdict_signature_input(self.to_mapping(include_signature=False))

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_mapping())


@dataclass(frozen=True)
class MergeReadinessEvaluationB1:
    schema: str
    evaluation_id: str
    verdict_id: str
    repository: str
    pull_request_number: int
    reviewed_head_sha: str
    validated_current_base_sha: str
    integration_check_sha: str
    required_check_results: tuple[Mapping[str, Any], ...]
    base_drift_classification: str
    scope_overlap_result: str
    core_gate_state: str
    council_state: str
    merge_expected_head_sha: str
    readiness_state: str
    evaluated_at: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MergeReadinessEvaluationB1":
        if not isinstance(value, Mapping):
            raise SchemaError("INVALID_TYPE")
        _closed(value, READINESS_FIELDS)
        if value["schema"] != READINESS_SCHEMA:
            raise SchemaError("INVALID_SCHEMA")
        number = value["pull_request_number"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise SchemaError("INVALID_PR_NUMBER")
        head = _sha(value["reviewed_head_sha"])
        if _sha(value["merge_expected_head_sha"]) != head:
            raise SchemaError("INVALID_SHA")
        checks = value["required_check_results"]
        if (
            not isinstance(checks, list)
            or len(checks) > 64
            or any(not isinstance(item, Mapping) for item in checks)
        ):
            raise SchemaError("INVALID_TYPE")
        normalized_checks: list[dict[str, Any]] = []
        for check in checks:
            _closed(check, CHECK_RESULT_FIELDS)
            conclusion = _str(check["conclusion"], "conclusion", max_len=32)
            if conclusion not in {"success", "failure", "cancelled", "timed_out", "unknown"}:
                raise SchemaError("INVALID_ENUM")
            normalized_checks.append(
                {
                    "name": _str(check["name"], "name", max_len=128),
                    "head_sha": _sha(check["head_sha"]),
                    "conclusion": conclusion,
                    "run_id": _str(check["run_id"], "run_id", max_len=128),
                }
            )
        allowed = {
            "base_drift_classification": {
                "none",
                "non_core_non_overlap",
                "core_or_overlap",
                "conflict",
                "unknown",
            },
            "scope_overlap_result": {"none", "overlap", "unknown"},
            "core_gate_state": {"non_core", "core_pending_council", "core_approved", "blocked"},
            "council_state": {"not_required", "pending", "approved", "rejected", "unknown"},
            "readiness_state": {"ready", "invalidated", "blocked"},
        }
        for field, options in allowed.items():
            if value[field] not in options:
                raise SchemaError("INVALID_ENUM")
        repository = _str(value["repository"], "repository", max_len=255)
        if not REPOSITORY_RE.fullmatch(repository):
            raise SchemaError("INVALID_REPOSITORY")
        integration_sha = _sha(value["integration_check_sha"])
        check_names: set[str] = set()
        run_ids: set[str] = set()
        for check in normalized_checks:
            if check["head_sha"] != integration_sha:
                raise SchemaError("INVALID_SHA")
            if check["name"] in check_names or check["run_id"] in run_ids:
                raise SchemaError("INVALID_TYPE")
            check_names.add(check["name"])
            run_ids.add(check["run_id"])
        core_state = value["core_gate_state"]
        council_state = value["council_state"]
        if core_state == "core_approved" and council_state != "approved":
            raise SchemaError("INVALID_ENUM")
        if value["readiness_state"] == "ready":
            if (
                not normalized_checks
                or any(check["conclusion"] != "success" for check in normalized_checks)
                or value["base_drift_classification"] not in {"none", "non_core_non_overlap"}
                or value["scope_overlap_result"] != "none"
                or core_state not in {"non_core", "core_approved"}
                or council_state not in {"not_required", "approved"}
            ):
                raise SchemaError("INVALID_ENUM")
        return cls(
            READINESS_SCHEMA,
            _id(value["evaluation_id"], "evaluation_id"),
            _id(value["verdict_id"], "verdict_id"),
            repository,
            number,
            head,
            _sha(value["validated_current_base_sha"]),
            integration_sha,
            tuple(normalized_checks),
            value["base_drift_classification"],
            value["scope_overlap_result"],
            value["core_gate_state"],
            value["council_state"],
            head,
            value["readiness_state"],
            _time(value["evaluated_at"]),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evaluation_id": self.evaluation_id,
            "verdict_id": self.verdict_id,
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "reviewed_head_sha": self.reviewed_head_sha,
            "validated_current_base_sha": self.validated_current_base_sha,
            "integration_check_sha": self.integration_check_sha,
            "required_check_results": [dict(x) for x in self.required_check_results],
            "base_drift_classification": self.base_drift_classification,
            "scope_overlap_result": self.scope_overlap_result,
            "core_gate_state": self.core_gate_state,
            "council_state": self.council_state,
            "merge_expected_head_sha": self.merge_expected_head_sha,
            "readiness_state": self.readiness_state,
            "evaluated_at": self.evaluated_at,
        }


@dataclass(frozen=True)
class ValidationResult:
    state: Literal["valid", "rejected", "stale", "blocked"]
    error_code: str | None
    message: str
    validated_identity: ReviewVerdictB1 | None = None
    evidence_state: Literal[
        "structurally_valid", "externally_verified", "unavailable", "mismatched"
    ] = "unavailable"
    schema_valid: bool = False
    signature_valid: bool = False

    def __post_init__(self) -> None:
        if (
            self.state not in VALIDATION_STATES
            or self.evidence_state not in EVIDENCE_STATES
            or not isinstance(self.schema_valid, bool)
            or not isinstance(self.signature_valid, bool)
        ):
            raise ValueError("invalid validation result state")


class ReviewerKeyVerifier(Protocol):
    def verify(
        self, reviewer_identity: str, reviewer_key_id: str, payload: bytes, signature: str
    ) -> "VerificationResult": ...


@dataclass(frozen=True)
class VerificationResult:
    state: str
    error_code: str | None = None
