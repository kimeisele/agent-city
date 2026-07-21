# Federation Slice 04 — Cross-Repo Protocol and Execution Boundary Recon

Status: **READ-ONLY RECON — no product code, no wire change, no activation**
Prepared from live `main` pins on 2026-07-21.
Heartbeat commits were excluded from the history sampling (`git log --invert-grep
--grep=heartbeat`); the conclusions below come from current code, tests, and
schemas rather than heartbeat commit volume.

## 1. Live pins and evidence boundary

| Repository | Main SHA | Relevant evidence |
|---|---|---|
| `kimeisele/steward-protocol` | `34a8a0efc25c15ef7c07dd4fb50aeb2510c071e8` | `vibe_core/mahamantra/federation/types.py:FederationMessage`; `vibe_core/protocols/identity.py:IdentityProtocol`; `docs/steward/FEDERATION.md` is explicitly planned |
| `kimeisele/agent-world` | `6771524abef20ef4f9b98ad366ba4bfa0968111a` | `agent_world/schema.py`; `agent_world/registry.py`; `agent_world/federation.py`; `config/world_registry.yaml`; `config/world_policies.yaml` |
| `kimeisele/agent-internet` | `dcd0206434b21d8c0ec2fac81e2aafc856401831` | `agent_internet/router.py:RegistryRouter`; `trust.py:InMemoryTrustEngine`; `federation_descriptor.py`; `docs/adrs/0003...` |
| `kimeisele/steward-federation` | `0a897d5774f0585552f268913fb2541b4fc24a11` | `nadi_kit.py:NadiMessage`, `NadiTransport`, `NadiHubRelay`, `NadiNode`; relay files under `nadi/` |
| `kimeisele/steward` | `7ad8954a1e319b9f8314b240fab78baae9f69c45` | `steward/federation.py:FederationBridge`; `federation_transport.py:NadiFederationTransport`; `federation_crypto.py`; `data/federation/*` |
| `kimeisele/agent-city` | `709898f551da65bf8517405ee8011d32831d9dde` | `city/federation_v1.py`; `city/federation_nadi.py`; `city/federation_relay.py`; `city/mission_router.py`; Slice-01A–03 docs/tests |

The current Agent City main includes the accepted maintenance recon merge
`709898f...`; its feature gate remains false and Slice 04 has not started.

## 2. Current direct Steward → Agent City path

The accepted Slice-01A path is a direct, exact-target compatibility path, not
the general control plane:

```text
Steward FederationV1Origin
  → signed Draft-0.5 delegate_task envelope
  → closed carrier (source/target/operation must match inner envelope)
  → transport adapter / NADI file or hub relay
  → Agent City carrier_inner + provenance validator
  → TargetAdmissionLedger (ACCEPTED or REJECTED, durable dedupe)
  → signed admission receipt carrier
  → Steward OriginDelegationLedger correlation by delegation/request IDs
```

Live code shows two coexisting layers. The newer V1 code is in
`agent-city/city/federation_v1.py:validate_envelope, build_carrier,
TargetAdmissionLedger, FederationV1Origin, FederationV1Admission`; the older
NADI layer is `city/federation_nadi.py:FederationMessage/FederationNadi` and
`city/federation_relay.py:FederationRelay`. Steward's generic bridge remains
`steward/federation.py:FederationBridge`, with `OP_DELEGATE_TASK` and a legacy
TaskManager handler at `_handle_delegate_task`.

Important current facts:

* V1 IDs, hashes, provenance and carriers are strict and typed in Agent City.
* The generic NADI models are not the Draft-0.5 V1 wire schema. Steward's
  legacy signer calls its hash `payload_hash`; Agent City NADI and
  `steward-federation/nadi_kit.py` have different field sets and dedupe keys.
* `FederationRelay` uses GitHub Contents API and per-peer mailbox files; it is
  transport, not admission authority.
* Legacy Steward `_handle_delegate_task` creates a TaskManager task and uses
  peer trust. It is not invoked by V1 Slice 01A and must remain isolated.
* Existing legacy callbacks can still correlate by title/description (for
  example `steward/federation.py:_handle_task_callback`); this is a known
  legacy risk, not a V1 correlation rule.

### Direct-path classification

**Classification: temporary compatibility adapter, with a valid-reference
subset.** The exact-target V1 path is a valid reference adapter for a fixed
target and already-defined envelope. It does not yet implement global
discovery, route selection, or relay ownership. The surrounding NADI/GitHub
relay path is a temporary compatibility transport because its IDs, TTL,
signature field names, and dedupe semantics differ from Draft 0.5.

It becomes an architecture break if this path starts deciding world
membership, global discovery, trust enrollment, route/carrier policy, relay
ownership, or global revocation. Those decisions must stay outside the
execution/admission adapter.

## 3. Normative ownership map (current truth)

`ACCEPTED` below means the code provides a bounded owner for the current
surface; `OPEN` means no single normative owner is proven.

| Responsibility | Current owner/status | Evidence and boundary |
|---|---|---|
| Cryptographic identity primitives | **OPEN / duplicated** | `steward-protocol/vibe_core/protocols/identity.py` is a Protocol; concrete Ed25519 handling exists in `steward-federation/nadi_kit.py:NodeKeyStore` and Steward/City modules |
| Node identity | **Duplicated** | NADI `ag_` derivation in `nadi_kit.py:_derive_node_id`; City `city/identity.py`; Steward `federation.py:_load_node_identity`; no shared normative implementation |
| Execution identity | **Agent City V1 for V1 delegation; otherwise OPEN** | `delegation_id`, `request_message_id`, `target_work_id` in `city/federation_v1.py`; generic NADI has `id`/timestamp only |
| Capability vocabulary | **Split** | World schema capability sets; MissionRouter requirements; V1 payload `capability`; no cross-repo closed vocabulary owner |
| Capability authorization | **Agent City TargetAdmission for V1; otherwise split** | `FederationV1Admission._policy_allows`; Steward peer trust and legacy handlers are separate |
| World membership | **agent-world** | `config/world_registry.yaml`, `agent_world/schema.py` validators, `agent_world/registry.py` |
| City registry | **agent-world declared; agent-internet runtime registry** | World registry is authoritative configuration; `agent_internet.router.RegistryRouter` consumes a `CityRegistry` adapter |
| World policy | **agent-world** | `config/world_policies.yaml`, `agent_world/schema.py:validate_policies` |
| Node discovery | **agent-internet implementation; protocol ownership OPEN** | `discovery_bootstrap.py`, descriptor loaders, registry/discovery interfaces; world also has registry/discovery concepts |
| Trust resolution | **agent-internet local engine; Steward legacy peer trust also exists** | `agent_internet/trust.py:InMemoryTrustEngine`; Steward `PeerRecord.trust` and federation trust floor |
| Route selection | **agent-internet** | `RegistryRouter.resolve_next_hop` |
| Next-hop selection | **agent-internet** | same resolver, longest-prefix/metric ordering |
| Carrier selection | **OPEN** | V1 builds a fixed carrier; agent-internet resolves endpoints/routes; no normative cross-repo carrier policy |
| Transport delivery | **steward-federation plus repo adapters** | `nadi_kit.py:NadiTransport/NadiHubRelay`; City/Steward filesystem and GitHub relay adapters |
| Delivery retries | **Duplicated/OPEN** | `city/net_retry.py`, relay GitHub retries, NADI TTL/buffer; no shared V1 delivery contract |
| Relay/store-and-forward | **steward-federation transport surface** | `NadiHubRelay`, `agent-city/FederationRelay`, Steward relay; ownership is operational, not execution authority |
| Admission authority | **Agent City TargetAdmissionLedger/V1 Admission** | `city/federation_v1.py:FederationV1Admission` and typed key registry |
| Assignment authority | **Agent City local Slice 02** | `TargetAdmissionLedger.assign_candidate`; target-local signed attestation |
| Local READY lifecycle | **Agent City** | embedded `ready_work_item` and `create_ready_work_item`; no transport |
| Claim/lease ownership | **OPEN / not implemented for Slice 04** | MissionRouter is pure scoring; no proven durable claim/lease boundary |
| Completion | **OPEN** | Legacy task callbacks and mission results exist, but no V1 lifecycle owner |
| Verification | **OPEN / Origin-side contract not yet wired** | V1 admission has no terminal/verification receipt in current scope |
| Public projection | **agent-world declared; agent-internet descriptor/index consumers** | World `public_projection` field and agent-internet descriptor/projection intents; authority split needs ADR |

The table deliberately does not promote a documented aspiration to a runtime
owner. In particular, `steward-protocol/docs/steward/FEDERATION.md` is marked
planned and cannot override the live NADI/V1 implementations.

## 4. Duplicate protocol audit

| Surface | Observed copies | Classification | Risk |
|---|---|---|---|
| Envelope/message model | Draft-0.5 V1 in Agent City; `FederationMessage` in steward-protocol; `NadiMessage` in steward-federation; City/Steward legacy NADI dicts | divergent parallel models, with legacy adapters | A V1 envelope can be accidentally sent through a legacy parser |
| Receipt model | V1 admission receipt in Agent City; generic `receipts.json`/transport receipts in Steward, City, Hub | distinct domains, not one schema | “receipt” name can imply false verification semantics |
| Canonical JSON/hash | SFDJ-1 helpers in Agent City; `json.dumps(sort_keys=True)` in legacy signers and Nadi kit | divergent implementation | Golden bytes are valid only for V1 module; do not reuse legacy signer |
| Typed hashes/IDs | V1 request/assignment/READY hashes; UUID/timestamp and `source:timestamp` dedupe elsewhere | V1 plus legacy transport IDs | Correlation loss at adapter boundaries |
| Signature verification | `ValidatedFederationV1KeyRegistry` in City; Steward `federation_crypto`; Nadi Ed25519 in Hub; City NADI signer | duplicated crypto paths | Provenance and revocation semantics differ |
| Key certificates/revocation | V1 provenance fixtures/registry in City; legacy peer/verified-agent maps in Steward; no equivalent in Hub Nadi | V1-specific plus untyped legacy state | Legacy registry must never satisfy V1 provenance |
| Retry/TTL | V1 retransmission rules; NADI TTL/buffer; GitHub relay retries; `city/net_retry.py` | adapter/runtime copies | Application retry can be confused with transport replay |
| NADI message object | steward-federation `nadi_kit.py` is advertised as shared/vendor copy; City and steward-protocol contain local compatible-looking models | generated/vendor copies plus drift | “100% compatible” claim is not a byte-level protocol proof |
| Golden fixtures | V1 fixtures/tests are in Agent City (`tests/federation_v1`); no evidence of a shared fixture package in all six mains | test fixture owner currently City | Later external receipt needs a pinned protocol owner and consumer pins |

No current evidence proves that the repositories consume one shared Draft-0.5
schema package. The safe interpretation is: Agent City V1 is the current
fixture/reference consumer, while the generic NADI copies are separate legacy
transport surfaces.

## 5. Agent Internet boundary

`agent-internet` is more than a README: `RegistryRouter` performs endpoint,
health, trust and next-hop selection; `InMemoryTrustEngine` stores pairwise
trust; descriptor loaders parse `agent_federation_descriptor`; filesystem,
HTTPS, Git and relay transports have tests. However, the implementation is
not the normative owner of Draft-0.5 execution semantics:

* its own ADR 0003 is **Proposed**, but explicitly says external protocols are
  transport adapters and must not replace Nadi/Lotus or subject/city/space
  identity;
* registry/trust/router implementations are in-memory or adapter-backed and
  not shown to be the authoritative world membership or V1 key-provenance
  registry;
* `steward-federation` remains the concrete NADI hub/relay implementation;
* no live code proves an Agent Internet bridge for the accepted V1
  `federation_v1.delegate_task` carrier.

Therefore agent-internet is **implemented for a control-plane-shaped
transport/discovery substrate, but not wired as the V1 execution authority**.
It is not safe to add it to Slice 04 merely to obtain a claim or lease.

## 6. World and protocol authority

`agent-world` owns declarative world registry/policy validation and emits
`world_state_update`, `policy_update`, `heartbeat`, and consumes `city_report`
through a NADI node (`agent_world/federation.py`). It does not own the V1
cryptographic envelope or Agent City admission ledger. Its registry capability
vocabulary and the V1 payload capability vocabulary are not proven identical.

`steward-protocol` contains useful interfaces and a planned federation model,
but its live `FederationMessage` is a permissive dataclass with generic payload,
timestamp, TTL, and optional correlation. It is not the frozen SFDJ-1/Draft-0.5
schema. The protocol repository therefore cannot currently be called the
exclusive wire-schema owner without a separate ADR.

## 7. Slice-04 consequence: READY → local claim/reservation

Current decision: **the next claim experiment must be Agent-City-local and
read-only in its authority scope**.

* MissionRouter (`city/mission_router.py`) is a pure capability scorer. It is
  not a durable claim owner and must not be called as a side effect of a
  claim unless a later plan proves that read-only snapshot use is safe.
* No current main shows a durable, crash-safe, process-safe local claim/lease
  store for READY. Existing Mission/Sankalpa/Task flows are active domain
  lifecycles and may trigger execution or side effects.
* A local claim may not require Agent Internet routing, global trust, world
  membership, or a network lease unless a future contract explicitly says so.
* The claim identity must be a new local `claim_id` (or equivalent local
  execution identity), distinct from `delegation_id`, `target_work_id`,
  `work_item_id`, node ID, and candidate ID. The authoritative owner is not
  determinable from current code.
* No external `started` receipt is justified by a local claim until the
  protocol owner, causality, lease semantics, crash/reclaim behavior, and
  evidence meaning are decided.

### Current data-flow versus safe target data-flow

```text
CURRENT:
V1 request → TargetAdmissionLedger ACCEPTED → ASSIGNED → READY (local)
legacy NADI/relay may carry other generic messages in parallel

SAFE NEXT TARGET (not implementation):
READY → local claim boundary (one durable first-set claim)
      → explicit claim evidence
      → later review of whether this can mean external `started`
```

No Scheduler, Worker, Mission, Queue, Lease, Tool, LLM, Git, or external
receipt belongs in the current recon or in a Slice-04 implementation before
the boundary is accepted.

## 8. Required ADRs (maximum five)

1. **Protocol ownership and distribution:** choose one normative owner for the
   Draft-0.5 schema and define how Steward, Agent City, and future consumers
   pin it and its fixtures.
2. **Identity/provenance separation:** decide whether node identity primitives
   live in steward-protocol, a dedicated protocol package, or remain adapter
   contracts; define key registry/revocation ownership.
3. **Transport/control-plane boundary:** define which agent-internet and
   steward-federation routing/trust decisions are transport-only and which are
   authoritative for execution.
4. **Local claim/lease semantics:** decide whether Slice 04 is local first-set
   claim only, and define claim ID, owner, crash, expiry, reclaim, and
   idempotency without implying external execution.
5. **Started evidence contract:** decide the minimum durable local event that
   permits a future `started` receipt, its repository owner, causal IDs, and
   whether a network route is required.

ADR-1 and ADR-2 are hard blockers before a new externally transported receipt.
ADR-4 is the blocker before Claim/Lease product code. ADR-5 is a blocker before
any `started` wire message. None blocks a purely local, read-only recon.

## 9. Recommendation and gates

Recommendation: classify the current direct V1 path as a **temporary
compatibility adapter with a valid exact-target reference subset**; do not move
authority into agent-internet or agent-world. Keep V1 admission/assignment/
READY ownership in Agent City, keep transport in steward-federation and repo
adapters, and treat steward-protocol's generic models as consumers/interfaces
until Protocol Ownership ADR-1 is accepted.

Before any Slice-04 claim code:

1. Agent-B reviews this recon and the A1 plan.
2. Resolve the five ADR questions as needed (at minimum ADR-4).
3. Reconfirm that local claim cannot invoke MissionRouter dispatch, Scheduler,
   Worker, Queue, or external routing.
4. Add adversarial tests for duplicate claim, crash before/after commit,
   stale candidate/authority, and no external message.

Before any external `started`, status, terminal, or verification receipt:

* complete the cross-repo protocol-ownership review;
* pin the normative schema and fixtures across all affected repositories;
* define transport replay separately from application retry;
* obtain a new Agent-B acceptance.

## 10. Hard exclusions

This recon does not authorize:

* READY → Claim/Lease product code;
* external READY/Assignment/Started messages;
* a new Federation wire contract;
* Agent Internet routing/registry wiring;
* authority migration between repositories;
* Scheduler, Worker, Mission, Queue, Tool, LLM, Git, or PR execution;
* Provider Failover, Context Bridge, Execution Spine, or activation.
