# Maintenance Slice A1 — Explicit Contract-Execution Policy (Revision 0.2)

Status: **PLAN ONLY — Agent-B review required before product code**
Repository: `kimeisele/agent-city`
Base pin: `709898f551da65bf8517405ee8011d32831d9dde` (`main`)
Accepted recon: `docs/MAINTENANCE_SLICE_A_CLI_TEST_GATE_RECON.md`, commit
`263fe04ffb9a5b56f65dfcdac18dc58144b46c58`.

This is the smallest plan for the accepted A1 defect. It does not introduce a
general evidence platform. Maintenance Slice A2 (campaign CLI bootstrap) and
Federation Slice 04 remain separate.

## 1. Defect and evidence

The deterministic timeout is:

```text
heartbeat → ContractsHook.execute
          → ContractRegistry.check_all()
          → check_tests_pass()
          → python -m pytest -x -q --tb=line <repository>
          → outer one-cycle smoke timeout
```

Evidence pins:

* `city/hooks/dharma/contracts_issues.py:ContractsHook.execute` calls
  `ctx.contracts.check_all()` synchronously.
* `city/contracts.py:ContractRegistry.check_all` currently uses
  `cwd or Path.cwd()` and runs every registered contract.
* `city/contracts.py:check_tests_pass` launches repository-wide pytest with a
  configured 120-second child timeout.
* `scripts/heartbeat.py:main` exposes `--cycles`, `--offline`, `--governance`,
  and `--daemon`; the accepted smoke is one cycle with governance enabled.
* `pyproject.toml` has a 30-second pytest test deadline. That is not changed.
* The accepted measurements observed 10/10 deterministic heartbeat cutoffs and
  no persistent child leak.

Campaign CLI has a different three-runtime-boot cost and remains A2; it is not
changed by this plan.

## 2. Narrow decision: exactly two modes

A1 introduces only these explicit modes:

| Mode | Meaning | Allowed execution | Missing/invalid mode |
|---|---|---|---|
| `FULL` | Existing complete ContractRegistry semantics | Run every registered contract once; `tests_pass` may run the repository pytest in this mode | Fail closed; no governance success |
| `BOUNDED` | One-cycle smoke contract policy | Run only the closed lightweight probe allowlist below; never repository-wide pytest | Fail closed; no silent skip |

There is no `evidence_only`, `deferred`, external evidence, freshness/expiry,
producer trust, scheduler evidence, or new evidence ledger in A1. Those would
require a separate recon/ADR if a real caller later needs them.

The caller chooses the mode explicitly. It is not inferred from `Path.cwd()`,
`PYTEST_CURRENT_TEST`, process names, import order, or an ambient test
environment. A missing mode is an error, not an automatic downgrade.

## 3. Exact API and local result

The proposed narrow API is:

```python
class ContractPolicy(str, Enum):
    FULL = "full"
    BOUNDED = "bounded"

@dataclass(frozen=True)
class ContractInvocation:
    invocation_id: str
    policy: ContractPolicy
    contract_scope: str

@dataclass(frozen=True)
class ContractAudit:
    contract_invocation_id: str
    policy_mode: str                 # "full" | "bounded"
    contract_scope: str
    started_at: str                  # RFC-3339 UTC
    finished_at: str                 # RFC-3339 UTC
    terminal_result: str              # "pass" | "fail" | "unavailable"
    reason_code: str | None
    executed_check_ids: tuple[str, ...]

def ContractRegistry.check_all(
    self, cwd: Path, *, invocation: ContractInvocation
) -> tuple[list[ContractResult], ContractAudit]: ...
```

The exact type names may be adjusted during review, but the semantics are
closed: `invocation.policy` is required and `cwd` is an explicit repository
argument. A malformed invocation, unknown policy, empty scope, or omitted
invocation fails closed before a check runs.

The local audit is carried through the existing `ContractResult`/heartbeat
operation and CityReport persistence path. A1 must not create a second
append-only evidence or trust subsystem. The persisted fields are exactly the
seven `ContractAudit` fields above; no external path or producer-authority
claim is added.

`contract_scope` is a deterministic identifier of the registered contract-name
set and policy, not a mutable filesystem path. `executed_check_ids` is the
actual ordered set returned by the registry, never a caller assertion.

## 4. BOUNDED allowlist (closed for A1)

The initial `BOUNDED` set is exactly:

| Contract ID | Callable | Allowed side effects | Max duration | Terminal result |
|---|---|---|---:|---|
| `ruff_clean` | `city.contracts.check_ruff_clean(cwd)` | read source/config; spawn `python -m ruff check --select F821,F811`; no writes/network | existing configured `ruff_timeout_s`, capped by A1 bounded limit | `passing` or `failing`; timeout/process error → `unavailable` |
| `integrity` | `city.contracts.check_integrity(cwd, protected_files=...)` | read Git/protected-file state; no writes/network | bounded local limit (proposed 5s) | `passing` or `failing`; missing Git/state → `unavailable` |

`tests_pass` is explicitly excluded from `BOUNDED`; it is the recursive
repository pytest defect. `audit_clean` is also excluded from the first slice
because it auto-discovers AuditKernel auditors and is not needed to prove the
smoke boundary. Adding either requires a later plan revision.

The `ContractsHook` itself remains the proof that the hook ran: it receives the
returned audit, appends the normal `contract_failing:<name>:<message>` operation
for failures, and the heartbeat result persists the operation through the
existing CityReport path. A bounded invocation with an empty or altered
`executed_check_ids` is invalid. Thus A1 proves both hook execution and that no
repository-wide pytest was launched, without injecting an external result.

## 5. Caller/default matrix

All current `ContractRegistry.check_all()` callers were inventoried on the
accepted main pin:

| Caller | Current behavior | A1 mode/argument | Missing/invalid policy |
|---|---|---|---|
| `city/hooks/dharma/contracts_issues.py:ContractsHook.execute` | implicit `check_all()` on every governance Dharma phase | receives explicit `ContractInvocation`; runtime caller chooses `FULL` or `BOUNDED` | fail closed; hook records unavailable and does not report governance pass |
| `scripts/heartbeat.py:main` normal one-cycle command (`--cycles 1 --offline --governance`) | builds runtime and invokes Mayor cycle | command/test must pass explicit `--contract-policy bounded` | argument/config error; never infer from `--cycles` or pytest |
| `scripts/heartbeat.py:main --daemon --governance` | continuous daemon | explicit `--contract-policy full` required; operational default is FULL only in the daemon’s explicit configuration, not ambient process detection | fail closed; no bounded downgrade |
| `city/discussions_commands.py:_exec_heal` | direct operator `/heal` invokes `check_all()` before selecting a named contract | explicit `FULL` invocation (operator command is not a smoke) | fail closed and return unavailable; no silent bounded mode |
| `tests/test_layer3.py` direct registry tests | unit tests currently call `check_all()` without policy | tests migrate to explicit `ContractInvocation(policy=FULL, ...)`; test helper may use BOUNDED only where the test asserts bounded semantics | missing invocation is an expected fail-closed unit case |
| other Python callers | `rg` on the pinned tree found no additional `ContractRegistry.check_all()` calls; `PRLifecycle.check_all` is a different API | not applicable | any future caller must pass an invocation; code review rejects implicit defaults |

The explicit CLI/config field is passed through `scripts/heartbeat.py:main` →
`city.runtime:build_city_runtime` → `PhaseContext.contracts` →
`ContractsHook.execute` → `ContractRegistry.check_all`. `ContractsHook` does
not inspect CLI arguments, cwd, or pytest state. A regular production/unknown
caller cannot receive BOUNDED implicitly.

## 6. Reentrancy: process-local only in A1

A1 does not create a lease, persistent marker, inter-process protocol, or
network lock. The existing `scripts/heartbeat.py:_acquire_heartbeat_lock`
uses `fcntl.flock` for single-writer heartbeat serialization, but it is not a
contract-runner ownership primitive and is not repurposed.

The A1 runner uses a process-local, exception-safe guard keyed by
`(contract_scope, policy)` (for example a `contextvars.ContextVar` plus a
thread-safe set). On direct recursion for the same scope, it returns an
`unavailable` audit with `reason_code="reentrant_contract_execution"` and runs
no child command. The guard is released in `finally`, including exceptions.

Different scopes may run in parallel. A crashed process leaves no persistent
marker; the operating system releases the heartbeat lock as before. An
inter-process contract-runner guard, stale PID handling, and PID-reuse policy
are explicitly outside A1 and require a separate recon if needed.

## 7. FULL and BOUNDED invariants

* `FULL` runs every registered contract exactly once for the invocation. A
  missing result, child timeout, exception, or recursive call is terminal
  `unavailable`/failure; it is never converted to pass.
* `BOUNDED` runs exactly `("ruff_clean", "integrity")` in registry order. It
  cannot call `check_tests_pass`, `python -m pytest <repository>`, or any
  unlisted contract.
* Both modes execute real callables; no injected or precomputed evidence is
  accepted.
* No mode changes contract definitions, governance authority, heartbeat
  cadence, or global pytest configuration.
* A bounded failure remains visible through the existing ContractResult,
  hook operation, and CityReport/audit trail. It is not a skip.

## 8. Required tests before implementation acceptance

The implementation PR must add focused tests for:

1. `FULL` success and failure, including `tests_pass` invocation only in FULL;
2. `BOUNDED` success and failure with exactly the two allowlisted IDs;
3. unknown mode and missing invocation fail closed;
4. a caller attempting to downgrade a required FULL invocation to BOUNDED;
5. direct recursion returns `unavailable` and launches no child;
6. BOUNDED never executes `python -m pytest <repo>` (subprocess spy);
7. the regular daemon path selects FULL explicitly;
8. the one-cycle smoke command selects BOUNDED explicitly;
9. audit fields contain actual IDs, times, result, and reason;
10. guard cleanup after exceptions permits a later independent invocation.

The PR must rerun the focused heartbeat smoke, Slice-01A/02/03 Federation
suites, Ruff, and py_compile. It must not change Campaign CLI, Federation,
Scheduler, Worker, Mission, Queue, READY, Claim, Lease, or Slice-04 code.

## 9. Definition of done and non-goals

A1 is complete only when the one-cycle smoke executes the bounded real probes,
never starts an unbounded repository pytest child, and records a local audit
showing the hook and exact check IDs ran. Daemon/production callers remain FULL
and fail closed on unavailable evidence. No caller can silently inherit a
different mode.

Not in A1: external evidence, freshness, producer trust, deferred mode,
Campaign CLI optimization (A2), inter-process contract leases, Federation,
Scheduler/Worker/Mission/Queue changes, READY→Claim, Started/terminal receipts,
Context Bridge, Provider Failover, Execution Spine, or activation.
