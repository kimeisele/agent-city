# B1-S3A shadow-path reconnaissance

This note is descriptive only.  B1-S3A never calls a merge API and does not
replace an existing lifecycle path.

## Current merge-capable paths

| Path | Location | Current behavior | S3A treatment |
| --- | --- | --- | --- |
| Agent City lifecycle | `city/pr_lifecycle.py:144-195` (`PRLifecycleManager.check_all`, `_auto_merge`) | Reads `gh pr checks`; when configured, invokes `gh pr merge --merge --auto`. | Read-only reconnaissance; unchanged. |
| Hook wrapper | `city/hooks/moksha/mission_lifecycle.py` | Invokes the existing lifecycle hook. | Unchanged. |
| Scanner/core classification | `city/hooks/genesis/pr_scanner.py` | Owns Agent-City `CORE_FILES` classification. | Read-only consumer classifier boundary; unchanged. |

No B1-S3A code imports these paths, invokes `gh`, or changes their authority.

## Evidence ownership

`review-governance/head` is an exact raw-head evidence identity.  A normal
`pull_request` workflow's synthetic SHA is not accepted as H evidence.  The
S3A package exposes read-only provider protocols and deterministic test
providers; a production Check Run/status producer remains a B1-S3B deployment
decision.

`review-governance/merge-result` must prove the tuple `(H, B_current, M)` and
is evaluated independently from the signed reviewer verdict.  No successful H
check substitutes for this integration evidence.

## Shadow boundary

Current-base snapshots, base-delta classifications, Policy-C decisions and
Council checks are local immutable inputs/results.  Optional ledger events are
append-only shadow evidence.  No event is merge-authorizing, and
`merge_completed`/`external_merge_observed` are never emitted by S3A.

Fork or permission failures are represented as unavailable/ambiguous evidence
and fail closed.  No untrusted PR text is executed and no privileged workflow
is introduced by this change.
