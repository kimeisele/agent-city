from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from city.review_governance.artifacts import ArtifactError, read_artifacts, write_artifacts
from city.review_governance.canonical import canonical_bytes
from city.review_governance.emitter import EmitterError, emit_verdict
from city.review_governance.request import RequestError, ReviewRequestB1, build_review_request
from city.review_governance.schema import ReviewVerdictB1
from city.review_governance.signer import Ed25519ReviewerSigner, SignerError
from city.review_governance.scope import scope_digest
from city.review_governance.validator import (
    DeterministicEvidenceVerifier,
    Ed25519ReviewerKeyVerifier,
    validate_verdict,
)

HEAD = "a" * 40
BASE = "b" * 40
SCOPE = [
    {
        "path": "city/example.py",
        "change_type": "modified",
        "previous_path": None,
        "base_blob_sha": "1" * 40,
        "head_blob_sha": "2" * 40,
    }
]


class IDs:
    def __init__(self, value: str = "request-1"):
        self.value = value

    def create(self, **_kwargs) -> str:
        return self.value


def request(**overrides) -> ReviewRequestB1:
    values = {
        "repository": "kimeisele/agent-city",
        "pull_request_number": 4242,
        "reviewed_head_sha": HEAD,
        "review_request_base_sha": BASE,
        "scope_entries": SCOPE,
        "requested_reviewer_identity": "reviewer-1",
        "requester_identity": "agent-city",
        "requested_at": datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
        "expires_at": datetime(2026, 7, 24, 12, tzinfo=timezone.utc),
        "reason": "please review",
        "id_factory": IDs(),
    }
    values.update(overrides)
    return build_review_request(**values)


def signer(key: Ed25519PrivateKey | None = None) -> tuple[Ed25519ReviewerSigner, Ed25519PrivateKey]:
    key = key or Ed25519PrivateKey.generate()
    return Ed25519ReviewerSigner(
        reviewer_identity="reviewer-1", reviewer_key_id="key_test", private_key=key
    ), key


def evidence(request_record: ReviewRequestB1, provider: str = "reviewer") -> dict:
    return {
        "kind": "head_security_evidence",
        "sha": request_record.reviewed_head_sha,
        "provider": provider,
        "name": "head-review",
        "evidence_digest": "sha256:" + "e" * 64,
    }


def emit(
    request_record: ReviewRequestB1,
    *,
    provider: str = "reviewer",
    key=None,
    verdict_id: str = "verdict-1",
    **kwargs,
):
    signing, key = signer(key)
    refs = kwargs.pop("evidence_refs", [evidence(request_record, provider)])
    return emit_verdict(
        request_record,
        decision="approve",
        review_reason="reviewed",
        producer_core_classification="non_core",
        evidence_refs=refs,
        reviewer_identity="reviewer-1",
        reviewer_key_id="key_test",
        signer=signing,
        issued_at=datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
        expires_at=datetime(2026, 7, 23, 13, tzinfo=timezone.utc),
        verdict_id=verdict_id,
        **kwargs,
    ), key


def test_request_round_trip_and_canonical_field_order():
    record = request()
    restored = ReviewRequestB1.from_canonical(record.canonical_bytes())
    assert restored == record
    mapping = record.to_mapping()
    reordered = {key: mapping[key] for key in reversed(list(mapping))}
    assert canonical_bytes(mapping) == canonical_bytes(reordered)


@pytest.mark.parametrize(
    "field", ["schema", "review_request_id", "reviewed_head_sha", "scope_entries"]
)
def test_request_missing_fields_reject(field):
    value = request().to_mapping()
    del value[field]
    with pytest.raises(RequestError):
        ReviewRequestB1.from_mapping(value)


def test_request_unknown_duplicate_and_invalid_identity_reject():
    value = request().to_mapping()
    value["unknown"] = True
    with pytest.raises(RequestError, match="UNKNOWN_FIELD"):
        ReviewRequestB1.from_mapping(value)
    raw = b'{"schema":"review-request-b1.1","schema":"review-request-b1.1"}'
    with pytest.raises(RequestError, match="DUPLICATE_KEY"):
        ReviewRequestB1.from_canonical(raw)
    value = request().to_mapping()
    value["repository"] = "not-a-repository"
    with pytest.raises(RequestError, match="INVALID_REPOSITORY"):
        ReviewRequestB1.from_mapping(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pull_request_number", 0),
        ("reviewed_head_sha", "bad"),
        ("review_request_base_sha", "bad"),
        ("requested_at", "2026-07-22T12:00:00+00:00"),
        ("expires_at", "2026-07-21T12:00:00Z"),
    ],
)
def test_request_invalid_pr_sha_or_time_reject(field, value):
    data = request().to_mapping()
    data[field] = value
    with pytest.raises(RequestError):
        ReviewRequestB1.from_mapping(data)


def test_request_scope_digest_and_bytes_change_with_scope():
    record = request()
    changed = request(scope_entries=[dict(SCOPE[0], head_blob_sha="3" * 40)])
    assert record.scope_digest != changed.scope_digest
    assert record.canonical_bytes() != changed.canonical_bytes()
    data = record.to_mapping()
    data["scope_digest"] = scope_digest([dict(SCOPE[0], head_blob_sha="3" * 40)])
    with pytest.raises(RequestError, match="SCOPE_DIGEST_MISMATCH"):
        ReviewRequestB1.from_mapping(data)


def test_request_lineage_is_immutable_and_new_ids_are_distinct():
    first = request()
    second = request(id_factory=IDs("request-2"))
    assert first.review_request_id != second.review_request_id
    before = first.canonical_bytes()
    changed = request(reviewed_head_sha="c" * 40)
    assert changed.reviewed_head_sha != first.reviewed_head_sha
    assert first.canonical_bytes() == before


def test_emitter_binds_every_request_identity_and_round_trips():
    record = request()
    (verdict, raw), key = emit(record)
    assert verdict.review_request_id == record.review_request_id
    assert verdict.reviewed_head_sha == record.reviewed_head_sha
    assert verdict.review_request_base_sha == record.review_request_base_sha
    assert verdict.scope_digest == record.scope_digest
    assert raw == verdict.canonical_bytes()
    assert ReviewVerdictB1.from_canonical(raw) == verdict
    verifier = Ed25519ReviewerKeyVerifier(
        {("reviewer-1", "key_test"): key.public_key().public_bytes_raw()}
    )
    result = validate_verdict(verdict.to_mapping(), repository=record.repository, verifier=verifier)
    assert result.state == "blocked"  # reviewer evidence is not independent proof


def test_multiple_verdict_ids_share_request_lineage_and_change_signed_bytes():
    record = request()
    (first, first_raw), _ = emit(record, verdict_id="verdict-1")
    (second, second_raw), _ = emit(record, verdict_id="verdict-2")
    assert first.review_request_id == second.review_request_id == record.review_request_id
    assert first.verdict_id != second.verdict_id
    assert first_raw != second_raw
    assert first.signature_input() != second.signature_input()


def test_verdict_id_boundary_requires_explicit_or_factory_id():
    record = request()
    signing, _ = signer()
    common = dict(
        decision="approve",
        review_reason="reviewed",
        producer_core_classification="non_core",
        evidence_refs=[evidence(record)],
        reviewer_identity="reviewer-1",
        reviewer_key_id="key_test",
        signer=signing,
        issued_at=datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
        expires_at=datetime(2026, 7, 23, 13, tzinfo=timezone.utc),
    )
    with pytest.raises(EmitterError, match="MISSING_OR_AMBIGUOUS_VERDICT_ID"):
        emit_verdict(record, **common)
    with pytest.raises(EmitterError, match="INVALID_VERDICT_ID"):
        emit_verdict(record, verdict_id="bad id", **common)

    class Factory:
        def create(self, **_kwargs):
            return "verdict-from-factory"

    verdict, _ = emit_verdict(record, verdict_id_factory=Factory(), **common)
    assert verdict.verdict_id == "verdict-from-factory"


def test_emitter_copies_request_identities_without_override_surface():
    record = request()
    (verdict, _), _key = emit(record)
    assert verdict.repository == record.repository
    assert verdict.pull_request_number == record.pull_request_number
    assert verdict.reviewed_head_sha == record.reviewed_head_sha
    assert verdict.review_request_base_sha == record.review_request_base_sha
    assert verdict.scope_digest == record.scope_digest


def test_emitter_signer_identity_and_key_mismatch_reject():
    record = request()
    with pytest.raises(EmitterError, match="MISSING_SIGNER"):
        emit_verdict(
            record,
            decision="approve",
            review_reason="x",
            producer_core_classification="non_core",
            evidence_refs=[evidence(record)],
            reviewer_identity="reviewer-1",
            reviewer_key_id="key_test",
            signer=None,
            issued_at=datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
            expires_at=datetime(2026, 7, 23, 13, tzinfo=timezone.utc),
            verdict_id="verdict-missing-signer",
        )
    signing, _ = signer()
    with pytest.raises(EmitterError, match="REVIEWER_IDENTITY_MISMATCH"):
        emit_verdict(
            record,
            decision="approve",
            review_reason="x",
            producer_core_classification="non_core",
            evidence_refs=[evidence(record)],
            reviewer_identity="other",
            reviewer_key_id="key_test",
            signer=signing,
            issued_at=datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
            expires_at=datetime(2026, 7, 23, 13, tzinfo=timezone.utc),
            verdict_id="verdict-other",
        )
    with pytest.raises(SignerError):
        Ed25519ReviewerSigner(reviewer_identity="", reviewer_key_id="key", private_key=None)


def test_emitter_decision_reason_and_evidence_rules():
    record = request()
    with pytest.raises(EmitterError):
        emit(record, evidence_refs=[])
    with pytest.raises(EmitterError, match="DUPLICATE_EVIDENCE"):
        emit(record, evidence_refs=[evidence(record), evidence(record)])
    with pytest.raises(EmitterError, match="EVIDENCE_SHA_MISMATCH"):
        emit(record, evidence_refs=[dict(evidence(record), sha="c" * 40)])
    (approved, _), _ = emit(record)
    changed, _ = emit_verdict(
        record,
        decision="request_changes",
        review_reason="more evidence",
        producer_core_classification="non_core",
        evidence_refs=[evidence(record)],
        reviewer_identity="reviewer-1",
        reviewer_key_id="key_test",
        signer=signer()[0],
        issued_at=datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
        expires_at=datetime(2026, 7, 23, 13, tzinfo=timezone.utc),
        verdict_id="verdict-2",
    )
    assert approved.signature_input() != changed.signature_input()


def test_artifact_writer_is_explicit_atomic_and_no_default_path(tmp_path):
    record = request()
    (verdict, _), _ = emit(record)
    bundle_path = write_artifacts(tmp_path / "artifacts", record, verdict)
    restored_request, restored_verdict = read_artifacts(bundle_path)
    assert restored_request == record
    assert restored_verdict == verdict
    with pytest.raises(ArtifactError, match="ARTIFACT_EXISTS"):
        write_artifacts(tmp_path / "artifacts", record, verdict)
    write_artifacts(tmp_path / "artifacts", record, verdict, overwrite=True)


def test_artifact_bundle_rejects_binding_mismatches_before_writing(tmp_path):
    record = request()
    (verdict, _), _ = emit(record)
    altered = ReviewVerdictB1.from_mapping({**verdict.to_mapping(), "pull_request_number": 7})
    with pytest.raises(ArtifactError, match="ARTIFACT_BINDING_MISMATCH"):
        write_artifacts(tmp_path / "artifacts", record, altered)
    assert not (tmp_path / "artifacts" / "review-artifact-bundle.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository", "other/repo"),
        ("pull_request_number", 7),
        ("reviewed_head_sha", "c" * 40),
        ("review_request_base_sha", "c" * 40),
        ("scope_digest", "sha256:" + "f" * 64),
    ],
)
def test_artifact_bundle_rejects_each_lineage_binding(tmp_path, field, value):
    record = request()
    (verdict, _), _ = emit(record)
    altered = dataclasses.replace(verdict, **{field: value})
    with pytest.raises(ArtifactError, match="ARTIFACT_BINDING_MISMATCH"):
        write_artifacts(tmp_path / field, record, altered)


def test_artifact_bundle_failure_preserves_previous_bytes_and_cleans_temp(tmp_path, monkeypatch):
    record = request()
    (first, _), _ = emit(record, verdict_id="verdict-first")
    path = write_artifacts(tmp_path / "artifacts", record, first)
    before = path.read_bytes()
    (second, _), _ = emit(record, verdict_id="verdict-second")

    def fail_replace(_source, _target):
        raise OSError("injected publication failure")

    monkeypatch.setattr("city.review_governance.artifacts.os.replace", fail_replace)
    with pytest.raises(OSError):
        write_artifacts(tmp_path / "artifacts", record, second, overwrite=True)
    assert path.read_bytes() == before
    assert not list(path.parent.glob("tmp*"))


def test_artifact_bundle_type_and_restrictive_permissions(tmp_path):
    record = request()
    (verdict, _), _ = emit(record)
    with pytest.raises(ArtifactError, match="INVALID_ARTIFACT_TYPE"):
        write_artifacts(tmp_path / "artifacts", record.to_mapping(), verdict)
    path = write_artifacts(tmp_path / "artifacts", record, verdict)
    assert path.stat().st_mode & 0o077 == 0


def test_pure_builder_and_emitter_have_no_subprocess_or_network_side_effects():
    record = request()
    assert record.canonical_bytes()
    verdict, raw = emit(record)[0]
    assert raw == verdict.canonical_bytes()


def test_independent_deterministic_evidence_can_validate_emitted_verdict():
    record = request()
    (verdict, _), key = emit(record, provider="github_status")
    reference = verdict.evidence_refs[0]
    evidence_verifier = DeterministicEvidenceVerifier(
        {
            (
                reference.kind,
                reference.sha,
                reference.provider,
                reference.name,
                reference.evidence_digest,
            )
        }
    )
    verifier = Ed25519ReviewerKeyVerifier(
        {("reviewer-1", "key_test"): key.public_key().public_bytes_raw()}
    )
    result = validate_verdict(
        verdict.to_mapping(),
        repository=record.repository,
        verifier=verifier,
        evidence_verifier=evidence_verifier,
    )
    assert result.state == "valid"
    assert result.evidence_state == "externally_verified"
