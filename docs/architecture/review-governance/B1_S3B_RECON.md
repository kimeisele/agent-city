# B1-S3B live governance boundary

Status: Draft implementation artifact. B1-S3B is shadow-capable but not
authorized to merge or activate production governance.

## Existing merge-capable paths

The reconnaissance found two historical application paths:

* `city/pr_lifecycle.py` previously issued an unbound `gh pr merge --merge --auto`.
* `city/hooks/dharma/pr_verdict.py` previously issued a direct merge after an
  approval verdict.

The S3B branch removes both direct mutations. The lifecycle and verdict hook
can request or observe governance, but only
`city/review_governance/merge_authority.py::ReviewGovernanceMergeAuthority`
contains the normal SHA-bound merge operation. Its feature flag is disabled
by default and no caller activates it in this slice.

## Evidence boundary

`GitHubLiveEvidenceProvider` is read-only. It resolves
`review-governance/head` against the raw reviewed head and
`review-governance/merge-result` against the explicit current integration SHA,
while checking repository, pull request, source head and source base. The
producer is accepted only through the explicit
`AGENT_CITY_B1_TRUSTED_PRODUCERS` allowlist; missing or malformed configuration
fails closed. No workflow or check producer is added in S3B.

Fork pull requests are fail-closed unless an independently trusted producer
observation is available. No privileged `pull_request_target` execution or
untrusted checkout is introduced.

## Snapshot, revalidation and merge boundary

`GitHubSnapshotResolver` reads the current PR, exact head/base, file identities,
and integration identity. `ReviewGovernanceMergeAuthority` requires a fresh
`FinalMergeStateResolver` supplies that complete observation immediately before
invoking a structured
`gh pr merge ... --squash --match-head-commit H` command. It records the final
squash SHA separately after GitHub confirms the merged state.

All Checks, Statuses, PR-file, and compare-file collections use bounded
pagination. Repeated links, malformed pages, partial failures, and page-limit
exhaustion fail closed. Missing GitHub provenance timestamps are unavailable;
the adapter never substitutes local wall-clock time for evidence provenance.

The shadow ledger records readiness and merge-observation events append-only;
it never rewrites a verdict. External merges are recorded as
`external_merge_observed`, not as internal completion.

Merge attempts reserve an immutable `merge_attempt_reserved` event before the
GitHub mutation. Completion is appended afterward. If completion persistence
fails after GitHub confirms success, the result is `MERGE_SUCCEEDED_AUDIT_PENDING`
and `reconcile()` can append completion idempotently without a second merge.

## Activation plan (not performed)

Branch protection is unchanged. A later activation review must establish the
stable checks `review-governance/head` and `review-governance/merge-result`,
verify trusted producers for same-repository and fork cases, stage enforcement
without a deadlock, and define rollback. No required checks are registered by
S3B and no live governed merge was performed.

Break-glass remains disabled by default and is not invoked.
