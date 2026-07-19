# Federation Delegation Slice 03 — Implementation Review Packet

## 1. Evidence and pins

Repository: `kimeisele/agent-city`

Implementation branch: `impl/federation-delegation-slice-03-ready-work-item`

Agent-City `main` base at implementation start:

`5acf648075643af575be0ad57be9960da02f3999`

Accepted Slice-03 plan pin:

`268f94b35bd28a2db88efa773102e8c60e385aaa`

Accepted Slice-03 recon/main pin:

`5acf648075643af575be0ad57be9960da02f3999`

Product/test implementation commit:

`51ab9dbe49a9ebeac9451d3d895f3ff0d1a5bd80`

This packet is documentation-only and records the implementation commit above;
it does not change the product scope described below.

## 2. Exact implementation scope

The implementation adds one target-local operation:

```text
TargetAdmissionLedger.create_ready_work_item(delegation_id, created_at)
```

Its only transition is:

```text
validated ASSIGNED parent
    -> one embedded ready_work_item with state READY
```

`READY` means only that a small, immutable local work record exists. It does
not mean started, dispatched, claimed, reserved, leased, scheduled, executable
by a worker, or externally visible.

Changed product/test files in `51ab9dbe49a9ebeac9451d3d895f3ff0d1a5bd80`:

* `city/federation_v1.py`
* `tests/test_federation_v1_ready_work_item.py`

The accepted plan remains versioned separately at
`docs/FEDERATION_DELEGATION_SLICE_03_IMPLEMENTATION_PLAN.md` (plan commit
`268f94b35bd28a2db88efa773102e8c60e385aaa`).

No Steward, agent-federation, agent-internet, Federation carrier, Federation
receipt, Golden Fixture, legacy NADI, MissionRouter, CityRouter, TaskManager,
Sankalpa, queue, scheduler, worker, cartridge, HealExecutor, Tool, LLM, Git,
PR, workflow, or managed-task path was changed.

No wiring manifest, runtime health state, Context Bridge, Provider Failover,
Execution-Spine document, or activation setting was changed. The existing
feature gate remains default `false`; the capability remains disposition
`disabled`.

## 3. Closed READY schema

The parent target-ledger record may contain one optional `ready_work_item`.
When non-null, its field set is exactly these 16 keys; no extra fields, maps,
arrays, nulls, logs, payload copies, signatures, receipts, or lifecycle fields
are accepted:

```json
{
  "schema": "agent-city-federation-ready-work-item-v1",
  "work_item_id": "work_v1_<64 lowercase hex characters>",
  "state": "READY",
  "delegation_id": "<parent delegation id>",
  "target_work_id": "<parent target work id>",
  "assignment_epoch": 1,
  "request_message_id": "<parent request message id>",
  "request_message_hash": "<64 lowercase hex characters>",
  "input_digest": "<64 lowercase hex characters>",
  "assignment_authority_digest": "<parent assignment authority digest>",
  "worker_snapshot_digest": "<parent worker snapshot digest>",
  "assigned_candidate_id": "<parent candidate id>",
  "candidate_snapshot_digest": "<64 lowercase hex characters>",
  "target_key_binding_digest": "<parent key-binding digest>",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "work_item_content_digest": "<64 lowercase hex characters>"
}
```

The child is bounded to 4096 canonical bytes. Identifiers are non-empty UTF-8
strings up to 256 bytes. Digests are lowercase SHA-256 hex. Timestamps use
the existing exact UTC-second parser. The parent request and assignment
evidence remain retained; the child stores only IDs and digest bindings.

## 4. Deterministic derivations

All derivations use the existing language-neutral `canonical_bytes` behavior:
UTF-8, NFC strings, UTF-8 byte-sorted object keys, duplicate-key rejection,
integer-only signed 64-bit numbers, and no floats, NaN, Infinity, or BOM.

The six-key Work Item ID input is exactly:

```json
{
  "assignment_authority_digest": "<parent>",
  "assignment_epoch": 1,
  "delegation_id": "<parent>",
  "request_message_hash": "<parent>",
  "target_work_id": "<parent>",
  "worker_snapshot_digest": "<parent>"
}
```

```text
work_item_id = "work_v1_" +
  SHA256(
    ASCII("agent-city-federation-ready-work-item-v1") || 0x00 ||
    canonical_bytes(six_key_input)
  ).hexdigest()
```

The other local typed domains are:

```text
agent-city-federation-ready-input-v1
agent-city-federation-ready-candidate-snapshot-v1
agent-city-federation-ready-content-v1
```

`input_digest` is over the exact projection of the persisted, authenticated
delegate-task request containing `authority`, `capability`, `deadline`,
`delegation_id`, `expected_outcome`, `intent`, `origin_task_id`,
`request_digest`, `target_repo`, `task_description`, and
`verification_contract`. The complete request bytes stay in the parent.

`candidate_snapshot_digest` is over the persisted Slice-02 observed candidate
snapshot. `worker_snapshot_digest` remains the parent Slice-02 digest and is
not replaced. `work_item_content_digest` is over all child fields except
itself, with the READY content domain.

No second READY signature is introduced. The child remains inside the
fail-closed target ledger and is bound to the parent request, assignment
attestation, target-key binding, and all derived digests.

## 5. Validation and atomicity

`FederationV1Admission` binds the typed origin-key registry to the target
ledger. Before creating READY, the ledger:

1. takes the existing thread and inter-process locks;
2. loads and fully validates the target document, assignment provenance, and
   existing assignment attestation;
3. returns the existing child unchanged if one is already present;
4. requires parent `state=ACCEPTED` and `assignment_state=ASSIGNED`;
5. parses the persisted canonical request bytes, rechecks the request hash,
   target/source/root IDs, request digest, idempotency binding, and—when the
   typed registry is bound—the original Ed25519 envelope signature;
6. derives all child IDs and digests without reading any candidate source;
7. writes the updated parent and child in one existing atomic file replace.

The first successful commit is authoritative. A later call with another
`created_at`, another process, or another ledger instance returns the stored
child and does not regenerate timestamps, IDs, digests, or bytes. A malformed
existing child or parent fails closed as `ledger_corrupt`; it is never rebuilt.

The method does not call candidate adapters, routers, Mission/Sankalpa,
queues, schedulers, NADI, carrier builders, relay code, or execution surfaces.

## 6. Boundary and negative evidence

The new test module proves:

* closed 16-field schema and deterministic READY creation;
* first-set duplicate behavior with a later timestamp;
* two independent processes and two ledger instances produce one child;
* crash before replace leaves ASSIGNED without READY;
* crash after replace leaves a fresh, valid READY child;
* missing ASSIGNED returns `assignment_required`;
* invalid assignment attestation and mutated persisted request bytes prevent
  READY;
* mutated work ID, input digest, candidate digest, authority digest, key
  binding, content digest, malformed scalars, missing fields, and extra fields
  fail closed;
* candidate, carrier, relay, and transport surfaces are not called;
* the canonical READY object is rejected as a Federation envelope and cannot
  be treated as a carrier;
* request and assignment wire bytes are unchanged by READY creation;
* the default feature gate remains false and no activation is performed.

`ready_work_item` is not added to any Federation top-level or payload schema,
carrier, receipt, or relay shape. It is never serialized or transmitted.

## 7. Validation results

Commands and measured results on the implementation branch:

```text
ruff check city/federation_v1.py tests/test_federation_v1_ready_work_item.py
  All checks passed

python -m py_compile city/federation_v1.py tests/test_federation_v1_ready_work_item.py
  passed

pytest -q tests/test_federation_v1_ready_work_item.py
  23 passed, 1 warning

pytest -q tests/test_federation_v1_admission.py \
  tests/test_federation_v1_assignment.py \
  tests/test_federation_v1_ready_work_item.py
  70 passed, 1 warning

pytest -q tests/test_federation_v1_assignment.py \
  tests/test_federation_v1_admission.py \
  tests/test_federation_v1_hardening.py \
  tests/test_federation_nadi.py tests/test_federation_relay.py tests/federation_v1
  178 passed, 1 warning

pytest -q tests/test_mission_router.py tests/test_city_router.py \
  tests/test_federation_nadi.py tests/test_federation_relay.py tests/test_layer4.py
  144 passed, 184 warnings
```

A repository-wide `pytest -q` was also attempted. Collection stops at an
unrelated pre-existing import error in `tests/test_campaign_recruitment.py`:
that test imports `_detect_recruitment_gap`, which is absent from
`city/hooks/dharma/campaign_recruitment.py`. No file in this implementation
touches that module or test. The scoped Federation and legacy suites above
are the relevant green gates.

## 8. Activation and ownership boundaries

This commit does not add a caller, scheduler, worker, queue, mission, or
external receipt. `READY` is not `started`; no local or external side effect
is performed. Feature gate default is `False`, and the existing capability
disposition remains `disabled`. No production activation occurred.

The next external `started`, status, terminal, or verification message still
requires the previously mandated cross-repository protocol-ownership review
covering agent-federation, Steward, Agent City, and any transport/discovery
repository. This local READY commit does not pre-authorize that work.

## 9. Agent-B review request

Please review commit `51ab9dbe49a9ebeac9451d3d895f3ff0d1a5bd80` against the
accepted Plan-03 pin and answer:

1. Is the 16-field child schema and six-key ID derivation exactly closed and
   reproducible?
2. Are request projection, candidate digest, content digest, and parent/child
   bindings sufficient without duplicating payload or adding a signature?
3. Does the existing TargetAdmissionLedger provide the required atomic and
   process-safe first-set boundary?
4. Do the crash, corruption, duplicate, and multiprocessing tests prove the
   claimed semantics rather than only a single-process mock?
5. Do the transport-boundary tests demonstrate that READY cannot become a
   Federation message or receipt?
6. Are all forbidden execution and activation paths unchanged?
7. Is the unrelated full-suite collection error correctly isolated from this
   implementation?

No merge or activation is requested by this packet; it is the implementation
evidence for the explicit Agent-B review gate.
