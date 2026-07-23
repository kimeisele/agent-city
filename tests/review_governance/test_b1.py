from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from city.review_governance.canonical import B1_DOMAIN, CanonicalError, canonical_bytes
from city.review_governance.ledger import LedgerError, ShadowLedger
from city.review_governance.scope import ScopeError, scope_digest
from city.review_governance.schema import MergeReadinessEvaluationB1, ReviewVerdictB1, SchemaError
from city.review_governance.validator import (
    DeterministicEvidenceVerifier,
    Ed25519ReviewerKeyVerifier,
    validate_verdict,
)

HEAD = "a" * 40
BASE = "b" * 40
H2 = "c" * 40
KEY_ID = "key_test"
SCOPE = [
    {
        "path": "city/example.py",
        "change_type": "added",
        "previous_path": None,
        "base_blob_sha": None,
        "head_blob_sha": "d" * 40,
    }
]


def _unsigned(*, head: str = HEAD, core: str = "non_core", provider: str = "reviewer") -> dict:
    return {
        "schema": "review-verdict-b1.1",
        "verdict_id": "verdict-1",
        "repository": "kimeisele/agent-city",
        "pull_request_number": 4242,
        "review_request_id": "request-1",
        "reviewed_head_sha": head,
        "review_request_base_sha": BASE,
        "scope_digest": scope_digest(SCOPE),
        "reviewed_files": ["city/example.py"],
        "core_classification": core,
        "decision": "approve",
        "reason": "reviewed",
        "evidence_refs": [
            {
                "kind": "head_security_evidence",
                "sha": head,
                "provider": provider,
                "name": "reviewer-bound",
                "evidence_digest": "sha256:" + "e" * 64,
            }
        ],
        "reviewer_identity": "reviewer-1",
        "reviewer_key_id": KEY_ID,
        "issued_at": "2027-07-22T12:00:00Z",
        "expires_at": "2027-07-23T12:00:00Z",
    }


def _signed(
    *,
    head: str = HEAD,
    core: str = "non_core",
    provider: str = "reviewer",
    key: Ed25519PrivateKey | None = None,
) -> tuple[dict, Ed25519PrivateKey]:
    key = key or Ed25519PrivateKey.generate()
    value = _unsigned(head=head, core=core, provider=provider)
    signature = key.sign(B1_DOMAIN + __import__("hashlib").sha256(canonical_bytes(value)).digest())
    value["signature"] = base64.b64encode(signature).decode()
    return value, key


def _validator(value: dict, key: Ed25519PrivateKey):
    return validate_verdict(
        value,
        repository="kimeisele/agent-city",
        verifier=Ed25519ReviewerKeyVerifier(
            {("reviewer-1", KEY_ID): key.public_key().public_bytes_raw()}
        ),
        scope_entries=SCOPE,
        now=datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
    )


def test_valid_verdict_and_record_separation():
    value, key = _signed()
    result = _validator(value, key)
    assert result.state == "blocked"
    assert result.schema_valid is True
    assert result.signature_valid is True
    assert result.evidence_state == "structurally_valid"
    assert result.error_code == "EVIDENCE_UNAVAILABLE"
    assert result.validated_identity is not None
    assert "integration_check_sha" not in result.validated_identity.to_mapping()


@pytest.mark.parametrize("field", ["schema", "verdict_id", "reviewed_head_sha", "signature"])
def test_missing_security_fields_rejected(field):
    value, _ = _signed()
    del value[field]
    with pytest.raises(SchemaError):
        ReviewVerdictB1.from_mapping(value)


def test_unknown_and_duplicate_keys_rejected():
    value, _ = _signed()
    value["extra"] = True
    with pytest.raises(SchemaError, match="UNKNOWN_FIELD"):
        ReviewVerdictB1.from_mapping(value)
    raw = b'{"schema":"review-verdict-b1.1","schema":"review-verdict-b1.1"}'
    with pytest.raises(CanonicalError, match="DUPLICATE_KEY"):
        from city.review_governance.canonical import parse_canonical

        parse_canonical(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pull_request_number", "4242"),
        ("reviewed_head_sha", "bad"),
        ("core_classification", "danger"),
        ("decision", "maybe"),
        ("reviewed_files", ["../secret"]),
    ],
)
def test_invalid_fields_rejected(field, value):
    data, _ = _signed()
    data[field] = value
    with pytest.raises(SchemaError):
        ReviewVerdictB1.from_mapping(data)


def test_evidence_sha_binding_and_self_reference_not_external_proof():
    data, key = _signed()
    data["evidence_refs"][0]["sha"] = H2
    with pytest.raises(SchemaError, match="EVIDENCE_SHA_MISMATCH"):
        ReviewVerdictB1.from_mapping(data)
    result = _validator(_signed(key=key)[0], key)
    assert result.state == "blocked"
    assert result.evidence_state == "structurally_valid"


def test_unknown_reviewer_key_fails_closed():
    data, _ = _signed()
    result = validate_verdict(
        data, repository="kimeisele/agent-city", verifier=Ed25519ReviewerKeyVerifier({})
    )
    assert result.state == "blocked"
    assert result.error_code == "UNKNOWN_REVIEWER_KEY"


def test_unavailable_github_evidence_is_blocked():
    value, key = _signed(provider="github_status")
    result = _validator(value, key)
    assert result.state == "blocked"
    assert result.error_code == "EVIDENCE_UNAVAILABLE"
    assert result.evidence_state == "unavailable"


def test_deterministic_independent_evidence_can_validate():
    value, key = _signed(provider="github_status")
    reference = value["evidence_refs"][0]
    evidence_verifier = DeterministicEvidenceVerifier(
        {
            (
                reference["kind"],
                reference["sha"],
                reference["provider"],
                reference["name"],
                reference["evidence_digest"],
            )
        }
    )
    result = validate_verdict(
        value,
        repository="kimeisele/agent-city",
        verifier=Ed25519ReviewerKeyVerifier(
            {("reviewer-1", KEY_ID): key.public_key().public_bytes_raw()}
        ),
        evidence_verifier=evidence_verifier,
        scope_entries=SCOPE,
    )
    assert result.state == "valid"
    assert result.evidence_state == "externally_verified"
    assert result.signature_valid is True


def test_independent_evidence_mismatch_is_rejected():
    value, key = _signed(provider="github_status")
    evidence_verifier = DeterministicEvidenceVerifier(set())
    result = validate_verdict(
        value,
        repository="kimeisele/agent-city",
        verifier=Ed25519ReviewerKeyVerifier(
            {("reviewer-1", KEY_ID): key.public_key().public_bytes_raw()}
        ),
        evidence_verifier=evidence_verifier,
        scope_entries=SCOPE,
    )
    assert result.state == "rejected"
    assert result.error_code == "EVIDENCE_SHA_MISMATCH"
    assert result.evidence_state == "mismatched"


def test_scope_digest_order_rename_and_blob_changes():
    assert scope_digest(SCOPE) == scope_digest(list(reversed(SCOPE)))
    renamed = [
        dict(
            SCOPE[0],
            change_type="renamed",
            previous_path="city/old.py",
            base_blob_sha="1" * 40,
        )
    ]
    assert scope_digest(SCOPE) != scope_digest(renamed)
    changed = [dict(SCOPE[0], head_blob_sha="f" * 40)]
    assert scope_digest(SCOPE) != scope_digest(changed)
    with pytest.raises(ScopeError):
        scope_digest([dict(SCOPE[0], path="../bad")])


@pytest.mark.parametrize(
    "entry",
    [
        {
            "path": "a",
            "change_type": "added",
            "previous_path": None,
            "base_blob_sha": None,
            "head_blob_sha": None,
        },
        {
            "path": "a",
            "change_type": "added",
            "previous_path": None,
            "base_blob_sha": "1" * 40,
            "head_blob_sha": "2" * 40,
        },
        {
            "path": "a",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": None,
            "head_blob_sha": "2" * 40,
        },
        {
            "path": "a",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": "1" * 40,
            "head_blob_sha": None,
        },
        {
            "path": "a",
            "change_type": "deleted",
            "previous_path": None,
            "base_blob_sha": None,
            "head_blob_sha": None,
        },
        {
            "path": "a",
            "change_type": "deleted",
            "previous_path": None,
            "base_blob_sha": "1" * 40,
            "head_blob_sha": "2" * 40,
        },
        {
            "path": "a",
            "change_type": "renamed",
            "previous_path": None,
            "base_blob_sha": "1" * 40,
            "head_blob_sha": "2" * 40,
        },
        {
            "path": "a",
            "change_type": "renamed",
            "previous_path": "old",
            "base_blob_sha": None,
            "head_blob_sha": "2" * 40,
        },
        {
            "path": "a",
            "change_type": "copied",
            "previous_path": "a",
            "base_blob_sha": "1" * 40,
            "head_blob_sha": "2" * 40,
        },
    ],
)
def test_scope_blob_matrix_rejects_missing_or_invalid_identity(entry):
    with pytest.raises(ScopeError):
        scope_digest([entry])


def test_scope_matrix_valid_examples_and_required_blob_digest_changes():
    entries = [
        {
            "path": "new",
            "change_type": "added",
            "previous_path": None,
            "base_blob_sha": None,
            "head_blob_sha": "1" * 40,
        },
        {
            "path": "same",
            "change_type": "modified",
            "previous_path": None,
            "base_blob_sha": "2" * 40,
            "head_blob_sha": "3" * 40,
        },
        {
            "path": "gone",
            "change_type": "deleted",
            "previous_path": None,
            "base_blob_sha": "4" * 40,
            "head_blob_sha": None,
        },
        {
            "path": "new-name",
            "change_type": "renamed",
            "previous_path": "old-name",
            "base_blob_sha": "5" * 40,
            "head_blob_sha": "6" * 40,
        },
        {
            "path": "copy",
            "change_type": "copied",
            "previous_path": "source",
            "base_blob_sha": "7" * 40,
            "head_blob_sha": "8" * 40,
        },
    ]
    first = scope_digest(entries)
    assert first == scope_digest(list(reversed(entries)))
    assert first != scope_digest(
        [dict(entries[1], head_blob_sha="9" * 40)] + entries[0:1] + entries[2:]
    )


def test_scope_rejects_duplicate_final_and_ambiguous_source_paths():
    entry = {
        "path": "a",
        "change_type": "added",
        "previous_path": None,
        "base_blob_sha": None,
        "head_blob_sha": "1" * 40,
    }
    with pytest.raises(ScopeError):
        scope_digest([entry, dict(entry, head_blob_sha="2" * 40)])
    rename = {
        "path": "b",
        "change_type": "renamed",
        "previous_path": "old",
        "base_blob_sha": "1" * 40,
        "head_blob_sha": "2" * 40,
    }
    copy = {
        "path": "c",
        "change_type": "copied",
        "previous_path": "old",
        "base_blob_sha": "1" * 40,
        "head_blob_sha": "3" * 40,
    }
    with pytest.raises(ScopeError):
        scope_digest([rename, copy])


def test_canonical_field_order_and_signature_exclusion():
    value, _ = _signed()
    reordered = {key: value[key] for key in reversed(list(value))}
    assert canonical_bytes(value) == canonical_bytes(reordered)
    record = ReviewVerdictB1.from_mapping(value)
    assert record.unsigned_bytes() != record.canonical_bytes()
    assert record.signature_input().startswith(B1_DOMAIN)


def test_core_classification_consumer_cannot_lower_severity():
    value, key = _signed(core="core", provider="github_status")
    reference = value["evidence_refs"][0]
    evidence_verifier = DeterministicEvidenceVerifier(
        {
            (
                reference["kind"],
                reference["sha"],
                reference["provider"],
                reference["name"],
                reference["evidence_digest"],
            )
        }
    )
    result = validate_verdict(
        value,
        repository="kimeisele/agent-city",
        verifier=Ed25519ReviewerKeyVerifier(
            {("reviewer-1", KEY_ID): key.public_key().public_bytes_raw()}
        ),
        evidence_verifier=evidence_verifier,
        scope_entries=SCOPE,
    )
    assert result.state == "valid"
    value, key = _signed(core="non_core", provider="github_status")
    reference = value["evidence_refs"][0]
    evidence_verifier = DeterministicEvidenceVerifier(
        {
            (
                reference["kind"],
                reference["sha"],
                reference["provider"],
                reference["name"],
                reference["evidence_digest"],
            )
        }
    )
    result = validate_verdict(
        value,
        repository="kimeisele/agent-city",
        verifier=Ed25519ReviewerKeyVerifier(
            {("reviewer-1", KEY_ID): key.public_key().public_bytes_raw()}
        ),
        evidence_verifier=evidence_verifier,
        scope_entries=SCOPE,
        consumer_core="core",
    )
    assert result.state == "blocked"
    assert result.error_code == "CORE_CLASSIFICATION_CONFLICT"


def test_readiness_closed_and_expected_head_invariant():
    value = {
        "schema": "merge-readiness-evaluation-b1.1",
        "evaluation_id": "eval-1",
        "verdict_id": "verdict-1",
        "repository": "kimeisele/agent-city",
        "pull_request_number": 4242,
        "reviewed_head_sha": HEAD,
        "validated_current_base_sha": BASE,
        "integration_check_sha": H2,
        "required_check_results": [],
        "base_drift_classification": "none",
        "scope_overlap_result": "none",
        "core_gate_state": "non_core",
        "council_state": "not_required",
        "merge_expected_head_sha": HEAD,
        "readiness_state": "ready",
        "evaluated_at": "2026-07-22T13:00:00Z",
    }
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(value)
    value["required_check_results"] = [
        {
            "name": "review-governance/merge-result",
            "head_sha": H2,
            "conclusion": "success",
            "run_id": "run-1",
        }
    ]
    record = MergeReadinessEvaluationB1.from_mapping(value)
    assert record.to_mapping()["integration_check_sha"] == H2
    value["merge_expected_head_sha"] = H2
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(value)


def _readiness(**overrides):
    value = {
        "schema": "merge-readiness-evaluation-b1.1",
        "evaluation_id": "eval-1",
        "verdict_id": "verdict-1",
        "repository": "kimeisele/agent-city",
        "pull_request_number": 4242,
        "reviewed_head_sha": HEAD,
        "validated_current_base_sha": BASE,
        "integration_check_sha": H2,
        "required_check_results": [
            {
                "name": "review-governance/merge-result",
                "head_sha": H2,
                "conclusion": "success",
                "run_id": "run-1",
            }
        ],
        "base_drift_classification": "none",
        "scope_overlap_result": "none",
        "core_gate_state": "non_core",
        "council_state": "not_required",
        "merge_expected_head_sha": HEAD,
        "readiness_state": "ready",
        "evaluated_at": "2026-07-22T13:00:00Z",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    "overrides",
    [
        {"required_check_results": []},
        {
            "required_check_results": [
                {"name": "x", "head_sha": H2, "conclusion": "failure", "run_id": "r"}
            ]
        },
        {
            "required_check_results": [
                {"name": "x", "head_sha": BASE, "conclusion": "success", "run_id": "r"}
            ]
        },
        {"base_drift_classification": "conflict"},
        {"base_drift_classification": "unknown"},
        {"scope_overlap_result": "overlap"},
        {"scope_overlap_result": "unknown"},
        {"council_state": "pending"},
        {"council_state": "rejected"},
        {"council_state": "unknown"},
        {"core_gate_state": "core_approved", "council_state": "pending"},
    ],
)
def test_ready_requires_all_readiness_invariants(overrides):
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(_readiness(**overrides))


def test_valid_non_core_and_council_approved_ready_records():
    assert MergeReadinessEvaluationB1.from_mapping(_readiness()).readiness_state == "ready"
    core = _readiness(core_gate_state="core_approved", council_state="approved")
    assert MergeReadinessEvaluationB1.from_mapping(core).readiness_state == "ready"


def test_blocked_record_preserves_failed_checks_and_merged_states_are_rejected():
    blocked = _readiness(
        readiness_state="blocked",
        required_check_results=[
            {
                "name": "review-governance/merge-result",
                "head_sha": H2,
                "conclusion": "failure",
                "run_id": "run-failed",
            }
        ],
    )
    assert MergeReadinessEvaluationB1.from_mapping(blocked).readiness_state == "blocked"
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(_readiness(readiness_state="merged"))
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(_readiness(readiness_state="external_merge"))


def test_duplicate_check_name_or_run_id_rejected():
    checks = [
        {"name": "same", "head_sha": H2, "conclusion": "success", "run_id": "run-1"},
        {"name": "same", "head_sha": H2, "conclusion": "success", "run_id": "run-2"},
    ]
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(_readiness(required_check_results=checks))
    checks[1]["name"], checks[1]["run_id"] = "other", "run-1"
    with pytest.raises(SchemaError):
        MergeReadinessEvaluationB1.from_mapping(_readiness(required_check_results=checks))


def test_verdict_is_not_rewritten_when_readiness_is_superseded(tmp_path):
    verdict, _ = _signed()
    verdict_bytes = ReviewVerdictB1.from_mapping(verdict).canonical_bytes()
    ledger = ShadowLedger(tmp_path / "ledger.jsonl")
    ledger.append("review_verdict_validated", "v1", {"reviewed_head_sha": HEAD})
    ledger.append("merge_readiness_evaluated", "r1", {"base": BASE, "integration": "m1"})
    ledger.append("merge_readiness_invalidated", "r1-invalidated", {"base": BASE})
    ledger.append("merge_readiness_evaluated", "r2", {"base": H2, "integration": "m2"})
    assert ReviewVerdictB1.from_canonical(verdict_bytes).canonical_bytes() == verdict_bytes
    assert [event["event_id"] for event in ledger.read()] == ["v1", "r1", "r1-invalidated", "r2"]


def test_shadow_ledger_order_corruption_duplicate_and_supersession(tmp_path):
    ledger = ShadowLedger(tmp_path / "ledger.jsonl")
    first = ledger.append("review_verdict_validated", "event-1", {"verdict_id": "verdict-1"})
    second = ledger.append(
        "merge_readiness_evaluated", "event-2", {"evaluation_id": "r1", "base": BASE}
    )
    ledger.append("merge_readiness_invalidated", "event-3", {"evaluation_id": "r1"})
    assert [event["sequence"] for event in ledger.read()] == [1, 2, 3]
    assert first["event_digest"] == second["previous_digest"]
    with pytest.raises(LedgerError, match="DUPLICATE_EVENT_ID"):
        ledger.append("review_verdict_received", "event-1", {})
    raw = (tmp_path / "ledger.jsonl").read_bytes()
    (tmp_path / "ledger.jsonl").write_bytes(raw.replace(b'"r1"', b'"tampered"', 1))
    with pytest.raises(LedgerError, match="LEDGER_CORRUPTION"):
        ledger.read()


def test_ledger_partial_tail_fails_closed(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = ShadowLedger(path)
    ledger.append("review_verdict_received", "event-1", {})
    path.write_bytes(path.read_bytes() + b'{"partial"')
    with pytest.raises(LedgerError, match="LEDGER_CORRUPTION"):
        ledger.read()


def test_ledger_rejects_non_positive_size_limit(tmp_path):
    with pytest.raises(LedgerError, match="INVALID_MAX_BYTES"):
        ShadowLedger(tmp_path / "ledger.jsonl", max_bytes=0)


def test_import_is_side_effect_free():
    import sys

    assert "city.runtime" not in sys.modules
