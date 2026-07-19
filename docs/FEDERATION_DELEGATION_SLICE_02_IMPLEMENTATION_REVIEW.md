# Federation Delegation Slice 02 — Implementation Review

Status: merged to `main`; post-merge smoke verified

This document is the self-contained Agent-B review packet for the accepted
target-local Slice 02. It records the implementation boundary, evidence, and
the remaining gate. It does not authorize activation or merge.

## Evidence and working basis

| Item | Value |
| --- | --- |
| Repository | `kimeisele/agent-city` |
| Branch | `impl/federation-delegation-slice-02-assignment` |
| Base pin | `a854f590391f73da10b33f402c321fd68f3fd0b5` (`main`, including docs PR #2209) |
| Slice-02 merge PR | #2235 |
| Slice-02 merge commit / final main pin | `09ea3d3770fa126936756becec2eb6b0493a1a13` |
| Contract pin | Federation Delegation Contract V1 Draft 0.5 as already frozen; no contract file changed |
| Steward product code | unchanged; no Steward repository change is part of this slice |
| Feature gate | `FEDERATION_V1_DELEGATION_ENABLED`, default `false`; tests opt in explicitly |
| Disposition | `disabled`; no production caller or transport activation |
| Cross-repo receipt | none by design; Slice 02 is target-local and emits no Federation receipt |

The implementation was merged by the documented owner-authorized admin bypass
because GitHub reported no automatic checks and blocked only on
`REVIEW_REQUIRED`. The merge commit above is now the authoritative Agent City
`main` pin. This document remains historical milestone evidence; it is not
runtime health state.

## Exact scope

The only new product transition is:

```text
validated ACCEPTED admission
  -> two read-only candidate observations
  -> one atomic target-ledger ASSIGNED record
  -> one target-local signed assignment attestation
```

`ASSIGNED` means that a deterministic candidate snapshot was observed twice,
the authority binding was checked, and the snapshot plus evidence was durably
bound to the existing admission record. It does **not** mean that work started.

The implementation does not create or call a mission, queue item, reservation,
lease, worker, cartridge, LLM, tool, Git operation, HealExecutor,
MissionRouter, TaskManager, Sankalpa path, or external transport. It does not
create a `started` Receipt and does not add a Steward state or correlation path.

## Changed files and isolation

Product and test changes are limited to:

* `city/federation_v1.py`
  * optional Slice-02 assignment fields and fail-closed validation;
  * `FederationV1CandidateSnapshotAdapter` (read-only source adapter);
  * deterministic candidate selection and authority binding;
  * atomic `TargetAdmissionLedger.assign_candidate`;
  * target-local signed assignment attestation builder and validator;
  * gated `FederationV1Admission.assign_candidate` adapter.
* `tests/test_federation_v1_assignment.py`
  * positive, duplicate, conflict, stale, unavailable, corruption,
    concurrency, process, crash, gate, and no-side-effect tests.
* `tests/test_federation_v1_admission.py`
  * binds the existing typed target identity registry into the target adapter
    used by the assignment tests.
* `docs/FEDERATION_DELEGATION_WIRING_MANIFEST_02.json`
  * static, versioned capability/audit documentation for this slice.
* this review document.

The following remain unchanged and explicitly out of scope:

* Steward product code and Steward Origin ledger;
* frozen Draft 0.5 wire contract and Golden Wire Fixtures 01A;
* Phase 1 and Context Bridge;
* legacy `OP_DELEGATE_TASK`, NADI, MissionRouter, TaskManager, Sankalpa,
  Worker/Cartridge, HealExecutor, provider, workflow, and merge authority
  paths;
* status query, leases, recovery automation, terminal/verification receipts,
  Managed-Task completion, and production activation.

## Existing ledger boundary and schema delta

No second work store was introduced. `TargetAdmissionLedger` remains the
single target-owned persistence boundary with its existing process lock,
fail-closed loading, and atomic `os.replace` write.

New records created by the admission path contain the following additional
fields. Slice-01A records without these fields continue to load; their
in-memory view defaults an accepted admission to `assignment_state=ACCEPTED`
and all assignment evidence fields to `null`.

```text
assignment_authority = {
  authority, capability, target_repo
}
assignment_state              ACCEPTED | ASSIGNED | null
assignment_epoch              integer (Slice 02: exactly 1) | null
assigned_candidate_id         string | null
observed_candidate_snapshot   object | null
worker_snapshot_digest        SHA-256 hex | null
assignment_authority_digest   SHA-256 hex | null
assigned_at                   RFC-3339 UTC second | null
assignment_attestation_id     string | null
assignment_content_digest     SHA-256 hex | null
assignment_message_hash       SHA-256 hex | null
assignment_signature           standard Base64 Ed25519 signature | null
assignment_wire_bytes_b64      standard Base64 canonical attestation bytes | null
assignment_key_binding         immutable validated-key snapshot | null
assignment_key_binding_digest  SHA-256 hex over validated-key snapshot | null
```

The transition is monotonic for this slice: `ACCEPTED -> ASSIGNED`. A rejected
admission cannot be assigned. `target_work_id` is the deterministic work
identifier already set by Slice 01A; Slice 02 does not create a new work item.

## Candidate observation and authority rules

`FederationV1CandidateSnapshotAdapter` accepts only a closed source record with
the fields `candidate_id`, `cartridge_id`, `capabilities`,
`capability_tier`, `domain`, `capability_protocol`, `guardian`, and `active`.
Unknown fields, malformed IDs, duplicate capabilities, and invalid types fail
closed.

The adapter normalizes capabilities, sorts candidates by
`(candidate_id, cartridge_id)`, and selects the first active candidate with
the `fix_repository` capability. It derives an opaque `source_generation`
from the canonical normalized source using the assignment-source domain. The
stored candidate snapshot contains the candidate facts, `source_generation`,
`observed_at`, and `snapshot_schema=federation-assignment-candidate-v1`.

The source is observed twice immediately before commit. A changed generation
or candidate fingerprint produces `candidate_snapshot_stale`; no assignment
or attestation is written. No candidate produces `assignment_unavailable`;
this is not retried automatically.

The admission authority must be exactly the existing V1 policy shape: capability
`fix_repository`, target repository `agent-city`, matching repository scope,
allowed actions drawn only from `branch`, `commit`, `read`, and `test`, and
`merge` present in denied actions. The authority input binds policy, candidate,
delegation, target node, epoch, target work ID, and worker snapshot digest.
`assignment_authority_digest` is SHA-256 over the canonical input with the
assignment-authority domain.

The candidate digest is SHA-256 over the canonical observed candidate snapshot
with the assignment-candidate domain. The source generation is an observation
fingerprint, not reservation, ownership, a lease, or a guarantee that the
candidate remains available after the commit.

The assignment signer is not trusted from the attestation alone. Before an
`ACCEPTED` assignment, the target resolves its own `key_id` through the typed,
immutable `ValidatedFederationV1KeyRegistry` snapshot already used by Slice
01A. The registry record must bind the target node, signer public key, key ID,
validity window, registry/certificate/activation epochs, and non-revoked state.
The complete binding snapshot and a domain-separated binding digest are stored
in the target ledger. On every `ASSIGNED` reload, the ledger checks:

* binding node equals the admission target node and configured target identity;
* attestation signer key and key ID equal the binding;
* key ID derives from the bound public key;
* `assigned_at` lies in the bound certificate window;
* the typed registry still validates the same key record at `assigned_at`;
* epoch and revocation fields match the immutable binding.

A foreign valid Ed25519 signature, a foreign key ID, a wrong target key, a
revoked key, or a persisted binding/digest mutation therefore fails closed as
`ledger_corrupt` (or a narrower provenance failure before an assignment is
created). A later retry cannot replace the first-set binding or create a second
epoch.

## Atomic assignment and duplicate semantics

1. Load and fully validate the target ledger under the existing process lock.
2. If the record is already `ASSIGNED`, return the stored record immediately.
   Do not read the Candidate source, derive a new observed time, or sign a new
   attestation.
3. For `ACCEPTED`, require a non-null Slice-01A `target_work_id`, allowed
   authority, and a provenance-valid target signing-key record.
4. Observe and normalize the candidate source twice.
5. Compute candidate, authority, and key-binding digests and deterministically
   build and sign the complete local attestation **before** the write.
6. Reacquire the process lock and reload the latest ledger.
7. If another process already persisted `ASSIGNED`, return that stored record
   byte-for-byte, regardless of a later caller `observed_at` or candidate
   source. Otherwise, write all assignment fields and complete attestation in
   one atomic document replacement.

The atomic commit contains the target work ID already present on the admission,
assignment epoch, immutable candidate snapshot, candidate/authority/key-binding
digests, assignment time, attestation ID/content/message hashes, signature, and
the complete canonical attestation bytes. There is no intermediate assignment
state and no separate evidence store.

## Target-local assignment attestation

The attestation is intentionally **not** a Federation V1 envelope and is never
accepted by the Federation receipt handler. Its closed key set is:

```text
assignment_attestation_id
assignment_attestation_version
assignment_authority_digest
assignment_content_digest
assignment_epoch
assignment_message_hash
assignment_signature
assignment_state
delegation_id
key_id
observed_at
origin_node_id
signer_key
target_node_id
target_work_id
worker_snapshot_digest
```

The attestation version is `federation-assignment-attestation-v1` and the
assignment state is `ASSIGNED`. The content digest covers the semantic
attestation content (excluding IDs, signer metadata, and digest/signature
fields). The message hash covers the complete unsigned attestation object.
The signature input is:

```text
ASCII("STEWARD-FEDERATION-ASSIGNMENT-ATTESTATION-V1")
|| 0x00 || bytes.fromhex(assignment_message_hash)
```

The target ledger validates canonical bytes, closed keys, all persisted field
bindings, content digest, message hash, timestamp binding to `assigned_at`, and
the Ed25519 signature before returning an assigned record. A malformed or
mutated record raises `ledger_corrupt`; it is never silently repaired.

This attestation is a signed target statement, not a Federation receipt and not
an independent proof available to Steward. Steward has no new product path in
this slice and cannot verify target-local candidate evidence remotely.

## Crash, duplicate, and conflict matrix

| Scenario | Required result | Evidence |
| --- | --- | --- |
| First accepted assignment | one `ASSIGNED`, epoch 1, complete attestation | `test_acceptance_becomes_one_target_local_assigned_attestation` |
| Identical duplicate | byte-identical stored evidence; no second write semantics | `test_identical_duplicate_returns_byte_identical_local_evidence` |
| Assigned retry with different candidate source/time | stored byte-identical assignment; source not read | `test_assigned_retry_ignores_changed_candidate_source` |
| Persisted authority mutation | `ledger_corrupt`; fail closed | `test_persisted_authority_mutation_fails_closed` |
| Persisted epoch/work-ID mutation | `ledger_corrupt`; fail closed | `test_changed_persisted_assignment_binding_fails_closed` |
| Source generation/candidate changes between observations | `candidate_snapshot_stale`; no evidence | `test_source_generation_change_is_stale_before_commit` |
| No eligible candidate | `assignment_unavailable`; no evidence | `test_no_candidate_is_unavailable_without_attestation` |
| Authority mismatch | `authority_denied`; no assignment | `test_authority_mismatch_is_fail_closed` |
| Crash before atomic assignment commit | accepted record remains without assignment evidence | `test_crash_before_assignment_commit_leaves_accepted_without_evidence` |
| Crash after atomic commit | complete assigned record survives and validates | `test_crash_after_assignment_commit_leaves_complete_assigned_evidence` |
| Two ledger instances/threads | at most one assignment and one byte set | `test_two_process_safe_instances_create_one_assignment` |
| Two independent processes | at most one assignment and one byte set | `test_two_independent_processes_create_one_assignment` |
| Mutated attestation signature | `ledger_corrupt` | `test_corrupt_assignment_attestation_fails_closed` |
| Foreign valid signer/key ID replacement | `ledger_corrupt`; target binding unchanged | `test_foreign_valid_key_cannot_replace_target_assignment_attestation` |
| Key revoked at assignment time | `ledger_corrupt`; no assignment | `test_key_revoked_at_assignment_time_fails_closed` |
| Retry source not read after assignment | byte-identical first-set record | `test_duplicate_retry_uses_stored_assignment_without_source_read` |
| Process race with different observed times | one first-set epoch and identical bytes | `test_process_race_with_different_times_returns_first_set_bytes` |
| Dispatch/execution surface called | test fails immediately; no call is made | `test_assignment_does_not_call_dispatch_or_execution_surfaces` |

The process lock protects the complete read-modify-write sequence. The atomic
replacement protects readers from partial JSON. No automatic retry or recovery
engine is introduced.

## Validation performed

The targeted and regression suites were run after the final code/test changes:

```text
ruff check city/federation_v1.py tests/test_federation_v1_assignment.py
  passed
python -m py_compile city/federation_v1.py tests/test_federation_v1_assignment.py
  passed
pytest -q tests/test_federation_v1_assignment.py
  23 passed, 1 warning
pytest -q tests/test_federation_v1_assignment.py \
  tests/test_federation_v1_admission.py \
  tests/test_federation_v1_hardening.py \
  tests/test_federation_nadi.py tests/test_federation_relay.py tests/federation_v1
  178 passed, 1 warning
pytest -q tests/test_mission_router.py tests/test_city_router.py \
  tests/test_federation_nadi.py tests/test_federation_relay.py tests/test_layer4.py
  144 passed, 184 warnings

The same suites were rerun against final `main` at
`09ea3d3770fa126936756becec2eb6b0493a1a13` after PR #2235 merged. The focused
post-merge crash/retry/process/corruption selection produced `9 passed` and
the static gate/disposition probe reported `feature_gate_default=False` and
no active disposition. The process-concurrency coverage is also part of the
full 178-test Federation run.
```

The warning is the pre-existing `ast.Num` deprecation in the external
`steward-protocol` dependency. No test changes import a shared runtime library
or fixture builder into production code.

## Wiring and activation truth

`docs/FEDERATION_DELEGATION_WIRING_MANIFEST_02.json` is static, versioned
capability/audit documentation. A repository search confirms no runtime module
imports or reads either wiring manifest as health state. The values
`code_complete`, `crucible_verified`, `disabled`, pins, and test counts are
historical milestone claims, not live provider/node/heartbeat/ledger health.
Dynamic health remains the responsibility of measured runtime state or probes.

The Slice-02 capability is recorded as target-local assignment only and remains
`disposition=disabled`. The feature gate defaults to `false`; no production
caller has been added. The legacy operation and all legacy routing/execution
paths remain isolated.

## Definition of done for this implementation branch

This slice is post-merge complete when:

* the exact merge commit and final main pin are the values recorded above;
* the tests and static checks above are green on final `main`;
* feature gate false, disposition disabled, and no runtime manifest import are
  re-verified;
* the review acknowledges that no cross-repo Assignment or Started receipt is
  emitted in Slice 02.

The next slice, if separately approved, must establish a real persistent work
item or scheduler reservation before introducing any externally visible
`started` receipt. No such work is part of this branch.
