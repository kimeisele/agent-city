# Federation Delegation Slice 03 — Existing Work-Item Surface Recon

**Status:** READ-ONLY RECON COMPLETE — NO PRODUCT IMPLEMENTATION AUTHORIZED
**Repository:** kimeisele/agent-city
**Authoritative Agent-City main:** 84b0f45df124c5374747474da0d7043b498280ab
**Slice-02 product merge:** 09ea3d3770fa126936756becec2eb6b0493a1a13
**Recon branch:** recon/federation-delegation-slice-03-work-item-surface
**Recon date:** 2026-07-19

This document is the complete, versioned evidence package for the Slice-03
Existing Work-Item Surface Recon. It records what exists at the pinned
Agent-City main, what it actually persists, and which existing boundaries may
be reused for a later, separately reviewed ASSIGNED -> READY implementation.
It does not add a Work Item, change a state machine, introduce a wire object,
or activate any path.

## 1. Scope, truth rules, and pins

### Requested transition

The next desired transition is deliberately narrower than execution:

~~~text
validated ACCEPTED admission
    -> exactly one durable target-local Work Item
    -> READY
~~~

For this recon, READY is only a proposed future local state meaning:

* an executable work record exists durably;
* its inputs and authority snapshot are frozen;
* no worker has claimed it;
* no reservation or lease exists;
* no mission, queue execution, scheduler action, tool, LLM, Git, or other
  external side effect has occurred.

The current Slice-02 state remains strictly ASSIGNED. ASSIGNED means a
target-local candidate observation and signed assignment attestation were
persisted; it does not mean work, start, or ownership.

### Authoritative pins and external dependency pin

| Evidence | Pin / result |
| --- | --- |
| Agent City main | 84b0f45df124c5374747474da0d7043b498280ab |
| Slice-02 product merge | 09ea3d3770fa126936756becec2eb6b0493a1a13 |
| Slice-02 final docs/main merge | 84b0f45df124c5374747474da0d7043b498280ab |
| Steward Protocol checkout inspected read-only | c51196d9e906c2e993d3548db6ef891b184b0b24 |
| Agent City remote refs/heads/main | matched 84b0f45df124c5374747474da0d7043b498280ab during recon |
| Working tree before documentation | only pre-existing untracked .claude/; not inspected as a Slice artifact and not changed |

The Steward Protocol checkout contained unrelated local state and was not
modified. It is cited only to identify the upstream Sankalpa types and
registry behavior used by Agent City.

### History method

The history overview used an explicit first-parent, all-ref log with both
--invert-grep --grep='heartbeat' --grep='Heartbeat' and path exclusions for
heartbeat-named files. Heartbeat commits were therefore excluded from the
signal used for this recon. The resulting recent non-heartbeat chain includes
the Slice-02 merge, its implementation commits, the Slice-01 merge, and the
Golden-Wire fixture commits; no heartbeat-only commit is used as evidence here.

### Existing post-merge evidence

The final Slice-02 smoke evidence is pinned in
docs/PHASE2_FEDERATION_DELEGATION_SLICE_02_STATUS.md and the Slice-02 review
packet at this same main:

* Federation/Slice suites: 178 passed;
* Legacy/Mission/Heal suites: 144 passed;
* focused crash/retry/process/corruption cases: 9 passed;
* Ruff, py_compile, JSON and diff checks: passed;
* FEDERATION_V1_DELEGATION_ENABLED=false by default;
* disposition disabled;
* no productive activation.

These are historical milestone observations, not current dynamic health
claims. The wiring manifests remain documentation-only; a repository search
at the pin found no non-doc runtime import or consumption of them.

## 2. Current Slice-02 sequence (the actual live path)

~~~mermaid
sequenceDiagram
    participant O as Steward V1 origin
    participant C as V1 request/receipt carrier
    participant A as Agent City FederationV1Admission
    participant L as TargetAdmissionLedger
    participant S as CandidateSnapshotAdapter
    participant K as validated target key registry

    O->>C: signed delegate_task request
    C->>A: exact target ingress
    A->>K: provenance, authority and target-key validation
    A->>L: atomic ACCEPTED admission + admission receipt
    Note over L: Slice-01A target_work_id exists
    A->>L: assign_candidate(delegation_id)
    L-->>A: existing ASSIGNED record, or continue
    A->>S: read-only observe (first)
    A->>S: read-only observe (second)
    S-->>A: candidate + source_generation snapshots
    A->>K: bind attestation to validated target signing key
    A->>L: one atomic ASSIGNED record + local signed attestation
    L-->>A: byte-identical first-set record on duplicate/race
    A-->>O: no external assignment/started message in Slice 02
~~~

The current path ends at the target-local ASSIGNED record. The assignment
tests explicitly assert that no mission_id, queue_item_id, or execution
result is written and that MissionRouter and HealExecutor are not called
(tests/test_federation_v1_assignment.py:414-430).

## 3. Exact Slice-02 persistence boundary

### TargetAdmissionLedger

**File/symbol:** city/federation_v1.py:1286 TargetAdmissionLedger
**Relevant symbols:** _process_lock (:779), _atomic (:789), _load
(:811), commit (:1337), assign_candidate (:1392).

Observed contract at the pin:

* path-backed JSON document with delegations and findings;
* per-instance threading.RLock plus an inter-process fcntl.flock lock file;
* _atomic writes a temporary file, flushes/fsyncs, then uses os.replace;
* an existing but malformed document raises V1Reject("ledger_corrupt", ...);
* ACCEPTED records already contain the Slice-01A target_work_id;
* Slice-02 adds assignment_state, fixed assignment_epoch=1, candidate
  snapshot, source generation, candidate/authority/key-binding digests,
  assignment time, and complete signed local attestation bytes;
* ASSIGNED retries return the stored record without reading the candidate
  source again;
* the assignment commit stores all assignment fields and attestation material
  in one replacement of the ledger document;
* no work_item_id, READY, mission, queue item, reservation, lease, worker
  claim, or started receipt exists in this record today.

The existing tests supply direct evidence for the boundary:

| Test | Observed proof |
| --- | --- |
| test_acceptance_becomes_one_target_local_assigned_attestation | ACCEPTED -> ASSIGNED, epoch 1, existing target_work_id, complete local attestation |
| test_duplicate_retry_uses_stored_assignment_without_source_read | an already-ASSIGNED retry does not invoke the candidate source |
| test_process_race_with_different_times_returns_first_set_bytes | two process attempts return identical first-set evidence |
| test_two_independent_processes_create_one_assignment | process-level lock prevents two assignments |
| test_crash_before_assignment_commit_leaves_accepted_without_evidence | pre-commit crash leaves ACCEPTED and no assignment evidence |
| test_crash_after_assignment_commit_leaves_complete_assigned_evidence | post-commit crash leaves a complete valid ASSIGNED record |
| test_assignment_does_not_call_dispatch_or_execution_surfaces | no MissionRouter/HealExecutor call, no queue/execution fields |
| test_assignment_attestation_is_not_a_federation_receipt | local attestation has no federation operation/carrier semantics |

This is the strongest existing persistence boundary for Slice 03. It is also
the only inspected surface that already combines provenance validation,
first-set deduplication, process locking, fail-closed corruption behavior, and
atomic durable evidence.

## 4. Surface inventory and reuse matrix

| Surface | File / symbols | Durable object and IDs today | Current status model | Persistence / concurrency | Side-effect boundary | Slice-03 suitability |
| --- | --- | --- | --- | --- | --- | --- |
| Target admission | city/federation_v1.py:1286 TargetAdmissionLedger; FederationV1Admission.assign_candidate | delegation_id, request/receipt IDs, existing target_work_id, assignment_epoch; no work_item_id | ACCEPTED, ASSIGNED; no READY | JSON, fail-closed load, fcntl process lock, RLock, fsync + os.replace, duplicate first-set | No mission/queue/worker call in assignment path | Best existing boundary; a narrow embedded READY object is technically plausible, but not yet implemented |
| Mission routing | city/mission_router.py:221 route_mission; RoutingResult | transient agent_name and score; no ID or record | return result only; no lifecycle | pure function, no persistence or lock | Selection/scoring only; does not create work | Adapter/source only, never Work owner |
| City routing index | city/router.py:38 CityRouter; register, remove, agents_for_requirement | in-memory agent names and index keys | registered/removed in memory | MahaAttention + dict/set; no durable snapshot, lock, or crash recovery | Query only; registration changes in-memory index | Read-only candidate source only; cannot own READY |
| Sankalpa mission registry | upstream will.py:83 SankalpaRegistry; Agent City city/missions.py factories | SankalpaMission.id, title/name, owner; IDs often heartbeat/title based | active, paused, completed, abandoned | .vibe/state/sankalpa.json; temp replace but no process lock; malformed state logs warning and reinitializes defaults | add_mission creates active missions later consumed by KARMA/MOKSHA; mission paths can invoke cartridges, HealExecutor, Git/PR | Reject for Slice 03 without a breaking semantic adaptation |
| Mission lifecycle | city/karma_handlers/sankalpa.py; city/hooks/moksha/mission_lifecycle.py | mission IDs and status | active -> completed/abandoned and hygiene | delegates to Sankalpa registry | Routing, cartridge processing, healing, PRs, rewards, issue closure | Explicitly locked; cannot be triggered by READY |
| Heal executor | city/heal_executor.py:75 FixResult, HealExecutor | result/PR fields, not durable work ID | success/escalate | no work ledger; subprocess/git paths | ruff --fix, healer mutation, branch/commit/push/PR | Prohibited execution surface; not an input model |
| City NADI / gateway queue | city/nadi_hub.py:50 CityNadi; city/membrane.py:286 queue_item; city/phases/__init__.py queue | NadiMessage payload, optional correlation; list/deque item, no durable work ID | pending/drained; TTL filtered | LocalNadi memory; fallback Python list; no durable crash contract | GatewayKarmaHandler drains and calls gateway/DM/discussion handling | Transport/ingress only; cannot own READY |
| Federation NADI | city/federation_nadi.py:41 FederationMessage, FederationNadi | source/target/operation/correlation/timestamp; no durable Work ID | outbox/inbox, expired/processed | JSON temp replace but no writer lock; malformed file reads as empty; dedupe is in-memory source:timestamp | transport and federation signal processing; not local work | Explicitly not a work store |
| Agent NADI | city/agent_nadi.py:57 AgentNadiManager | per-agent deque message, correlation only | pending/drained/TTL | in-memory deque; restart loses items | messaging only | Not suitable |
| Discussion thread ledger | city/thread_state.py:154 ThreadStateEngine | comment ID, discussion number, body hash; thread/comment status | thread active/waiting/cooling/archived; comment seen/enqueued/replied/self | SQLite WAL, per-instance RLock; domain-specific comment lifecycle | re-enqueue feeds gateway; replies are external effects | Durable input history, not generic Work owner |
| Discussion state store | city/discussions_state.py:53 DiscussionsStateStore | comment/cursor/content hash and outbound comment dedup | pending/sent cursors | SQLite + RLock, no explicit cross-process lock/CAS | reserves and confirms external discussion posts | Side-effect-specific; not suitable |
| Signal state ledger | city/signal_state_ledger.py:27 SignalStateLedger | signal ID, topic, post ID | processed/broadcast/replied | SQLite + thread lock; no explicit process coordination | communication dedupe only | Not suitable |
| Discovery ledger | city/discovery_ledger.py:30 DiscoveryLedger | repository full name, propagation gap ID | discovered/processed/evaluated | SQLite + thread lock; no Work Item schema or process contract | discovery/scanning state | Not suitable |
| Cartridge registry/factory | city/cartridge_loader.py:27; city/cartridge_factory.py:107 | agent/cartridge name and in-memory instance/spec | available/loaded/generated | in-memory caches; no durable IDs/state | get/process may instantiate or execute cognitive pipeline | Read-only metadata source only; never call for READY |
| TaskManager / generic Job / WorkItem | repo-wide search at pin (city, tests) | no matching implementation or schema found | none | none | none | Does not exist in Agent City main; must not be assumed |

The matrix distinguishes “durable” from “usable as a Work Item.” Several
SQLite ledgers are durable but own a different domain and have no immutable
input/authority/work lifecycle. Conversely, the router and cartridge surfaces
have useful facts but no persistence.

## 5. IDs, states, and binding gaps

### Existing IDs that can be reused

* delegation_id is the stable federation semantic root.
* request_message_id and request_message_hash are persisted in the target
  admission record.
* target_work_id is already assigned by Slice 01A and is first-set/duplicate
  checked at admission receipt correlation.
* assignment_epoch=1 and assignment_authority_digest bind the Slice-02
  candidate assignment.
* assigned_candidate_id, observed_candidate_snapshot,
  source_generation, and worker_snapshot_digest are persisted for the
  target-local candidate observation.

### Missing Work-Item identity and state

No work_item_id, Work Item schema, READY status, input digest, immutable
work-record digest, or READY dedupe key exists in Agent City main. The
existing target_work_id is a federation/target correlation identifier; it
must not silently be re-described as proof that a local executable Work Item
already exists.

The following are not equivalent to READY:

* a router-selected agent name;
* a cartridge object in memory;
* an active Sankalpa mission;
* an item in gateway_queue or a NADI inbox;
* a thread_state.comment_ledger row with enqueued;
* an ASSIGNED candidate snapshot.

### Authority and capability facts

Slice 02 freezes an assignment_authority_digest and a candidate snapshot. The
snapshot is an observation with a source_generation and observed_at; it is not
a reservation, lease, ownership claim, or guarantee that the candidate is
still available. A future READY builder must carry these facts as immutable
inputs and must not invoke a router or worker to “confirm” them.

## 6. Persistence, lock, and crash matrix

| Surface | Missing file | Existing corruption | Atomic write | Thread safety | Inter-process safety | Duplicate / crash meaning |
| --- | --- | --- | --- | --- | --- | --- |
| TargetAdmissionLedger | creates a new valid document on first use | ledger_corrupt; no reset | temp file, fsync, os.replace | RLock | explicit fcntl lock | first-set record survives; duplicates return stored bytes; pre-commit crash leaves prior state |
| SankalpaRegistry | initializes default missions and saves them | warning + defaults (_init_defaults), not fail-closed | temp replace | none documented | none | ID-level mission overwrite; no process-safe immutable first-set contract |
| ThreadStateEngine | SQLite schema created | SQLite error behavior; no Work Item corruption contract | SQLite transaction/WAL | RLock | SQLite locking exists, but no explicit application-level multi-process contract for this use | comment IDs dedupe; stale comments can be re-enqueued, intentionally not immutable work |
| DiscussionsStateStore | SQLite schema created | SQLite error behavior; no Work Item corruption contract | SQLite transaction | RLock | no explicit process lock/CAS | content-hash reservation has TTL and is intentionally repeatable |
| SignalStateLedger / DiscoveryLedger | SQLite schema created | no fail-closed Work Item validation | SQLite commit | Lock | no explicit process lock | INSERT OR IGNORE domain dedupe only |
| FederationNadi | empty list | malformed JSON becomes empty list | temp replace | no lock on object | no writer lock; scanner separately locks its read/modify path | in-memory source+timestamp dedupe; restart can replay |
| CityNadi / AgentNadiManager | empty/in-memory | not applicable | not durable | object-local | none | TTL/drain semantics; restart loses pending items |
| runtime JSON snapshots | usually skipped or warning | warning/skip in several restore paths | direct write_text in runtime helpers | none | none | snapshots are not a Work Item contract |

Only TargetAdmissionLedger meets all currently demonstrated Slice-02
requirements: fail-closed corruption, process lock, atomic first-set commit,
and duplicate return of immutable stored evidence.

## 7. Side-effect and caller matrix

| Caller/surface | What creation or use does | Side effect risk for READY | Recon decision |
| --- | --- | --- | --- |
| TargetAdmissionLedger.assign_candidate | reads two candidate snapshots, computes digests, signs local attestation, commits JSON | no mission/queue/worker call in current tests | reusable as input boundary; a future READY commit must remain under the same lock and must not reread a source after ASSIGNED |
| MissionRouter.route_mission | pure capability gate and score; returns best agent name | no persistence, but result can be fed into execution by callers | never call from READY creation; candidate facts are already frozen in Slice 02 |
| CityRouter.register/remove | mutates in-memory capability indices | registration/removal changes routing availability | only a read-only snapshot source in a later explicitly reviewed adapter; not owner |
| SankalpaRegistry.add_mission / city.missions.* | persists an active mission; IDs can depend on heartbeat/title | downstream KARMA scans active missions and may execute cartridges/heals | do not adapt for READY in Slice 03; would import active-mission semantics and side effects |
| SankalpaHandler._process_issue_missions | scans active missions, routes and executes issue/exec work | cartridge process, HealExecutor, issue close, PR path | locked out |
| HealExecutor.execute_heal/create_fix_pr | runs Ruff/healer/subprocess/Git/PR | direct repository and network side effects | locked out |
| CityNadi.enqueue / gateway_queue.append | creates transient inbound message | later drain invokes gateway/DM/discussion handling | not a Work Item; no enqueue on READY commit |
| FederationNadi.emit/flush | writes transport outbox | external transport/relay semantics | no external message in Slice 03 |
| ThreadStateEngine.mark_enqueued | marks a discussion comment and later re-enqueues stuck comments | gateway response path is activated | not a generic work record |
| CartridgeFactory.get/process | returns or runs a cartridge | cognitive processing and possible downstream action | do not call for READY |

The existing Slice-02 no-side-effect test is important evidence, but it does
not prove that any later Work Item model exists. It proves only that the
current assignment boundary has not accidentally entered these callers.

## 8. Candidate surfaces in detail

### MissionRouter and CityRouter

city/mission_router.py declares itself a pure function module. route_mission
receives a mission-like object, specs, active agents, optional inventories,
and an optional CityRouter; it returns a RoutingResult with agent_name, score,
blocked count, and candidate count. Tests tests/test_mission_router.py:221-290
cover best-fit, blocked, inactive, and unknown-prefix behavior. No record is
created.

city/router.py:38 is an in-memory O(1) index over capability/domain/tier/
protocol/guardian keys. register overwrites an existing name and remove
removes it on freeze/archive/death. Tests tests/test_city_router.py:131-242
cover set intersections and router integration. There is no durable source
generation, snapshot version, lock, or crash recovery. A router output is
therefore a candidate fact, not a Work Item.

### Sankalpa and mission models

Agent City mission factories in city/missions.py call
ctx.sankalpa.registry.add_mission and construct active SankalpaMission
objects. IDs include heartbeat, issue, proposal, signal, or discussion
identity (for example heal_<contract>_<heartbeat> and
issue_<number>_<heartbeat>). This is a mission lifecycle, not an immutable
federation work lifecycle.

At upstream pin c51196d..., SankalpaMission has id, name, description,
priority, status, strategies, timestamps, and owner; its status enum is
ACTIVE, PAUSED, COMPLETED, ABANDONED. The registry uses
.vibe/state/sankalpa.json, writes through a temporary file, but has no
inter-process lock and treats a load error as “using defaults.” This violates
the fail-closed and immutable first-set requirements for READY. More
importantly, the KARMA handler scans active missions and can invoke cartridges,
HealExecutor, Git, issue resolution, and reward hooks. Reusing it would alter
legacy mission semantics and breach the no-side-effect gate.

### Heal, worker, and cartridge surfaces

city/heal_executor.py is explicitly an execution adapter. FixResult and
PRResult are outcome views, not persisted work records. execute_heal can run
Ruff, invoke immune/healing logic, and create_fix_pr can branch, commit, push,
and open a PR.

CityCartridgeLoader and CartridgeFactory maintain in-memory availability,
loaded, and generated caches. CartridgeFactory._make_agent_class exposes a
process method that invokes Buddhi and returns a cognitive result. Neither
has a durable Work Item, immutable input digest, or process-safe dedupe.

### Queues, inboxes, NADI, and discussion state

city/membrane.py:286 turns an ingress object into CityNadi.enqueue or an
in-memory gateway_queue append. GatewayKarmaHandler.execute drains those
items at city/karma_handlers/gateway.py:79-159 and calls the gateway,
discussion handlers, DM sender, or other action paths. The queue item is
therefore an execution trigger, not a READY record.

CityNadi wraps LocalNadi and drains priority/TTL-filtered messages;
AgentNadiManager is a set of per-agent deques. FederationNadi is a file
transport with TTL, bounded buffers, and source/timestamp in-memory dedupe.
None owns a stable work ID or authority snapshot. NadiInboxScannerHook
(city/hooks/genesis/nadi_inbox_scanner.py:54-167) verifies and executes
federation signals through IntentExecutor; it is explicitly not a passive
Work Item materializer.

ThreadStateEngine is the closest existing durable input queue: comments are
stored in SQLite with seen -> enqueued -> replied and can be re-enqueued
after 15 minutes. It is tied to GitHub Discussion identity and intentionally
feeds the gateway. It cannot be repurposed as a generic federation Work Item
without changing domain semantics and introducing side effects.

## 9. Atomically possible design variants

### Variant A — ledger-internal embedded Work Item

Extend the existing TargetAdmissionLedger record with a narrowly namespaced
optional object, for example ready_work_item, only after a separate plan and
schema review. The builder would consume a validated ASSIGNED record and
persist, under the same RLock + process lock and one atomic replacement:

* deterministic work_item_id;
* state=READY;
* the original delegation_id, target_work_id, and assignment_epoch;
* immutable request/input digest references;
* immutable authority digest and candidate snapshot reference;
* a work-record/content digest;
* creation timestamp and schema version;
* no worker claim, reservation, lease, queue ID, mission ID, or execution
  result.

**Advantages:** reuses the only proven fail-closed, process-safe, atomic
first-set boundary; no dual-write gap; a crash before commit leaves ASSIGNED
only; a crash after commit leaves the complete READY record; duplicate calls
return the stored first-set bytes.

**Risks:** the admission ledger gains a small work-record responsibility and
could grow in scope; the exact READY schema and deterministic ID still need an
ADR/implementation plan; future worker lifecycle may eventually deserve a
separate store. These are manageable if the object remains optional,
immutable, and explicitly target-local.

### Variant B — separate Work Store plus durable intent/outbox

Persist an immutable work_creation_intent in TargetAdmissionLedger, then a
separate idempotent materializer creates one Work Item in another store.

**Advantages:** clearer separation of admission and later work lifecycle;
potentially easier future worker/lease evolution.

**Risks evidenced by the current code:** no existing materializer or outbox
consumer has the required fail-closed/process-safe semantics; two stores create
a crash window between intent and materialization; recovery, ownership of the
intent, conflict handling, and status reconstruction would be new machinery.
The existing NADI and JSON outboxes are transport paths, not suitable durable
intent stores. This is not the smallest safe Slice 03.

### Variant C — adapt an existing Mission/Task/Job model

Reuse Sankalpa, a discussion comment row, NADI item, or a cartridge/router
object as the Work Item.

**Result of live inspection:** no Agent City TaskManager, generic Job, or
WorkItem model exists. Sankalpa is an active mission lifecycle; discussion
rows are external-input state; NADI is transport; routers and cartridges are
in-memory. None simultaneously provides stable IDs, immutable authority/input
binding, fail-closed corruption handling, process-safe first-set dedupe, and
zero-side-effect creation. Variant C is therefore rejected for Slice 03.

## 10. Recon recommendation for the smallest Slice 03 plan

**Recommendation: choose Variant A, but only as a new, separately reviewed
target-local ledger extension. Do not implement it in this recon.**

The recommendation follows from the evidence, not from a preselected system
architecture:

1. TargetAdmissionLedger is the only existing boundary with all required
   crash, lock, corruption, and first-set properties.
2. Slice 02 already stores the immutable candidate and authority facts needed
   to build a READY input snapshot.
3. A second store would introduce an unproven dual-write/recovery boundary.
4. Existing Mission/Queue/NADI structures are semantically active or
   transient, so adapting them would either trigger side effects or change
   legacy behavior.

The smallest future implementation plan should be target-local and
ledger-internal:

~~~text
ASSIGNED record loaded and fully validated
    -> pure deterministic READY Work-Item builder
    -> one immutable ready_work_item object first-set under the existing lock
    -> READY returned locally
~~~

Required boundaries for that future plan (not implementation decisions made by
this recon):

* no candidate-source reread, router call, worker lookup, mission creation,
  queue enqueue, cartridge load, or external message;
* if ready_work_item already exists, return the stored immutable object and
  do not regenerate timestamps, IDs, or digests;
* if the assigned record is malformed, fail closed as ledger corruption;
* if no valid ASSIGNED record exists, do not synthesize READY;
* the observed candidate snapshot remains an observation, never ownership or a
  reservation;
* crash before replacement leaves ASSIGNED without READY;
* crash after replacement leaves complete READY evidence;
* a future started slice must consume READY only after a separately reviewed
  durable Work/Scheduler boundary exists.

No exact JSON schema, work_item_id derivation, or new status contract is
accepted by this recon. Those are implementation-plan/ADR questions below.

## 11. Persisted-state and side-effect hazards to carry forward

1. **Dual-write hazard:** writing a Work Item outside the target ledger after
   reading ASSIGNED can produce a durable ledger record with no Work Item or
   two Work Items after a crash/retry.
2. **False ownership:** the current candidate snapshot and assigned_candidate_id
   do not prove a reservation, worker claim, or continued availability.
3. **Timestamp drift:** a duplicate READY call must not reobserve candidates or
   regenerate observed_at, IDs, digests, or signatures.
4. **Legacy activation:** any call into city.missions, Sankalpa KARMA,
   GatewayKarmaHandler, NADI, cartridge process, or HealExecutor would silently
   leave the READY-only scope.
5. **Corruption policy:** Sankalpa and several JSON/SQLite surfaces do not
   satisfy the target ledger's fail-closed policy; they cannot be trusted as a
   second authority without explicit hardening.
6. **Process boundary:** thread locks alone are not evidence of cross-process
   first-set behavior. The future Work Item commit must reuse the existing
   process lock or provide an equivalently tested mechanism.
7. **Static versus dynamic truth:** the wiring manifest and historical smoke
   counts remain documentation evidence only. They must not be used as a
   runtime readiness or worker-availability check.

## 12. Maximum five open architecture decisions

These are questions, not hidden defaults. They must be answered in a later
plan/review before product code:

1. **READY schema and ID:** What closed, versioned fields and deterministic
   digest derive work_item_id from delegation_id, target_work_id, assignment
   epoch, request/input digest, authority digest, and candidate snapshot
   without implying ownership?
2. **Ledger scope boundary:** Is the optional embedded ready_work_item
   accepted as a bounded Slice-03 extension, with a documented migration and
   size/retention limit, or is a separately specified intent/materializer
   boundary required before implementation?
3. **Crash/read semantics:** What exact API and result codes distinguish
   ASSIGNED, READY, ledger_corrupt, and a pre-commit crash, and how does a
   later caller prove it is returning the immutable first-set record?
4. **Snapshot retention:** Which request, authority, candidate, and provenance
   fields are copied into READY versus referenced by digest, and how long must
   the target retain the underlying evidence for later started/verification
   work?
5. **Next-slice handoff:** What durable local Work/Scheduler boundary is the
   first permitted consumer of READY, and what evidence is required before a
   future started receipt can be introduced without redefining READY?

## 13. Explicitly locked areas

The following remain outside this recon and must not be implemented as part of
Slice 03 planning or documentation:

* MissionRouter dispatch or Mission creation;
* CityRouter mutation or worker selection beyond read-only evidence already
  frozen by Slice 02;
* Sankalpa mission creation, KARMA/MOKSHA mission processing, or mission
  lifecycle changes;
* TaskManager/Job/WorkItem implementation (none currently exists);
* queue, NADI, inbox, scheduler, reservation, lease, or ownership creation;
* worker/cartridge lookup or invocation;
* HealExecutor, Tool, LLM, Git, branch, commit, push, PR, or issue side effect;
* external assignment or started receipts;
* Status Query, terminal result, Verification, Recovery automation, or
  Managed-Task completion;
* Provider Failover, Context Bridge, Execution-Spine system specification,
  automatic merge authority, or productive feature activation;
* modification of Phase 1 documentation, frozen Federation V1 wire contract,
  Golden-Wire fixtures, or the documentation-only wiring manifests as runtime
  state;
* use or commit of the pre-existing untracked .claude/ files.

## 14. Decision

**Recon outcome:** no existing Agent-City Work-Item model satisfies the
requested ASSIGNED -> READY contract. Mission, router, NADI, discussion,
Sankalpa, cartridge, and heal surfaces are either transient, domain-specific,
side-effecting, or missing the required crash/idempotency guarantees.

**Smallest defensible next plan:** a target-local, ledger-internal immutable
READY object built from a fully validated ASSIGNED record, with no external
receipt and no execution caller. This is a recommendation for the next
implementation plan, not authorization to code.

**Gate:** Slice 03 remains documentation-only until the five questions above
are decided in a small implementation plan and independently reviewed. The
current authoritative runtime truth remains Slice 02 ASSIGNED, feature gate
false, disposition disabled, and no productive activation.
