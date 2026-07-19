# Federation Delegation Slice 03 — Immutable READY Work-Item Plan

**Status:** PLAN ONLY — NO PRODUCT CODE AUTHORIZED
**Repository:** kimeisele/agent-city
**Implementation-plan branch:** plan/federation-delegation-slice-03-ready-work-item
**Exact Agent-City main pin:** 5acf648075643af575be0ad57be9960da02f3999
**Recon accepted at:** 076810ad7bd5ad9bc7c977a0e36b6ead8d80ae07
**Slice-02 product pin:** 09ea3d3770fa126936756becec2eb6b0493a1a13
**Contract:** frozen Federation Delegation V1 Draft 0.5; no wire change proposed
**Feature gate:** FEDERATION_V1_DELEGATION_ENABLED remains false by default
**Disposition:** disabled; no productive activation

This document is the self-contained implementation plan requested after the
accepted Slice-03 recon. It defines only the smallest target-local transition:

~~~text
fully validated ASSIGNED
    -> exactly one embedded target-local ready_work_item
    -> READY
~~~

It does not implement the transition or add a product/runtime file, alter
Federation wire objects, add a receipt, create a mission or queue item, or
notify a scheduler. Agent-B review and acceptance of this plan are required
before any product-code branch is created.

## 1. Scope and non-goals

### In scope

* Extend the existing TargetAdmissionLedger record with one optional,
  closed ready_work_item object.
* Build that object only from a fully validated persisted ASSIGNED record.
* Persist parent and child in the same existing process-locked atomic file
  replacement.
* Return the immutable first-set object on duplicates and process races.
* Validate all parent/child bindings on every ledger load.
* Keep the child small: IDs, digests, epoch, and one first-set timestamp only.

### READY semantics

READY means exactly:

* a durable local work record exists;
* request/input, authority, assignment, candidate, and key-binding references
  are frozen;
* no worker has claimed the record;
* no reservation or lease exists;
* no mission, queue item, scheduler notification, cartridge, tool, LLM, Git,
  HealExecutor, or other side effect exists.

READY does not mean started, dispatched, owned, reserved, executable by a
particular worker, or externally acknowledged.

### Explicit non-goals

The following are not fields or behaviors of Slice 03:

* worker claims, worker ownership, reservations, leases, attempts, retries;
* mission, Sankalpa, queue, NADI, inbox, scheduler, or outbox creation;
* tool, LLM, cartridge, HealExecutor, Git, branch, commit, push, PR, or issue
  activity;
* execution results, logs, terminal state, verification, recovery automation;
* external READY, Assignment, Started, terminal, or Verification messages;
* Status Query, Managed-Task completion, Steward product changes, or runtime
  activation.

Those are separate future boundaries and must not be smuggled into the
admission ledger by this plan.

## 2. Reused persistence boundary

The implementation must extend, not replace, the existing:

* File: city/federation_v1.py
* Target owner: TargetAdmissionLedger
* Existing process lock: _process_lock
* Existing atomic exchange: _atomic
* Existing fail-closed loader: _load
* Existing assignment path: assign_candidate

The ledger already has:

* a per-instance threading.RLock;
* an inter-process fcntl lock;
* temporary-file write, flush/fsync, and os.replace;
* fail-closed malformed-file behavior;
* Slice-02 first-set assignment and immutable local attestation;
* process/crash/duplicate evidence.

No second Work Store, outbox, materializer, or authority owner is introduced.
No existing Sankalpa, queue, NADI, discussion, signal, discovery, router, or
cartridge store is adapted as a Work Item owner.

## 3. Closed READY object schema

The parent record gains one optional key:

~~~text
ready_work_item: object | null
~~~

For a valid READY child, the object field set is exactly the following. No
unknown fields, nested maps, arrays, null values, free-form metadata, logs, or
blobs are allowed.

~~~json
{
  "schema": "agent-city-federation-ready-work-item-v1",
  "work_item_id": "work_v1_<64 lowercase hex characters>",
  "state": "READY",
  "delegation_id": "<validated delegation id>",
  "target_work_id": "<parent target work id>",
  "assignment_epoch": 1,
  "request_message_id": "<parent request message id>",
  "request_message_hash": "<64 lowercase hex characters>",
  "input_digest": "<64 lowercase hex characters>",
  "assignment_authority_digest": "<64 lowercase hex characters>",
  "worker_snapshot_digest": "<64 lowercase hex characters>",
  "assigned_candidate_id": "<parent candidate id>",
  "candidate_snapshot_digest": "<64 lowercase hex characters>",
  "target_key_binding_digest": "<parent assignment key binding digest>",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "work_item_content_digest": "<64 lowercase hex characters>"
}
~~~

### Normative field rules

| Field | Type / limits | Source or derivation | Mutable after first commit |
| --- | --- | --- | --- |
| schema | fixed string, UTF-8, exactly agent-city-federation-ready-work-item-v1 | literal | no |
| work_item_id | fixed prefix work_v1_ plus 64 lowercase hex characters | deterministic typed hash in section 4 | no |
| state | fixed enum READY | literal | no |
| delegation_id | non-empty UTF-8 string, maximum 256 bytes | parent record and parent key | no |
| target_work_id | non-empty UTF-8 string, maximum 256 bytes | parent admission/assignment record | no |
| assignment_epoch | signed integer, 1 through 2^31-1; current Slice-02 value is 1 | parent assignment record | no |
| request_message_id | non-empty UTF-8 string, maximum 256 bytes | parent record | no |
| request_message_hash | exactly 64 lowercase ASCII hex characters | parent record | no |
| input_digest | exactly 64 lowercase ASCII hex characters | local semantic-input digest in section 5 | no |
| assignment_authority_digest | exactly 64 lowercase ASCII hex characters | parent record | no |
| worker_snapshot_digest | exactly 64 lowercase ASCII hex characters | parent record | no |
| assigned_candidate_id | non-empty UTF-8 string, maximum 256 bytes | parent assignment record | no |
| candidate_snapshot_digest | exactly 64 lowercase ASCII hex characters | digest of parent observed snapshot in section 5 | no |
| target_key_binding_digest | exactly 64 lowercase ASCII hex characters | parent assignment key binding digest | no |
| created_at | exact RFC-3339 UTC second form, 20 ASCII bytes | first successful commit input | no |
| work_item_content_digest | exactly 64 lowercase ASCII hex characters | digest of all other child fields in section 5 | no |

The child object has a closed field set. An implementation must reject any
missing, extra, null, float, noncanonical, oversized, or malformed value as
ledger corruption. The JSON storage indentation used by the parent ledger is
not the identity representation; all digest inputs use canonical_bytes.

Machine-checkable shape requirements are: JSON type object; exactly the 16
keys listed above; all 16 keys required; additionalProperties false;
nullable false for every field; no arrays or nested objects in the child; and
the scalar, enum, encoding, and size constraints in the table are normative.

### Size and retention limits

* Canonical child bytes must be at most 4096 bytes.
* Every non-digest identifier is at most 256 UTF-8 bytes.
* Every digest is exactly 32 bytes represented as 64 lowercase hex characters.
* No request payload, certificate, candidate object, log, result, or signature
  is duplicated into the child.
* The complete parent request and assignment evidence remain retained in
  the parent record.
* Slice 03 performs no cleanup, compaction, or evidence deletion.

## 4. Canonicalization and work_item_id

### Canonicalization

All local READY digests reuse the already frozen language-neutral SFDJ-1
canonical_bytes behavior in city/federation_v1.py:

* UTF-8 encoding;
* NFC strings only;
* object keys sorted by UTF-8 byte order;
* no duplicate JSON keys;
* integers only, signed 64-bit range;
* floats, NaN, Infinity, BOM, and noncanonical JSON rejected;
* canonical compact bytes, with the existing maximum wire-size guard.

The READY child itself is not a Federation wire envelope. Reusing this
canonicalizer avoids inventing a second local JSON identity algorithm; it does
not change the frozen external wire contract.

### Typed hash

For every digest below, typed_hash(domain, value) is:

~~~text
SHA-256(ASCII(domain) || 0x00 || canonical_bytes(value))
~~~

The resulting digest is lowercase hexadecimal. Domains are fixed ASCII
literals and are not caller-controlled.

### Deterministic work_item_id

The exact ID input object contains exactly these six keys:

~~~json
{
  "assignment_authority_digest": "<parent value>",
  "assignment_epoch": 1,
  "delegation_id": "<parent value>",
  "request_message_hash": "<parent value>",
  "target_work_id": "<parent value>",
  "worker_snapshot_digest": "<parent value>"
}
~~~

The keys are canonicalized by SFDJ-1. The ID is:

~~~text
digest = typed_hash(
  "agent-city-federation-ready-work-item-v1",
  id_input
)
work_item_id = "work_v1_" + digest
~~~

This is the exact implementation of the preferred typed-hash derivation. The
input_digest and created_at are deliberately not ID inputs: request/message
identity and assignment identity already determine the first-set Work Item.
A changed input digest or timestamp in an existing child is an integrity
conflict, not a new Work Item.

target_work_id remains the Federation/target correlation identifier. It is
never reused as work_item_id.

## 5. Input and evidence digests

### Parent evidence remains authoritative

The builder first loads and fully validates the parent. It must parse the
persisted request_wire_bytes_b64 from the parent, not regenerate a request and
not consult an external source. The original signed request bytes remain in
the parent and are not copied into READY.

request_message_hash alone is not sufficient as a local input binding: it
identifies the complete signed envelope, including transport and signature
fields, rather than the normalized local execution input. The parent
request_digest remains the Federation semantic binding. READY additionally
stores a local input_digest so a future local consumer can check the exact
input projection without duplicating the payload.

### Exact input projection

After full request validation, construct this in-memory projection:

~~~json
{
  "authority": "<validated request payload authority object>",
  "capability": "<validated capability>",
  "deadline": "<validated deadline>",
  "delegation_id": "<validated delegation id>",
  "expected_outcome": "<validated expected outcome object>",
  "intent": "<validated intent object>",
  "origin_task_id": "<validated origin task id>",
  "request_digest": "<validated request digest>",
  "target_repo": "<validated target repo>",
  "task_description": "<validated task description>",
  "verification_contract": "<validated verification contract object>"
}
~~~

The projection is only a digest input; it is not stored as a child map. Its
digest is:

~~~text
input_digest = typed_hash(
  "agent-city-federation-ready-input-v1",
  input_projection
)
~~~

This gives READY a stable local execution-input identity while retaining the
complete signed request only in the parent.

### Candidate snapshot digest

The parent observed_candidate_snapshot is canonicalized exactly as persisted.
The child stores only:

~~~text
candidate_snapshot_digest =
  typed_hash(
    "agent-city-federation-ready-candidate-snapshot-v1",
    parent.observed_candidate_snapshot
  )
~~~

worker_snapshot_digest remains the parent Slice-02 assignment digest and is
copied unchanged. The two digests have different domains and meanings; neither
is a claim of reservation or current availability.

### Content digest

Let child_without_content be the exact child object with
work_item_content_digest omitted. Then:

~~~text
work_item_content_digest =
  typed_hash(
    "agent-city-federation-ready-content-v1",
    child_without_content
  )
~~~

The field is then inserted. No signature is added to the child.

## 6. READY API and transition semantics

### Proposed local API

The only new public operation proposed for the implementation plan is:

~~~text
create_ready_work_item(delegation_id: str, created_at: str)
    -> (result_code: "created" | "duplicate", ready_work_item: object)
~~~

This is a target-local ledger method. It is not a Federation operation, not a
carrier, and not accepted by any Federation receipt handler.

created_at is required and must pass the existing exact UTC-second parser. The
first successful commit stores it. On duplicate, a later created_at is ignored
and the stored object is returned byte-for-byte according to canonical child
bytes.

### Exact operation order

1. Acquire the existing per-instance and inter-process ledger locks.
2. Load the complete document with the existing fail-closed validator.
3. Resolve the parent by delegation_id and validate its parent key binding.
4. If ready_work_item is present, validate the complete child and all
   parent/child invariants; return duplicate and the stored child.
5. If parent assignment_state is not ASSIGNED, raise stable
   V1Reject(assignment_required, ready_work_item).
6. Validate the complete persisted assignment attestation and provenance again
   as part of the parent load.
7. Parse and validate the persisted request wire bytes and build the exact
   input projection.
8. Derive candidate_snapshot_digest, input_digest, work_item_id, and content
   digest deterministically.
9. Set ready_work_item on the in-memory parent record.
10. Perform one existing _atomic replacement of the complete ledger document.
11. Return created and the just-persisted child.

The candidate source, CityRouter, MissionRouter, Worker Registry, Cartridge
Factory, Sankalpa, NADI, queue, scheduler, or any execution surface is never
read or called. Lazy migration means only this explicit method may add the
child; ordinary reads never rewrite old records.

### State relation

| Parent assignment_state | ready_work_item | API result |
| --- | --- | --- |
| ACCEPTED or legacy assignment view | absent | assignment_required |
| ASSIGNED and valid | absent | create and return READY |
| ASSIGNED and valid | valid matching child | duplicate and return stored READY |
| any | malformed child or mismatched parent | ledger_corrupt; no rebuild |
| REJECTED | absent | assignment_required; no child |

The parent assignment_state remains ASSIGNED after READY creation. READY is a
child state, not a replacement for the Federation assignment state.

## 7. Parent/child invariants and fail-closed validation

Every ledger load that contains ready_work_item must enforce all of these:

* parent map key equals parent delegation_id;
* parent state is ACCEPTED;
* parent assignment_state is exactly ASSIGNED;
* child field set equals the closed schema exactly;
* child schema and state equal the fixed literals;
* child delegation_id equals the parent delegation_id;
* child target_work_id equals the parent target_work_id;
* child assignment_epoch equals parent assignment_epoch;
* child request_message_id equals parent request_message_id;
* child request_message_hash equals parent request_message_hash;
* child assignment_authority_digest equals parent assignment_authority_digest;
* child worker_snapshot_digest equals parent worker_snapshot_digest;
* child assigned_candidate_id equals parent assigned_candidate_id;
* child target_key_binding_digest equals parent assignment_key_binding_digest;
* candidate_snapshot_digest recomputes from the parent snapshot;
* input_digest recomputes from the validated persisted request projection;
* work_item_id recomputes from the exact six-key ID input;
* work_item_content_digest recomputes from all other child fields;
* created_at is an exact valid UTC-second timestamp;
* no forbidden lifecycle field is present in the child;
* canonical child bytes are within the 4096-byte limit.

Forbidden child fields include worker_claim, owner, lease, reservation,
attempt, retry_count, queue_item_id, mission_id, scheduler_id, execution,
result, log, receipt, signature, verification, recovery, and any arbitrary
metadata map.

Any violation raises ledger_corrupt (or a narrower stable ready-integrity
code if the existing error taxonomy provides one). The implementation must
never silently rebuild, overwrite, or “repair” a malformed child.

## 8. Signature decision

No second READY signature is included.

The child is target-local, remains inside the already fail-closed
TargetAdmissionLedger, and binds through:

* the parent request and assignment digests;
* the parent provenance-bound assignment attestation;
* the copied target key binding digest;
* the child content digest and deterministic Work Item ID.

Adding a second signature would create a parallel cryptographic structure
without a new trust boundary or external consumer. If a later design exports
READY to another process, repository, or transport, the signature decision
must be reopened before that boundary is added.

## 9. Crash, duplicate, and process matrix

| Event | Required durable result | Required caller result |
| --- | --- | --- |
| crash before lock or before load | parent unchanged | next call retries normally |
| crash while validating/building, before _atomic | parent remains valid ASSIGNED; no child | next call may create |
| crash during temp write before replace | prior ledger remains; no partial child visible | next call may create |
| crash after replace before method return | complete child is present and validates | next call returns duplicate stored child |
| identical retry with later created_at | no new digest, ID, or timestamp | byte-identical stored child |
| two processes start from ASSIGNED | one lock holder commits | both callers receive the same first-set child; at most one child |
| second process sees READY after waiting | no candidate/source read | duplicate stored child |
| parent field changed after READY | load detects mismatch | ledger_corrupt; no rebuild |
| child field changed after READY | child digest/invariant fails | ledger_corrupt; no rebuild |
| assignment attestation invalid | parent validation fails first | no READY |
| no ASSIGNED parent | no child | assignment_required |
| legacy Slice-01A/Slice-02 record without child | read remains unchanged | explicit create may lazily add child |

The two-process test must use independent ledger instances or independent
processes against the same path, not only a single-thread mock. The
post-replace crash test must show that the complete child survives and
validates on a fresh ledger instance.

## 10. Legacy compatibility and migration

* Slice-01A and Slice-02 parent records without ready_work_item remain valid.
* The loader supplies no implicit child and performs no write on read.
* Only an explicit create_ready_work_item call may add the child.
* No historical parent evidence is rewritten, removed, or compacted.
* A rejected admission cannot receive a child.
* Existing assignment duplicate, corruption, and process-lock semantics remain
  unchanged.
* No Steward code or Origin ledger changes are required.
* The existing federation feature gate remains false and disposition remains
  disabled.

## 11. Planned wiring diff (documentation only)

No runtime wiring is changed by this plan branch. The intended future
capability entry is:

~~~json
{
  "operation": "target_local_ready_work_item",
  "direction": "Agent City target-local",
  "handler": "city.federation_v1.TargetAdmissionLedger.create_ready_work_item",
  "ledger": "city.federation_v1.TargetAdmissionLedger",
  "input": "validated ASSIGNED parent record",
  "output": "embedded ready_work_item state READY",
  "external_receipt": false,
  "worker_or_mission_call": false,
  "lifecycle_maturity": "declared",
  "disposition": "disabled"
}
~~~

This planned entry is not a runtime health value and must not be written into
the existing wiring manifest until implementation, tests, and evidence exist.
No manifest update is part of this plan branch.

## 12. Required implementation tests

The implementation PR must add or extend repo-local tests for all of the
following. These tests are plan requirements; none are claimed as executed by
this document.

1. A fully valid ASSIGNED parent creates exactly one READY child.
2. READY creation reads only persisted parent evidence; candidate source,
   CityRouter, MissionRouter, Worker Registry, and Cartridge Factory are
   forbidden and not called.
3. A duplicate call with a different later created_at returns the stored child
   byte-for-byte.
4. A real multiprocess race creates one child and both callers receive the
   same first-set data.
5. A crash before final replace leaves ASSIGNED unchanged and child absent.
6. A crash after replace leaves a complete, freshly loadable READY child.
7. A parent without ASSIGNED raises assignment_required.
8. A malformed or foreign assignment attestation prevents READY.
9. Mutated work_item_id, input_digest, candidate_snapshot_digest, authority
   digest, target key binding, or content digest fails closed.
10. Parent/child delegation, target work, epoch, request ID/hash, candidate,
    authority, or key-binding mismatch fails closed.
11. Missing child fields, extra child fields, nulls, floats, noncanonical
    strings, oversized IDs, and oversized child bytes fail closed.
12. Slice-01A and Slice-02 records remain readable before explicit READY
    creation.
13. No Mission, Sankalpa, NADI, queue, scheduler, cartridge, HealExecutor,
    Tool, LLM, Git, or PR function is invoked.
14. Existing Slice-01A/Slice-02 federation and legacy regressions remain green.
15. Feature gate remains false by default and disposition remains disabled.
16. No external carrier, receipt, Steward Origin update, or wire fixture is
    emitted.

## 13. Verification and rollout sequence

The future implementation must follow this order:

1. Re-pin Agent-City main and confirm this plan commit plus the accepted recon.
2. Implement the closed child validator and pure digest builders.
3. Implement the locked first-set API inside TargetAdmissionLedger.
4. Add crash, duplicate, corruption, process, legacy, and no-side-effect tests.
5. Run focused tests, full Slice-01A/Slice-02 suites, and legacy regressions.
6. Verify the diff contains no Steward change, wire change, manifest runtime
   import, activation, or forbidden caller.
7. Produce a self-contained Agent-B implementation-review packet with exact
   commit, test results, and crash/process evidence.
8. Do not merge or activate until Agent-B accepts the implementation diff.

No cross-repository Crucible is needed for this slice because the child never
crosses the repository boundary. A later Started slice must not be designed
until READY has been proven and a separate durable Work/Scheduler boundary is
accepted.

## 14. Definition of Done

Plan 03 is implementation-ready only when an implementation PR can prove:

* the schema field set is closed and mechanically validated;
* every child field is copied, derived, or first-set exactly as specified;
* work_item_id, input_digest, candidate_snapshot_digest, and
  work_item_content_digest are reproducible from persisted evidence;
* no second signature or wire object was introduced;
* ASSIGNED remains the parent Federation state and READY is only the child
  state;
* parent/child mismatches, corruption, missing assignment, and forbidden
  lifecycle fields fail closed;
* pre-commit and post-commit crash behavior is demonstrated;
* duplicate and independent-process races produce one first-set child;
* old parent records remain readable and are not rewritten on read;
* no candidate/router/worker/mission/queue/scheduler/tool/LLM/Git call occurs;
* no external message, receipt, Steward code, or wire contract changed;
* feature gate is false, disposition disabled, and no productive activation;
* the implementation diff and evidence are independently reviewed by Agent B.

## 15. Agent-B review gate

Agent B must review this plan before any product implementation and answer:

1. Is the closed child schema complete, minimal, and free of hidden lifecycle
   semantics?
2. Are the canonicalization, domain-separated digests, and deterministic
   work_item_id fully reproducible and unambiguous?
3. Is input_digest’s projection correct, and does it avoid duplicating parent
   payload while preserving future integrity checks?
4. Do parent/child invariants and fail-closed rules cover every mutation and
   malformed-record path?
5. Does the existing TargetAdmissionLedger provide a truly atomic and
   process-safe boundary for this child without a second store?
6. Are crash, duplicate, and multiprocess expectations testable as written?
7. Does the no-signature decision remain correct for this target-local object?
8. Are size, retention, lazy migration, and legacy compatibility explicit
   enough to prevent accidental rewrites or evidence loss?
9. Does the planned wiring remain documentation-only and feature-gated?
10. Is the plan ready for implementation, or must it return for a targeted
    revision before code?

Decision required before code: ACCEPTED FOR IMPLEMENTATION SLICE 03 or
REVISION REQUIRED. This plan itself makes no implementation authorization.
