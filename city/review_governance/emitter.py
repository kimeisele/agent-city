"""Transport-neutral Steward-side ReviewVerdictB1 emission."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable, Mapping, Protocol

from .canonical import canonical_bytes, verdict_signature_input
from .request import ReviewRequestB1
from .schema import EvidenceRefB1, ReviewVerdictB1, SchemaError
from .signer import ReviewerSigner, SignerError


class EmitterError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


VERDICT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class VerdictIdFactory(Protocol):
    def create(
        self,
        *,
        review_request_id: str,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
    ) -> str: ...


def _time(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0) or value.microsecond:
        raise EmitterError("INVALID_TIMESTAMP")
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_verdict(
    request: ReviewRequestB1,
    *,
    decision: str,
    review_reason: str,
    producer_core_classification: str,
    evidence_refs: Iterable[Mapping[str, Any] | EvidenceRefB1],
    reviewer_identity: str,
    reviewer_key_id: str,
    signer: ReviewerSigner,
    issued_at: dt.datetime,
    expires_at: dt.datetime,
    verdict_id_factory: VerdictIdFactory | None = None,
    verdict_id: str | None = None,
) -> tuple[ReviewVerdictB1, bytes]:
    """Construct and sign exactly the request-bound verdict; never merge."""

    if signer is None or not callable(getattr(signer, "sign", None)):
        raise EmitterError("MISSING_SIGNER")
    if (verdict_id_factory is None) == (verdict_id is None):
        raise EmitterError("MISSING_OR_AMBIGUOUS_VERDICT_ID")
    if verdict_id_factory is not None:
        if not callable(getattr(verdict_id_factory, "create", None)):
            raise EmitterError("MISSING_VERDICT_ID_FACTORY")
        verdict_id = verdict_id_factory.create(
            review_request_id=request.review_request_id,
            repository=request.repository,
            pull_request_number=request.pull_request_number,
            reviewed_head_sha=request.reviewed_head_sha,
        )
    if not isinstance(verdict_id, str) or not VERDICT_ID_RE.fullmatch(verdict_id):
        raise EmitterError("INVALID_VERDICT_ID")
    if reviewer_identity != request.requested_reviewer_identity:
        raise EmitterError("REVIEWER_IDENTITY_MISMATCH")
    if reviewer_identity != signer.reviewer_identity or reviewer_key_id != signer.reviewer_key_id:
        raise EmitterError("SIGNER_IDENTITY_MISMATCH")
    refs: list[dict[str, Any]] = []
    for value in evidence_refs:
        try:
            reference = value.to_mapping() if isinstance(value, EvidenceRefB1) else dict(value)
            parsed = EvidenceRefB1.from_mapping(reference)
        except (SchemaError, TypeError, ValueError) as exc:
            raise EmitterError(getattr(exc, "code", "INVALID_EVIDENCE")) from exc
        if parsed.sha != request.reviewed_head_sha:
            raise EmitterError("EVIDENCE_SHA_MISMATCH")
        refs.append(parsed.to_mapping())
    identities = [(ref["kind"], ref["provider"], ref["name"]) for ref in refs]
    if len(identities) != len(set(identities)):
        raise EmitterError("DUPLICATE_EVIDENCE")
    issued = _time(issued_at)
    expires = _time(expires_at)
    if expires <= issued or issued < request.requested_at or expires > request.expires_at:
        raise EmitterError("INVALID_TIMESTAMP")
    unsigned = {
        "schema": "review-verdict-b1.1",
        "verdict_id": verdict_id,
        "repository": request.repository,
        "pull_request_number": request.pull_request_number,
        "review_request_id": request.review_request_id,
        "reviewed_head_sha": request.reviewed_head_sha,
        "review_request_base_sha": request.review_request_base_sha,
        "scope_digest": request.scope_digest,
        "reviewed_files": list(request.reviewed_files),
        "core_classification": producer_core_classification,
        "decision": decision,
        "reason": review_reason,
        "evidence_refs": refs,
        "reviewer_identity": reviewer_identity,
        "reviewer_key_id": reviewer_key_id,
        "issued_at": issued,
        "expires_at": expires,
    }
    try:
        signature = signer.sign(verdict_signature_input(unsigned))
        value = dict(unsigned, signature=signature)
        verdict = ReviewVerdictB1.from_mapping(value)
    except (SchemaError, SignerError, ValueError) as exc:
        raise EmitterError(getattr(exc, "code", "INVALID_VERDICT")) from exc
    return verdict, canonical_bytes(value)
