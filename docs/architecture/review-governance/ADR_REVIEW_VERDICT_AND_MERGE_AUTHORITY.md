# ADR-B1 — Canonical Review Verdict and Unified Merge Authority

Status: **Proposed — Senior Lead accepted in principle; implementation not authorized**

Controlling issue: #2495. Baseline: Agent City `6bd06b5bed5707e114be059f703ce690397944de`.

## Decision summary

B1 will establish one versioned, signed review-verdict contract and one normal merge authority. A verdict is valid only for the exact repository, pull request, reviewed head, canonical scope digest, and accepted reviewer identity. The consumer recomputes core-scope classification; it does not trust a producer-supplied boolean. The verdict ledger is append-only. `PRVerdictHook` validates and persists evidence only. `PRLifecycleManager` is the sole normal merge caller. A merge is a SHA-bound squash operation and external or break-glass merges remain visible as explicit audit outcomes.

The CI/Base Binding Gate amendment selects **Model HM** with two separate artifacts:

- the immutable, reviewer-signed `ReviewVerdictB1` binds security judgment and independently verified head evidence to raw reviewed head `H`;
- the mutable, Agent-City-owned `MergeReadinessEvaluationB1` binds current-base integration evidence to `M = merge(current_base, H)`;
- both artifacts are required before a normal merge, but a later readiness evaluation never rewrites the signed verdict.

This is a policy decision, not an implementation grant. If GitHub cannot expose a required check at the required SHA, the validator fails closed and the merge is not attempted.

## Why the gate exists

For a `pull_request` workflow GitHub sets `GITHUB_REF` to `refs/pull/<number>/merge` and `GITHUB_SHA` to the last commit on that merge branch. The event payload separately exposes `github.event.pull_request.head.sha`, which is the raw source-branch head. GitHub documents that the default checkout therefore tests the merged result, not only the head. Check-run and check-suite objects carry their own `head_sha`, and the Checks API associates a check run with the SHA for which it was created. Sources: [workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) and [check runs](https://docs.github.com/en/rest/checks/runs).

The baseline Agent City repository has no `pull_request` workflow. Its existing workflows are scheduled/manual heartbeat and main-branch wiki publication. The related Steward main (`2d6d86ff9b99452f8d642d015e913b70b1d6aad9`) does have a `pull_request` CI workflow with test, lint, and security jobs, but those checks run in Steward and cannot satisfy Agent City's merge policy. Therefore Agent City's nominal PR-CI path is currently absent; B1-S3 must create and protect that path later. This ADR does not add it.

## Scope and authority

The verdict producer may attest to its own analysis. The Agent City consumer owns merge gating for Agent City. Steward independently computes and reports its assessment; disagreement escalates to Council and Steward's answer cannot lower Agent City's classification. No trust-on-first-use is permitted. The baseline still has two concrete merge-capable paths (`steward/pr_gate.py` emits CI/verdict decisions and Agent City's `PRVerdictHook` directly invokes `gh pr merge`), which is the reason B1-S3 must cut over to one normal authority. Their current core-file sets also differ (`steward/pr_gate.py` includes `CLAUDE.md`; Agent City's scanner does not); U3 therefore requires Agent City's consumer-side recomputation to win.

The signed `ReviewVerdictB1` is immutable evidence of the reviewer's judgment about `H`. It contains no mutable current-base integration result. `MergeReadinessEvaluationB1` is a separate local append-only record owned by Agent City's merge-gating authority; it may be superseded whenever `B_current`, `M_current`, overlap classification, council state, or required checks change. Head-security evidence is represented inside the signed verdict only as independently verifiable, H-bound evidence references; it is not a mutable check result. Current-base integration evidence belongs only to the local readiness record.

`PRVerdictHook` may:

1. parse and authenticate a verdict;
2. recompute scope and core classification;
3. validate identities, timestamps, and check evidence;
4. append a verdict/finding to the local ledger.

It may not merge. `PRLifecycleManager` alone may perform a normal merge after final revalidation. Existing external or break-glass merges are recorded as such and never represented as ordinary lifecycle success.

## Base-drift policy: Policy C

The verdict remains cryptographically tied to `H`, but merge readiness is separate and must be recomputed against the current base.

### Non-core, non-overlapping change

If `B_request != B_current`, compute the base delta `D = paths(B_request..B_current)`. If the PR is non-core and `D` does not overlap the reviewed changed-path set or any core rule path:

- preserve the verdict's validity for `H`;
- invalidate old integration readiness;
- generate a new synthetic merge result `M_current` and rerun the required integration check;
- allow merge only when the new check is successful and bound to `M_current`.

### Core or overlapping change

If the PR touches a core path, or `D` overlaps the reviewed scope/core rule paths, the previous verdict is not merge-authorizing. Require a new review request/verdict for the same `H` and `B_current`, followed by fresh checks. This is the strict re-review branch of Policy C.

### Conflict or unavailable comparison

A merge conflict, inability to compute `D`, missing path metadata, or unavailable current-base check is fail-closed. No inferred non-overlap is allowed.

### Head movement

Any `H1 -> H2` movement makes the verdict stale. `H2` is never silently substituted for `H1`; a new request and verdict are required.

## CI/check binding: Model HM

The minimum B1-S3 required set is two stable check identities, not display text chosen per run:

- `review-governance/head` — proposed H-bound security/static evidence reference consumed by the signed verdict; it must bind to `reviewed_head_sha`.
- `review-governance/merge-result` — proposed M-bound integration aggregate recorded in `MergeReadinessEvaluationB1`; `head_sha == integration_check_sha` and `integration_check_sha` is the current synthetic merge result for `validated_current_base_sha + reviewed_head_sha`.

The names are proposed stable policy names; exact branch-protection registration is deferred to B1-S3. A check with a matching name but a different SHA is not evidence. If the branch-protection API cannot require both identities reliably, the consumer-side gate still requires both and refuses the merge.

### Raw-head evidence production boundary

A standard `on: pull_request` Actions job does **not** by itself create a raw-head check: its normal `GITHUB_SHA` is the synthetic merge result. Until B1-S3 selects and deploys a concrete producer, the signed verdict may carry an independently verified reviewer evidence reference whose provider record explicitly names `H` and whose digest is checked by the consumer. This is evidence bound to `H`, not a claim that an ordinary Actions check run was created on `H`.

B1-S3 must choose one operational producer for a native H-bound check: a same-repository `push` workflow (not sufficient for fork PRs), an explicitly created Check Run, or a commit status on `H`. A Check Run/status producer requires the appropriate GitHub App/token permissions to write checks/statuses; the consumer requires read access to retrieve and compare `head_sha`. Fork workflows must not execute untrusted fork code with write privileges. Until that producer and fork-safe policy are approved, unknown, unavailable, or mismatched H evidence fails closed and no native `review-governance/head` required check is claimed.

## Merge-time identity chain

The ledger keeps these identities distinct:

```text
review_request
  -> reviewed_head_sha = H
  -> verdict (repository, PR, H, scope_digest)
  -> signed H-bound evidence reference(s)
  -> review_request_base_sha = B_request
  -> validated_current_base_sha = B_current
  -> integration_check_sha = M_current
  -> merge_expected_head_sha = H
  -> final squash merge_commit_sha = S
```

`S` is created only by GitHub after the merge and is not a valid substitute for `H` or `M_current`.

## Atomic merge rule

The normal authority must re-fetch the PR immediately before merging, verify that the current head is exactly `merge_expected_head_sha`, verify current-base and both check identities, then call the GitHub merge endpoint with `sha=merge_expected_head_sha` and `merge_method=squash`. GitHub's REST endpoint documents that `sha` is the required expected PR head and returns conflict when the head differs. Canonical CLI form is `gh pr merge --squash --match-head-commit <H>`; REST is the fallback. A changed head causes no merge attempt or an atomic conflict response. Source: [REST pull-request merge](https://docs.github.com/en/rest/pulls/pulls).

## U1–U5 disposition

- **U1 — Core PR base drift:** resolved by Policy C above: non-core/non-overlap reruns current-base integration; core/overlap requires re-review; conflict/unknown comparison fails closed.
- **U2 — Required check names:** do not finalize arbitrary names in B1-S1. B1-S3 proposes the stable pair `review-governance/head` and `review-governance/merge-result`; names are policy identifiers, not mutable display labels.
- **U3 — `CORE_FILES` source:** Agent City is authoritative for Agent City merge gating. Steward independently reports. Both repositories keep versioned local rule sets in their own contracts; B1 does not create a shared repository. Disagreement escalates and cannot reduce Agent City's classification.
- **U4 — Canonicalization:** the current baseline's `city.federation_v1.canonical_bytes` imported and ran without initializing other `city.federation`/runtime modules in a targeted read-only probe. B1-S1 may reuse it behind a neutral local verdict-schema interface, with a side-effect test. If a future import path is not safely importable, B1-S1 documents the smallest neutral extraction; it does not copy a second profile or activate Federation V1.
- **U5 — Reviewer keys:** use the existing trusted identity/key service if it deterministically verifies Steward; otherwise use an explicit configured allowlist of accepted reviewer identities/keys and fail closed for unknown keys. The limitation is an ADR-B7 follow-up. A supplied `signer_key` is never self-authorizing.

## Consequences

This decision adds explicit state and check identity to the ledger and makes base drift observable rather than silently tolerated. It requires a future PR workflow and a deterministic current-base merge-result check. It intentionally does not create that workflow, change branch protection, or implement the verdict path in this documentation PR.

## Amendment log

- **Amendment 0.1 (2026-07-22):** resolved the CI/Base Binding Gate using official GitHub workflow/check API semantics; selected Model HM, Policy C, distinct SHA fields, and SHA-bound squash revalidation. Implementation remains unauthorized.
- **Amendment 0.2 (2026-07-22):** separated immutable signed `ReviewVerdictB1` from mutable local `MergeReadinessEvaluationB1`, clarified that head-security evidence is an independently verified H-bound reference rather than mutable integration data, and documented the raw-head evidence production boundary. Implementation remains unauthorized.
