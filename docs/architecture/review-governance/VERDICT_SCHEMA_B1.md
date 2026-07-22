# B1 Verdict and Merge-Readiness Records `b1.1`

Status: proposed; implementation not authorized. The signed reviewer judgment and the consumer's mutable merge-readiness evidence are separate closed records.

## A. Signed `ReviewVerdictB1`

The reviewer owns and signs this record. It is immutable after issuance and is bound to the exact reviewed head `H`. It contains no current-base integration result.

Example uses fictional PR number `4242`; it is not a reference to the controlling issue or documentation PR.

```json
{
  "schema": "review-verdict-b1.1",
  "verdict_id": "rv_01HXFICTIONAL",
  "repository": "kimeisele/agent-city",
  "pull_request_number": 4242,
  "review_request_id": "rr_01HXFICTIONAL",
  "reviewed_head_sha": "<H>",
  "review_request_base_sha": "<B_request>",
  "scope_digest": "sha256:<hex>",
  "reviewed_files": ["city/example.py"],
  "core_classification": "core|non_core",
  "decision": "approve|request_changes|reject",
  "reason": "<bounded review reason>",
  "evidence_refs": [
    {
      "kind": "head_security_evidence",
      "sha": "<H>",
      "provider": "reviewer|github_check|github_status",
      "name": "<stable evidence name>",
      "evidence_digest": "sha256:<hex>"
    }
  ],
  "reviewer_identity": "<registry-bound identity>",
  "reviewer_key_id": "<allowlisted key id>",
  "issued_at": "2026-07-22T12:00:00Z",
  "expires_at": "2026-07-22T18:00:00Z",
  "signature": "<canonical envelope signature>"
}
```

`reviewed_files` is the canonical scope projection used to derive `scope_digest`; it is not a free-form display list. `reason` is bounded explanatory text and cannot control dispatch, authority, scope, or merge behavior. `evidence_refs` are immutable references signed as part of the verdict. The consumer must independently validate every reference and its SHA binding.

### Head-security evidence decision

For B1, head-security evidence is an independently verified evidence reference, not a mutable check field inside the verdict and not an assumption that a normal `pull_request` Actions job ran on `H`. The reference must bind to `reviewed_head_sha == H`, a stable evidence name, and a digest. The consumer verifies the reference through the trusted reviewer/key service or GitHub Checks/Statuses read APIs. Unknown, unavailable, or mismatched evidence fails closed.

The normal `pull_request` event naturally exposes `GITHUB_SHA` for the synthetic merge ref, not a raw-head check. GitHub documents that `github.event.pull_request.head.sha` is the raw head and that default checkout tests the merge branch. A later B1-S3 may operationalize a true GitHub check on `H` through a push workflow, explicitly created Check Run, or commit status. Until then, reviewer-bound evidence is the only accepted head-security mechanism. Sources: [workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [check runs](https://docs.github.com/en/rest/checks/runs), and [commit statuses](https://docs.github.com/en/rest/commits/statuses).

### `ReviewVerdictB1` field rules

| Field | Rule |
|---|---|
| `schema` | Exact literal `review-verdict-b1.1`. |
| `verdict_id` | Producer-unique, immutable, and never reused. |
| `repository` | Exact owner/name; must equal the consumer repository. |
| `pull_request_number` | Positive integer resolving in that repository. |
| `review_request_id` | Immutable request lineage identity. |
| `reviewed_head_sha` | Full 40-hex Git SHA `H`; never replaced after issuance. |
| `review_request_base_sha` | Full 40-hex `B_request` observed at request creation. |
| `scope_digest` | SHA-256 over the canonical scope projection. |
| `reviewed_files` | Closed array of normalized repository-relative paths; no duplicates. |
| `core_classification` | Producer assertion; consumer recomputes and cannot lower severity. |
| `decision` | Closed enum. Only `approve` can contribute to merge readiness. |
| `reason` | Bounded display text; never semantic authority. |
| `evidence_refs` | Closed references independently checked against `H`; no mutable current-base result. |
| `reviewer_identity` / `reviewer_key_id` | Must resolve through trusted service or explicit allowlist. |
| `issued_at` / `expires_at` | RFC-3339 UTC; expiry checked at consumption. |
| `signature` | Covers every other canonical field with the B1 domain separator. |

Unknown fields, missing security fields, wrong types, duplicate keys, non-canonical bytes, unknown reviewer keys, or invalid signatures reject. There are no security defaults.

## B. Local `MergeReadinessEvaluationB1`

Agent City's merge-gating authority owns this append-only record. Each base/check change creates a new evaluation; it never rewrites `ReviewVerdictB1`.

```json
{
  "schema": "merge-readiness-evaluation-b1.1",
  "evaluation_id": "mre_01HXFICTIONAL",
  "verdict_id": "rv_01HXFICTIONAL",
  "repository": "kimeisele/agent-city",
  "pull_request_number": 4242,
  "reviewed_head_sha": "<H>",
  "validated_current_base_sha": "<B_current>",
  "integration_check_sha": "<M_current>",
  "required_check_results": [
    {
      "name": "review-governance/merge-result",
      "head_sha": "<M_current>",
      "conclusion": "success",
      "run_id": "<provider run id>"
    }
  ],
  "base_drift_classification": "none|non_core_non_overlap|core_or_overlap|conflict|unknown",
  "scope_overlap_result": "none|overlap|unknown",
  "core_gate_state": "non_core|core_pending_council|core_approved|blocked",
  "council_state": "not_required|pending|approved|rejected|unknown",
  "merge_expected_head_sha": "<H>",
  "readiness_state": "ready|invalidated|blocked|merged|external_merge",
  "evaluated_at": "2026-07-22T13:00:00Z"
}
```

The current-base record may be superseded by a newer evaluation when `B_current`, `M_current`, overlap, council, or required-check evidence changes. `merge_expected_head_sha` must equal `reviewed_head_sha`; it is repeated to make the final merge precondition explicit, not to create a third head identity.

## Ledger events

The append-only ledger records distinct event types rather than one mutable verdict row:

- `review_verdict_received`
- `review_verdict_validated`
- `review_verdict_rejected`
- `review_verdict_stale`
- `merge_readiness_evaluated`
- `merge_readiness_invalidated`
- `council_gate_recorded`
- `merge_completed`
- `external_merge_observed`

A base movement may append `merge_readiness_invalidated` while the original verdict remains `review_verdict_validated`. A head movement appends verdict-stale evidence and invalidates every readiness evaluation tied to the old head. `merge_completed` is emitted only after GitHub returns final squash SHA `S`; an externally performed or break-glass merge uses `external_merge_observed`.

## Canonicalization and signature

The B1 schema reuses the already tested canonical JSON profile only through a pure neutral interface. The baseline probe found `city.federation_v1.canonical_bytes` importable without initializing other Federation/runtime modules. B1-S1 must preserve that property with a side-effect test; it must not copy a subtly different serializer.

The signature input is:

```text
REVIEW-VERDICT-B1.1\0 + SHA256(canonical_json(unsigned_ReviewVerdictB1))
```

Only `ReviewVerdictB1` is reviewer-signed. `MergeReadinessEvaluationB1` is locally authenticated/persisted evidence and is not represented as a new reviewer verdict.

## Validation order

1. Parse closed canonical `ReviewVerdictB1` bytes.
2. Verify reviewer-key provenance and signature.
3. Resolve repository/PR and current head/base.
4. Require current head `== reviewed_head_sha`; otherwise append `review_verdict_stale`.
5. Recompute changed paths, core classification, and scope digest.
6. Independently validate each H-bound `evidence_ref`.
7. Apply Policy C and append a new `MergeReadinessEvaluationB1`.
8. Validate current merge-result evidence against `B_current + H`.
9. Only `PRLifecycleManager` may perform final head revalidation and SHA-bound squash merge.

Any failed or unavailable step blocks merge. No field is defaulted, inferred from a title, or reconstructed from a prior evaluation.
