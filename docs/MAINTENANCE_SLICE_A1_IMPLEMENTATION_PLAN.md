# Maintenance Slice A1 — Explicit Contract-Execution Policy

Status: **PLAN ONLY — Agent-B review required before product code**  
Repository: `kimeisele/agent-city`  
Base pin: `709898f551da65bf8517405ee8011d32831d9dde` (`main`)  
Related recon: `docs/MAINTENANCE_SLICE_A_CLI_TEST_GATE_RECON.md` at
`263fe04ffb9a5b56f65dfcdac18dc58144b46c58`.

This document is a bounded implementation plan. It does not change the
heartbeat contract, weaken governance, or authorize a production activation.
Maintenance Slice A2 (campaign CLI bootstrap) is deliberately separate.

## 1. Problem and evidence

The accepted A1 recon measured a deterministic timeout, not a child-process
leak:

* `scripts/heartbeat.py:main` invokes the Mayor cycle. With `--governance`,
  `city/hooks/dharma/contracts_issues.py:ContractsHook.execute` calls
  `ctx.contracts.check_all()`.
* `city/contracts.py:ContractRegistry.check_all(cwd=None)` resolves `cwd` to
  `Path.cwd()` and `check_tests_pass` starts `python -m pytest -x -q --tb=line
  <cwd>`. The one-cycle smoke therefore starts an unbounded nested repository
  test run synchronously.
* The global `pyproject.toml` pytest timeout is 30 seconds. It is a test
  harness deadline, not a product contract deadline, and must not be raised
  globally as the fix.
* The accepted measurements found 10/10 isolated heartbeat cutoffs and
  repeated nested pytest processes, with no persistent child leak.

The campaign CLI has a different cause: each of `apply`, `list`, and `show`
builds a full runtime (`scripts/campaigns.py:_build_runtime` →
`city.runtime:build_city_runtime` → `Spawner.materialize_existing`). It did not
perform network, Git, worker, or Federation work. A1 must not change that path;
it belongs to A2.

## 2. Decision

Introduce an explicit, typed contract-execution policy at the invocation
boundary. The policy is selected by the caller/configuration and is never
inferred from `Path.cwd()`, `PYTEST_CURRENT_TEST`, import order, or process
name.

The plan uses four evidence outcomes, which are persisted independently of the
policy:

* `executed`: the requested checks ran to a terminal result;
* `deferred`: the policy intentionally postponed execution and records why;
* `externally_supplied`: a caller supplied a validated, still-fresh evidence
  record;
* `unavailable`: the required evidence could not be produced or validated.

The policy and outcome are separate fields. A bounded smoke may legitimately
produce `deferred`; a production governance cycle may not silently treat that
as success.

## 3. Normative policy modes

The implementation plan defines these modes (names are part of the proposed
local API and require Agent-B acceptance before coding):

| Mode | Intended caller | Allowed work | Missing/invalid evidence |
|---|---|---|---|
| `full` | daemon/production governance, explicit operator run | Run the complete configured contract set once, outside a nested test invocation | `unavailable` and fail closed; no governance success is reported |
| `bounded` | one-cycle CLI/smoke | Run only an explicitly enumerated bounded set (no repository-wide pytest); the set and limit are recorded | `unavailable`; smoke reports non-success, never silently passes |
| `evidence_only` | controlled caller with precomputed evidence | Do not execute tests; accept only a schema-valid, digest-bound, fresh evidence record | `unavailable` |
| `deferred` | explicit maintenance/offline caller only | Record that execution was intentionally deferred | `deferred`; forbidden as an implicit production fallback |

The one-cycle heartbeat smoke must pass `bounded` explicitly (for example by a
CLI flag/config value). The normal daemon/governance entry point defaults to
`full`. A production caller may use `evidence_only` only when an operator or a
trusted scheduler explicitly supplies valid evidence under the freshness and
scope rules below. No caller may downgrade `full` to `bounded` or `deferred`
implicitly.

## 4. Explicit configuration contract

The proposed configuration object is conceptually:

```text
ContractExecutionPolicy {
    mode: full | bounded | evidence_only | deferred
    contract_scope: immutable identifier of the configured contract set
    evidence_path: optional, only for evidence_only
    max_duration_seconds: mode-specific bounded value, not a global pytest timeout
    allow_nested_runner: false by default
    invocation_id: required opaque local audit ID
}
```

The actual location (CLI option, runtime constructor, or config file) is an
implementation decision for Agent-B review, but it must be explicit and
serializable. `cwd` may identify the repository under test after policy
selection; it is not allowed to select the policy. A configuration parse error,
unknown mode, missing scope, or path substitution is fail-closed.

The policy must be passed into `ContractRegistry.check_all(...)` (or its
replacement adapter) rather than read from ambient pytest variables. Existing
callers without an explicit policy must be audited; production/daemon callers
must receive `full`, while tests must opt into `bounded` or `evidence_only`.

## 5. Full-check and bounded-check semantics

`full` executes the complete contract set configured for the invocation. A
successful result means every required check produced a terminal pass result
and its evidence was persisted. A timeout, runner error, missing result, or
partial set is `unavailable`/failure, not pass.

`bounded` has a closed allow-list of checks and a closed scope digest. It must
not call `python -m pytest` over the repository. If a bounded check needs a
subprocess, the command, argument vector, timeout, and output digest are part
of the audit record. The initial A1 slice should use precomputed lightweight
contract probes or injected evidence, not invent a second test framework.

`evidence_only` validates the supplied evidence schema, contract-scope digest,
producer identity, creation time, expiry/freshness window, and terminal result.
Evidence for another repository, scope, or policy is rejected.

`deferred` is for explicitly named maintenance/offline workflows. It is never
accepted as evidence of a production governance pass.

## 6. Reentrancy and nested pytest rule

The contract runner must not recursively invoke a full repository pytest run
from inside pytest or from another active full contract run. This is a policy
rule, not an environment heuristic. The implementation must:

1. allocate an `invocation_id` and acquire a process-local plus inter-process
   reentrancy marker keyed by `(contract_scope, mode)`;
2. reject a second `full` execution for the same scope while the first is
   active, recording `unavailable` with reason `reentrant_execution`;
3. disallow `allow_nested_runner` for `full` in production configuration;
4. release the marker in normal and exceptional teardown;
5. make stale markers detectable and fail closed rather than silently starting
   a second runner.

`PYTEST_CURRENT_TEST` may be recorded as diagnostic context, but it is not a
decision input. A one-cycle smoke is safe because it selects `bounded` before
the cycle starts; the heartbeat code does not discover that it is under pytest.

## 7. Audit evidence schema (plan)

Each invocation writes one immutable append-only evidence record with a closed
field set:

```json
{
  "schema": "agent-city-contract-evidence-v1",
  "invocation_id": "ci_...",
  "policy_mode": "full|bounded|evidence_only|deferred",
  "outcome": "executed|deferred|externally_supplied|unavailable",
  "contract_scope": "sha256:...",
  "repository_root": "content-addressed or configured repo identity",
  "producer": "daemon|cli_smoke|operator|external_evidence",
  "started_at": "RFC-3339 UTC",
  "finished_at": "RFC-3339 UTC|null",
  "evidence_digest": "sha256:...|null",
  "terminal_result": "pass|fail|unknown",
  "reason_code": "...|null"
}
```

No free-form field may decide authority, scope, or pass/fail. `externally_supplied`
must point to an immutable evidence digest; a mutable path alone is not proof.
Records are retained as audit evidence. This slice does not add a new runtime
health dashboard or manually maintained health state.

## 8. Failure and governance rules

* Daemon/production `full` with unavailable, stale, partial, or reentrant
  evidence fails closed and does not report a successful governance cycle.
* One-cycle `bounded` with unavailable evidence returns a non-success result
  with an auditable reason; it may not silently skip the contract hook.
* `deferred` is visible in the result and audit ledger and is rejected by any
  caller requiring production governance proof.
* An invalid externally supplied record is `unavailable`, not `deferred`.
* No global pytest timeout, heartbeat cadence, governance authority, or
  contract definition is weakened.

## 9. Minimal implementation and test sequence (after Agent-B review)

1. Add the typed policy/evidence boundary and closed validation.
2. Thread explicit policy from heartbeat CLI/daemon entry points to the
   contract hook/registry.
3. Add the reentrancy marker and fail-closed teardown.
4. Make the one-cycle smoke choose `bounded` explicitly; leave daemon default
   `full`.
5. Add tests for every mode, stale/foreign evidence, unknown mode, missing
   scope, recursive invocation, marker cleanup, and production downgrade
   attempts.
6. Re-run the accepted heartbeat smoke and the Federation/Slice 01A–03 suites.
   Do not modify Federation code or the campaign CLI in this PR.

Definition of done is behavioral: the smoke no longer launches an unbounded
repository pytest run; daemon governance still requires complete or explicitly
validated fresh evidence; every non-executed outcome is persisted and visible;
and no nested runner can pass by recursion. A2 remains a later independent
maintenance slice.

## 10. Explicit non-goals and review gate

This plan does not authorize product code yet and does not include:

* a global timeout change;
* a test skip, marker, or pytest configuration weakening;
* campaign runtime optimization (A2);
* Scheduler, Worker, Mission, Queue, Federation, READY, Claim, Lease, or
  Started-Receipt changes;
* Context Bridge, Provider Failover, or Execution-Spine work;
* activation or authority changes.

Agent-B must review the mode names, evidence schema, freshness rules, marker
storage, and caller defaults before implementation.
