# Phase 2 Addendum — Federation Delegation Slice 02

This is an Agent City Phase-2 status addendum. Agent City has no pre-existing
`PHASE2_CURRENT.md` or `PHASE2_BEFUND.md`; this file therefore records only the
Slice-02 milestone and does not claim to replace another repository's Phase-2
SSOT.

## Authoritative merge pin

* Repository: `kimeisele/agent-city`
* PR: #2235
* Merge commit and `main` pin: `09ea3d3770fa126936756becec2eb6b0493a1a13`
* Pre-merge implementation head: `b56f58fac44c3e8f55866177f3b47df94df2397e`
* Merge method: documented owner-authorized admin bypass; GitHub had no
  automatic checks and was blocked only by `REVIEW_REQUIRED`

## Accepted Slice-02 truth

The merged slice proves only a target-local transition:

```text
validated ACCEPTED admission
  -> one atomically persisted ASSIGNED candidate snapshot
  -> one provenance-bound local assignment attestation
```

`ASSIGNED` does not mean started work. The slice creates no mission, queue,
reservation, lease, worker, cartridge, tool, LLM, Git side effect, external
assignment/started receipt, terminal result, verification, or Managed-Task
completion. Steward has no new product path in this milestone.

## Historical evidence

Post-merge checks against the final `main` pin:

* Federation/Slice suites: 178 passed
* Legacy/Mission/Heal suites: 144 passed
* Focused crash/retry/process/corruption cases: 9 passed
* Ruff, `py_compile`, JSON and diff checks: passed
* Feature gate: `FEDERATION_V1_DELEGATION_ENABLED=false`
* Disposition: `disabled`

Warnings are pre-existing dependency deprecations and are not interpreted as
runtime health. These are reproducible milestone observations, not live
provider, node, heartbeat, ledger, or capability-health values.

## Wiring truth and next gate

`FEDERATION_DELEGATION_WIRING_MANIFEST_02.json` is versioned audit
documentation only. No runtime module imports it or treats its merge pins,
test counts, `code_complete`, `disabled`, or `crucible_verified` values as
current health. Dynamic health must continue to come from runtime state or
measured probes.

The following remain explicitly locked after Slice 02:

* external Assignment or Started receipts;
* mission, queue, scheduler, worker, cartridge, tool, LLM, or Git execution;
* lease/recovery automation and status query;
* terminal/verification receipts and Managed-Task completion;
* Provider Failover, Context Bridge, Execution-Spine expansion, and productive
  activation.

No Slice 03 implementation is authorized by this addendum.
