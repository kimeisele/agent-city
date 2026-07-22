# B1 Impact and Test Plan

Status: planning only. No test workflow or production implementation is authorized by this document.

## Impact boundaries

The change will eventually affect the Steward verdict emitter, Agent City verdict consumer, local append-only ledger, and the normal PR lifecycle merge caller. It must not change Federation V1 transport semantics, READY/Claim/Lease, Scheduler/Worker/Mission/Queue behavior, Context Bridge, Provider Failover, or activation.

The current Agent City baseline has no `pull_request` workflow. The existing heartbeat workflow is schedule/manual/repository-dispatch driven and the wiki workflow is main-push/scheduled. Therefore B1-S3 must explicitly introduce the required CI path later; this package does not add it.

## B1-S1 — schema, validator, ledger

Scope:

- closed `review-verdict-b1.1` shape;
- pure canonicalization adapter or minimal neutral extraction;
- trusted reviewer-key verification with explicit allowlist and fail-closed unknown-key behavior;
- repository/PR/head/scope binding;
- consumer-side core recomputation;
- append-only ledger records with distinct SHA fields.

Required tests:

1. missing security fields, unknown fields, duplicate keys, and non-canonical bytes reject;
2. signature verifies only for the exact canonical envelope and trusted key;
3. wrong repository, PR, head, scope digest, expiry, or reviewer identity rejects;
4. producer `core_classification` cannot lower consumer classification;
5. U4 helper import is proven side-effect free, or the neutral extraction is tested;
6. ledger append is immutable, ordered, and corruption fails closed;
7. the six identity fields (`reviewed_head_sha`, request/current bases, check identities, merge expected head, final merge SHA) never alias.

## B1-S2 — request and Steward emitter

Scope:

- canonical review request construction;
- exact repository/PR/head/base capture;
- signed verdict emission;
- no merge authority in the emitter.

Required tests:

- request and verdict regenerate byte-identically;
- a head movement creates a new request lineage and never updates an old verdict;
- missing or unknown reviewer key blocks emission/consumption;
- scope changes alter the digest;
- Steward and Agent City disagreeing on core classification escalates and cannot lower Agent City's decision.

## B1-S3 — merge authority and required PR CI

Scope:

- stable required checks `review-governance/head` and `review-governance/merge-result`;
- raw-head security/static check and synthetic-merge integration check;
- current-base revalidation;
- sole normal `PRLifecycleManager` merge caller;
- SHA-bound squash merge using `gh pr merge --match-head-commit H` or REST `sha=H` fallback;
- external/break-glass audit visibility.

Required tests:

1. a verdict for H1 remains cryptographically valid after base movement;
2. integration readiness clears when the relevant base/check identity changes;
3. current-base integration check passes before merge;
4. head movement always makes the verdict stale;
5. base movement never silently substitutes a new reviewed head;
6. core/overlap Policy C requires re-review;
7. obsolete synthetic merge SHA is rejected;
8. successful head check cannot substitute for a failed merge-result check;
9. atomic merge fails when the head changes after final revalidation;
10. ledger records reviewed head, checked integration identity, and final merge SHA separately;
11. no second merge authority can call GitHub in the normal path;
12. external/break-glass merge is recorded as `external_merge` with actor/reason.

## Matrix of required identities

| Scenario | H | B_request | B_current | head check | integration check | Expected |
|---|---|---|---|---|---|---|
| unchanged base | same | B1 | B1 | H success | M1 success | merge eligible |
| non-overlap base drift | H1 | B1 | B2 | H1 success | M2 success | eligible after rerun |
| core/overlap drift | H1 | B1 | B2 | H1 success | M2 success | fresh verdict required |
| head moved | H2 | B1 | B1/B2 | H1 or H2 mismatch | any | stale/block |
| merge result failed | H1 | B1 | B1 | H1 success | M1 failure | blocked |
| obsolete merge result | H1 | B1 | B2 | H1 success | M1 only | blocked |
| final race | H1 then H2 | B_current | B_current | success | success | atomic merge rejects H2 mismatch |

## U1–U5 test ownership

- **U1:** B1-S3 base-delta and overlap tests.
- **U2:** B1-S3 branch-policy registration and stable-name tests; no arbitrary names in S1.
- **U3:** B1-S1 consumer classification tests plus S2 disagreement escalation.
- **U4:** B1-S1 import/side-effect test and canonical-byte parity tests.
- **U5:** B1-S1 key-registry provenance and unknown-key rejection tests.

## Explicit exclusions

No workflow, branch-protection setting, Python code, Federation code, G-07 fix, or implementation issue is created here. The controlling issue remains [#2495](https://github.com/kimeisele/agent-city/issues/2495).
