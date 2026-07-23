"""Pure, immutable B1 review-request construction."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from .canonical import canonical_bytes, parse_canonical
from .scope import ScopeError, canonical_scope, scope_digest

REQUEST_SCHEMA = "review-request-b1.1"
REQUEST_FIELDS = frozenset(
    {
        "schema",
        "review_request_id",
        "repository",
        "pull_request_number",
        "reviewed_head_sha",
        "review_request_base_sha",
        "scope_digest",
        "scope_entries",
        "requested_reviewer_identity",
        "requested_at",
        "expires_at",
        "requester_identity",
        "reason",
    }
)
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class RequestError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _text(value: Any, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RequestError("INVALID_TYPE")
    return value


def _id(value: Any) -> str:
    value = _text(value, maximum=128)
    if not ID_RE.fullmatch(value):
        raise RequestError("INVALID_ID")
    return value


def _sha(value: Any) -> str:
    value = _text(value, maximum=40)
    if not SHA_RE.fullmatch(value):
        raise RequestError("INVALID_SHA")
    return value


def _time(value: Any) -> str:
    value = _text(value, maximum=20)
    if not TIME_RE.fullmatch(value):
        raise RequestError("INVALID_TIMESTAMP")
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RequestError("INVALID_TIMESTAMP") from exc
    return value


def _format_time(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0) or value.microsecond:
        raise RequestError("INVALID_TIMESTAMP")
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _closed(value: Mapping[str, Any]) -> None:
    if set(value) - REQUEST_FIELDS:
        raise RequestError("UNKNOWN_FIELD")
    if set(value) != REQUEST_FIELDS:
        raise RequestError("MISSING_FIELD")


class ReviewRequestIdFactory(Protocol):
    def create(self, *, repository: str, pull_request_number: int, reviewed_head_sha: str) -> str:
        """Return a producer-domain unique request ID."""


@dataclass(frozen=True)
class ReviewRequestB1:
    schema: str
    review_request_id: str
    repository: str
    pull_request_number: int
    reviewed_head_sha: str
    review_request_base_sha: str
    scope_digest: str
    scope_entries: tuple[Mapping[str, Any], ...]
    requested_reviewer_identity: str
    requested_at: str
    expires_at: str
    requester_identity: str
    reason: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewRequestB1":
        if not isinstance(value, Mapping):
            raise RequestError("INVALID_TYPE")
        _closed(value)
        if value["schema"] != REQUEST_SCHEMA:
            raise RequestError("INVALID_SCHEMA")
        repository = _text(value["repository"], maximum=255)
        if not REPOSITORY_RE.fullmatch(repository):
            raise RequestError("INVALID_REPOSITORY")
        number = value["pull_request_number"]
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or number <= 0
            or number > 2**31 - 1
        ):
            raise RequestError("INVALID_PR_NUMBER")
        entries = value["scope_entries"]
        if not isinstance(entries, list):
            raise RequestError("INVALID_SCOPE")
        try:
            normalized = canonical_scope(entries)
            digest = scope_digest(normalized)
        except ScopeError as exc:
            raise RequestError(exc.code) from exc
        if digest != value["scope_digest"]:
            raise RequestError("SCOPE_DIGEST_MISMATCH")
        scope_value = tuple(MappingProxyType(dict(entry)) for entry in normalized)
        requested_at = _time(value["requested_at"])
        expires_at = _time(value["expires_at"])
        if expires_at <= requested_at:
            raise RequestError("INVALID_TIMESTAMP")
        return cls(
            REQUEST_SCHEMA,
            _id(value["review_request_id"]),
            repository,
            number,
            _sha(value["reviewed_head_sha"]),
            _sha(value["review_request_base_sha"]),
            _text(value["scope_digest"], maximum=71),
            scope_value,
            _id(value["requested_reviewer_identity"]),
            requested_at,
            expires_at,
            _id(value["requester_identity"]),
            _text(value["reason"], maximum=4096),
        )

    @classmethod
    def from_canonical(cls, raw: bytes | str) -> "ReviewRequestB1":
        try:
            value = parse_canonical(raw)
        except Exception as exc:
            raise RequestError(getattr(exc, "code", "INVALID_SCHEMA")) from exc
        return cls.from_mapping(value)

    @property
    def reviewed_files(self) -> tuple[str, ...]:
        return tuple(entry["path"] for entry in self.scope_entries)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "review_request_id": self.review_request_id,
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "reviewed_head_sha": self.reviewed_head_sha,
            "review_request_base_sha": self.review_request_base_sha,
            "scope_digest": self.scope_digest,
            "scope_entries": [dict(entry) for entry in self.scope_entries],
            "requested_reviewer_identity": self.requested_reviewer_identity,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "requester_identity": self.requester_identity,
            "reason": self.reason,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_mapping())


def build_review_request(
    *,
    repository: str,
    pull_request_number: int,
    reviewed_head_sha: str,
    review_request_base_sha: str,
    scope_entries: Sequence[Mapping[str, Any]],
    requested_reviewer_identity: str,
    requester_identity: str,
    requested_at: dt.datetime,
    expires_at: dt.datetime,
    reason: str,
    id_factory: ReviewRequestIdFactory,
) -> ReviewRequestB1:
    """Build a request from resolved inputs without I/O or ambient inference."""

    if not callable(getattr(id_factory, "create", None)):
        raise RequestError("MISSING_ID_FACTORY")
    try:
        normalized = canonical_scope(scope_entries)
        digest = scope_digest(normalized)
    except ScopeError as exc:
        raise RequestError(exc.code) from exc
    if not normalized:
        raise RequestError("INVALID_SCOPE")
    request = ReviewRequestB1(
        REQUEST_SCHEMA,
        _id(
            id_factory.create(
                repository=repository,
                pull_request_number=pull_request_number,
                reviewed_head_sha=reviewed_head_sha,
            )
        ),
        repository,
        pull_request_number,
        reviewed_head_sha,
        review_request_base_sha,
        digest,
        normalized,
        requested_reviewer_identity,
        _format_time(requested_at),
        _format_time(expires_at),
        requester_identity,
        reason,
    )
    return ReviewRequestB1.from_mapping(request.to_mapping())
