# B1 Verdict Schema `b1.1`

Status: proposed; implementation not authorized. This is the wire/data contract for B1-S1 planning, not a runtime schema implementation.

## Envelope

The canonical signed envelope is a closed object. Unknown fields, absent required security fields, wrong types, non-canonical JSON, or duplicate keys are rejected. There are no security defaults.

```json
{
  "schema": "review-verdict-b1.1",
  "verdict_id": "rv_...",
  "repository": "kimeisele/agent-city",
  "pull_request_number": 2495,
  "review_request_id": "rr_...",
  "reviewed_head_sha": "<H>",
  "review_request_base_sha": "<B_request>",
  "scope_digest": "sha256:<hex>",
  "core_classification": "core|non_core",
  "decision": "approve|request_changes|reject",
  "reviewer_identity": "<registry-bound identity>",
  "reviewer_key_id": "<allowlisted key id>",
  "issued_at": "2026-07-22T12:00:00Z",
  "expires_at": "2026-07-22T18:00:00Z",
  "head_check": {
    "name": "review-governance/head",
    "head_sha": "<H>",
    "conclusion": "success",
    "run_id": "<provider run id>"
  },
  "integration_check": null,
  "signature": "<canonical envelope signature>"
}
```

`integration_check` is required for a merge-authorizing verdict after current-base validation and has this closed shape:

```json
{
  "name": "review-governance/merge-result",
  "head_sha": "<M_current>",
  "base_sha": "<B_current>",
  "reviewed_head_sha": "<H>",
  "conclusion": "success",
  "run_id": "<provider run id>"
}
```

The initial verdict may carry `null` only while it is a non-merge-authorizing review result. A consumer may not infer an integration pass from null.

## Field rules

| Field | Rule |
|---|---|
| `schema` | Exact literal `review-verdict-b1.1`. |
| `verdict_id` | Producer-unique, immutable, and never reused. |
| `repository` | Exact owner/name string; must equal the consumer repository. |
| `pull_request_number` | Positive integer; must resolve to the same repository. |
| `review_request_id` | Immutable request identity; all later verdicts refer to the request lineage. |
| `reviewed_head_sha` | Full 40-hex Git SHA `H`; never replaced after issuance. |
| `review_request_base_sha` | Full 40-hex SHA `B_request` observed at request creation. |
| `scope_digest` | SHA-256 over the canonical sorted changed-path/scope projection. |
| `core_classification` | Producer assertion only; consumer recomputes and rejects disagreement that would lower severity. |
| `decision` | Closed enum. Only `approve` can be considered for merge. |
| `reviewer_identity` / `reviewer_key_id` | Must resolve through the trusted key service or explicit allowlist. Unknown keys fail closed. |
| `issued_at` / `expires_at` | RFC-3339 UTC; expiry is checked at consumption. |
| `head_check` | Required for merge; `head_check.head_sha == reviewed_head_sha` and conclusion must be success. |
| `integration_check` | Required for merge after base validation; its SHA must equal the current synthetic merge result and its base/head pair must equal the validated pair. |
| `signature` | Covers all other canonical fields with the B1 domain separator. |

No field named `current_head`, `merge_sha`, or generic `check_sha` is permitted; those names hide distinct identities.

## Canonicalization and signature

The B1 schema reuses the already tested canonical JSON profile only through a pure neutral interface. The implementation must first prove that importing the existing helper does not initialize Federation runtime behavior. Otherwise B1-S1 must perform a minimal neutral extraction; it must not copy a subtly different serializer.

The signature input is:

```text
REVIEW-VERDICT-B1.1\0 + SHA256(canonical_json(unsigned_envelope))
```

The exact key registry and algorithm remain those of the existing trusted identity service. A key supplied inside the envelope is data, not provenance.

## Ledger projection

The append-only local ledger stores the signed envelope and validation facts without conflating identities:

```json
{
  "verdict_id": "rv_...",
  "repository": "kimeisele/agent-city",
  "pull_request_number": 2495,
  "reviewed_head_sha": "<H>",
  "review_request_base_sha": "<B_request>",
  "validated_current_base_sha": "<B_current>",
  "head_check_sha": "<H>",
  "integration_check_sha": "<M_current>",
  "merge_expected_head_sha": "<H>",
  "merge_commit_sha": null,
  "scope_digest": "sha256:<hex>",
  "validation_state": "valid|stale|blocked|merged|external_merge",
  "append_sequence": 17
}
```

`merge_commit_sha` is null until GitHub confirms a merge. On a squash merge it is the final new commit `S`; it cannot be used as a check or reviewed-head identity. An external or break-glass merge records `validation_state=external_merge` and its observed `merge_commit_sha`, never `merged` through the normal authority path.

## Validation order

1. Parse closed canonical bytes and reject unknown/duplicate/non-canonical input.
2. Resolve repository and PR and fetch current head/base.
3. Verify reviewer key provenance and signature.
4. Require `current_head == reviewed_head_sha`; otherwise stale.
5. Recompute changed paths, core classification, and `scope_digest`.
6. Apply base-drift Policy C and determine whether a fresh review is required.
7. Verify `head_check_sha == H` and success.
8. Verify current synthetic integration identity `M_current`, its base/head pair, and success.
9. Append validation evidence atomically.
10. Only `PRLifecycleManager` may perform final head revalidation and SHA-bound squash merge.

Any failed or unavailable step blocks the merge. No field is defaulted, inferred from a title, or reconstructed from an old verdict.
