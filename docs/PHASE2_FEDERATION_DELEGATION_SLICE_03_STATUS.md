# Phase 2 Addendum — Federation Delegation Slice 03

This Agent City addendum records the merged Slice-03 milestone. Agent City has
no pre-existing `PHASE2_CURRENT.md` or `PHASE2_BEFUND.md`; this file is a
versioned milestone record and does not replace another repository's Phase-2
SSOT.

## Authoritative merge pins

* Repository: `kimeisele/agent-city`
* PR: #2245
* Product implementation commit: `51ab9dbe49a9ebeac9451d3d895f3ff0d1a5bd80`
* Merge commit and final `main` pin: `e4682c28905f6202eb6a92124b1eee3d01b0e3d2`
* Pre-merge branch head: `3800e2d532525c87b71dd4ddded9fcf156f10f00`
* Base before merge: `5acf648075643af575be0ad57be9960da02f3999`
* Merge method: owner-authorized documented admin bypass; GitHub reported no
  automatic checks and only `REVIEW_REQUIRED` blocked merge

## Accepted Slice-03 truth

The merged slice proves only this target-local transition:

```text
validated ASSIGNED parent
  -> one atomically persisted embedded ready_work_item(state=READY)
```

`READY` means that a small immutable local work record exists with frozen
request, assignment, authority, candidate, and target-key digest bindings. It
does not mean started work, dispatch, claim, reservation, lease, scheduler
acceptance, mission creation, queue creation, worker activity, or any side
effect.

The child is not a Federation envelope, carrier, receipt, or external message.
No Steward product code, Federation wire contract, Golden Fixture, Mission,
Queue, Scheduler, Worker, Cartridge, Tool, LLM, Git, Status Query, Recovery,
terminal receipt, Verification receipt, or Managed-Task transition was added.

## Historical post-merge evidence

Smoke was run against final `main` pin `e4682c28905f6202eb6a92124b1eee3d01b0e3d2`.
The deterministic private test seed file is ignored by Git by design and was
provided only in the temporary local test checkout; it was not changed or
committed.

* READY suite: 23 passed
* Federation/Slice regression suites: 178 passed
* Legacy/Mission/Heal suite: 144 passed
* Focused READY integrity/crash/duplicate/process cases: 15 passed
* Focused Slice-02 retry/crash/corruption/process cases: 9 passed
* Ruff and `py_compile`: passed
* Full repository collection: blocked by the separate import finding recorded
  in `MAINTENANCE_FINDING_CAMPAIGN_RECRUITMENT_IMPORT.md`
* Feature gate: `FEDERATION_V1_DELEGATION_ENABLED=false`
* Disposition: `disabled`
* Product activation: none

These are historical, reproducible milestone observations. They are not live
provider, node, heartbeat, ledger, or capability-health values.

## Wiring truth

`FEDERATION_DELEGATION_WIRING_MANIFEST_03.json` is versioned capability/audit
documentation only. No runtime module imports it or treats its merge pins,
test counts, `crucible_verified`, or `disabled` value as current health.
Dynamic health remains sourced from runtime state, persistent runtime state,
or measured probes.

## Explicit locks after Slice 03

The following remain locked:

* external READY, Assignment, or Started messages;
* Federation-wire changes and cross-repository protocol ownership changes;
* mission, queue, scheduler, claim, reservation, or lease creation;
* worker, cartridge, tool, LLM, Git, or PR execution;
* recovery automation, Status Query, terminal or Verification receipts;
* Steward product changes, Provider Failover, Context Bridge, and
  Execution-Spine expansion;
* productive activation and Slice 04.
