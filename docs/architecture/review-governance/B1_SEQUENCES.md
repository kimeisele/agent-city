# B1 Sequences

These are normative planning sequences only. They do not authorize implementation.

## Normal review and merge

```text
Steward/Reviewer             Agent City consumer             GitHub
      |                              |                         |
      | review request (B_request,H) |                         |
      |----------------------------->|                         |
      | signed verdict for H         |                         |
      |----------------------------->|                         |
      |                              | verify key/signature    |
      |                              | recompute scope/core    |
      |                              | validate head check H  |
      |                              |------------------------>|
      |                              | fetch current B/H       |
      |                              | request merge-result CI |
      |                              |<-------------------------|
      |                              | M_current check success |
      |                              | append verdict evidence |
      |                              | final fetch H/B/checks  |
      |                              | PUT merge sha=H,squash  |
      |                              |------------------------>|
      |                              |<-------------------------| S
      |                              | append merge_commit S   |
```

The three merge-time facts are separate: `H` is the reviewed head, `M_current` is the current synthetic merge-result check identity, and `S` is the final squash commit.

## Q15 — Base advances, head unchanged

```text
B1 + H1 -> review request/verdict
B1 + H1 -> head check succeeds on H1
B1 advances to B2
consumer computes D = paths(B1..B2)
non-core and D has no reviewed/core overlap
old verdict remains valid for H1
old integration readiness is discarded
CI produces M2 = merge(B2,H1)
merge-result check succeeds on M2
final merge revalidates H1 and B2, then squash-merges with sha=H1
```

No new reviewed head is invented. If `M2` cannot be produced or checked, merge is blocked.

## Q16 — Base advances and overlaps reviewed scope

```text
B1 + H1 -> verdict
B1 advances to B2
D = paths(B1..B2) overlaps changed scope or CORE_FILES
old verdict remains historical evidence but is not merge-authorizing
new review request binds H1 to B2
fresh head and merge-result checks are required
```

An uncomputable delta is treated as overlap/unknown and takes the same fail-closed branch. A conflict never receives a synthetic approval.

## Q17 — Head check passes, current merge result fails

```text
H1 -> review verdict and successful head check
B_current + H1 -> M_current
merge-result check on M_current fails or is unavailable
ledger state = blocked
PRLifecycleManager does not call merge
```

A successful head check cannot substitute for a failed integration check. The verdict remains useful for audit but not for merge authorization.

## Head movement

```text
verdict(H1) -> PR head moves to H2
consumer observes current_head != reviewed_head
verdict(H1) = stale
no substitution of H2
new review request/verdict required
```

## External or break-glass merge

```text
normal authority gate -> blocked or bypassed by authorized external actor
GitHub reports merge S
consumer records external_merge, actor, reason, observed H/B/S
normal merged state is not fabricated
```

## Identity table

| Symbol | Meaning | Owner/observation point |
|---|---|---|
| `H` | raw reviewed PR head | GitHub PR event `pull_request.head.sha`; verdict binds it |
| `B_request` | base observed at review request | request creator, persisted in verdict |
| `B_current` | base fetched immediately before merge | consumer/merge authority |
| `M_current` | synthetic merge result used by integration CI | GitHub PR merge ref and check `head_sha` |
| `S` | final squash merge commit | GitHub merge response and post-merge audit |

No sequence may use one symbol as another. In particular, `GITHUB_SHA` on a pull-request workflow is `M_current`, not `H`.
