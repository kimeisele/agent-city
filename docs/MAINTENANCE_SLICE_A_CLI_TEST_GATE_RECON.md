# Maintenance Slice A — CLI/Test-Gate Reliability Recon

## Decision status

**READ-ONLY RECON COMPLETE — IMPLEMENTATION PLAN REQUIRED**

No product code, test code, pytest configuration, Federation code, Scheduler,
Worker, or activation was changed. Slice 04 remains locked.

## Evidence and pins

Repository: `kimeisele/agent-city`

* Final `main` pin: `42b48f820473a71e9205f66531c9698c36bfea1f`
* Parent maintenance merge: `9c6770e9ef8982971b8c39e1c21ab2fefacda3da`
* Recon branch: `docs/maintenance-slice-a-cli-recon`
* Python: `3.11.13`
* Host: macOS Darwin `22.6.0`, x86_64
* Test key: ignored synthetic Federation key file copied only into the
  disposable checkout; no key or fixture was changed.

Relevant history was inspected with heartbeat commits explicitly excluded:

```text
git log --regexp-ignore-case --invert-grep --grep=heartbeat \
  -n 8 --oneline -- city/contracts.py city/runtime.py scripts/heartbeat.py \
  scripts/campaigns.py tests/test_heartbeat_campaign_bootstrap.py \
  tests/test_campaign_cli.py
```

The relevant live symbols are pinned below; no historical heartbeat prose is
used as evidence.

## Tested surfaces and exact commands

Heartbeat test command from
`tests/test_heartbeat_campaign_bootstrap.py::test_heartbeat_cli_smoke_with_campaign_manifest`:

```text
python scripts/heartbeat.py --cycles 1 --offline --governance \
  --db <tmp>/city.db --campaign-file <tmp>/campaign.json
```

Campaign CLI test command from
`tests/test_campaign_cli.py::test_campaign_cli_apply_list_show`:

```text
python scripts/campaigns.py --db <tmp>/city.db --offline apply --file <tmp>/campaign.json
python scripts/campaigns.py --db <tmp>/city.db --offline list
python scripts/campaigns.py --db <tmp>/city.db --offline show internet-adaptation
```

The measurement harness used `subprocess.Popen(..., start_new_session=True)`,
monotonic wall-clock timestamps, a 40-second Heartbeat / 60-second Campaign
CLI per-process cutoff, process-tree inspection via `psutil`, and process-group
termination only after a measurement cutoff. It recorded spawn return,
subprocess return, teardown, return code, timeout, observed children, and
leftovers. No external network or Git command was enabled.

## Measurement results

### Ten isolated Heartbeat runs

| metric | result |
| --- | ---: |
| runs | 10 |
| completed before cutoff | 0 |
| cutoffs at 40 s | 10/10 |
| subprocess return median | 40,108 ms |
| subprocess return p90 | 40,159 ms |
| subprocess return maximum | 40,163 ms |
| `Popen` return range | 3.8–19.5 ms |
| teardown range after process-group termination | 0.1–1.9 ms |
| child process observed | 9/10 |
| nested pytest child observed | 7/10 explicitly; nested child command observed repeatedly |
| leftover child processes after teardown | 0 |

Every run was terminated at the measurement cutoff with `SIGTERM` to the
process group. The observed nested command was:

```text
python -m pytest -x -q --tb=line /private/tmp/agent-city-slice-a-recon
```

The child was not a network or Federation process. It was the quality contract
runner executing the whole repository from the Heartbeat process.

### Ten isolated Campaign CLI sequences

Each sequence used fresh database/manifest paths and three fresh Python
processes (`apply`, `list`, `show`). All 30 subprocesses returned zero and no
child process or post-return leak was observed.

| metric | result |
| --- | ---: |
| sequences | 10 |
| subprocesses | 30 |
| failed/timeouts | 0 |
| total sequence median | 27,943 ms |
| total sequence p90 | 41,895 ms |
| total sequence maximum | 43,803 ms |
| `apply` return median | 11,495 ms |
| `list` return median | 7,929 ms |
| `show` return median | 7,566 ms |
| `Popen` return range | 2.7–117.9 ms |
| teardown range | 0.1–1.0 ms |
| child processes / leftovers | 0 / 0 |

The first sequence was 29.6 s; later sequences ranged from 24.3 s to 43.8 s.
Warm OS/Python caches did not produce a stable monotonic improvement. The
dominant time is process/runtime initialization and local database/file work,
not `Popen` or teardown.

### Ten alternating pairs

Ten pairs were executed in alternating order:

```text
pair 1: Heartbeat → Campaign CLI
pair 2: Campaign CLI → Heartbeat
... alternating through pair 10
```

| metric | Heartbeat | Campaign sequence |
| --- | ---: | ---: |
| runs | 10 | 10 |
| timeouts | 10/10 at 35-s cutoff | 0 |
| return/sequence median | 35,101 ms | 30,606 ms |
| p90 | 35,119 ms | 32,753 ms |
| maximum | 35,157 ms | 35,555 ms |
| leftovers | 0 | 0 |

Order changed Campaign runtime but did not change the Heartbeat outcome. This
is deterministic nested-work behavior for Heartbeat, and variable but
successful startup cost for Campaign CLI.

### Neighboring test-module runs

| command | result |
| --- | --- |
| `pytest -q tests/test_campaigns.py tests/test_campaign_cli.py::test_campaign_cli_apply_list_show` | `6 passed`, 16 warnings, 31.55 s |
| `pytest -q tests/test_heartbeat_campaign_bootstrap.py::test_heartbeat_cli_smoke_with_campaign_manifest tests/test_campaign_cli.py::test_campaign_cli_apply_list_show` | `1 failed` (Heartbeat timeout), `1 passed`, 1 warning, 56.52 s |

The neighboring run reproduces the Heartbeat failure and leaves Campaign CLI
passing.

## Live execution traces and root causes

### Test harness boundary

`pyproject.toml` sets:

```toml
[tool.pytest.ini_options]
timeout = 30
```

This is a pytest test deadline, not a Heartbeat or Campaign domain deadline.
Neither CLI sets a 30-second application timeout. Raising it globally, skipping
the tests, or weakening the gate would hide the observed behavior and is not a
valid fix.

### Heartbeat — deterministic nested full-suite execution

The live path is:

```text
scripts/heartbeat.py:main (lines 133, 167–168)
  → runtime.mayor.run_cycle(1)
  → city/phases/dharma.py:execute
  → ContractsHook.execute (city/hooks/dharma/contracts_issues.py:43–49)
  → ctx.contracts.check_all()
  → ContractRegistry.check_all(cwd=None) (city/contracts.py:72–82)
  → cwd = Path.cwd()
  → check_tests_pass (city/contracts.py:158–166)
  → python -m pytest -x -q --tb=line <repo>
```

`check_tests_pass` has a configured contract timeout of 120 s, while the outer
pytest test kills the Heartbeat at 30 s. The nested child is therefore a
real synchronous quality-contract execution, not a teardown leak. When the
contract reports failures, the same governance cycle can create local healing
missions and council proposals through `ContractsHook`; these are temporary
local state effects in the test database, not external network effects.

**Root cause:** `--governance` synchronously runs the repository-wide pytest
contract during a one-cycle CLI smoke command. The timeout is deterministic and
product-path related, not stale test syntax or random process teardown.

### Campaign CLI — repeated full runtime bootstrap

The live path is:

```text
scripts/campaigns.py:main (line 42)
  → _build_runtime (lines 77–86; governance=True, federation=False)
  → city.runtime:build_city_runtime
  → substrate bootstrap, ledgers, CivicBank, Pokedex, factory.build_all
  → state restore and _spawn_system_agents (runtime.py:189)
  → Spawner.materialize_existing (spawner.py:191–236)
  → command-specific apply/list/show
```

Each of `apply`, `list`, and `show` constructs a new full runtime. The
`materialize_existing` path iterates existing citizens, regenerates cartridge
data, rewrites physical manifests, and indexes agents. The measurements saw
no child process, no Git invocation, no network call, and no post-return leak.
The `apply` command additionally calls `persist_city_runtime`, including a
Pokedex checkpoint; `list` and `show` return after serialization.

**Root cause:** the CLI has no lightweight campaign-only bootstrap and pays the
full city runtime/materialization cost three times per test. This is a real
performance/design inefficiency, but it did not fail in ten isolated sequences
or ten alternating pairs. It is not evidence of a shutdown bug.

### Shared versus distinct causes

Shared:

* both subprocess tests cold-start a heavyweight Agent City runtime;
* the 30-second limit is a test configuration default, not a product deadline;
* no remaining child processes were found after controlled termination.

Distinct:

* Heartbeat synchronously invokes a nested repository-wide pytest contract and
  deterministically exceeds the outer test limit;
* Campaign CLI performs three independent runtime builds and local materializer
  I/O, producing variable 24–44 s sequences but successful commands.

## Scheduler, Worker, Federation, and external-side-effect boundary

The recon found no Scheduler claim, Worker execution, Tool/LLM/Git side effect,
external Receipt, or Federation-wire change in either test path.

* Heartbeat does run governance hooks and can create local healing/proposal
  state when the nested contract fails.
* Campaign CLI does not call `Mayor.run_cycle`; it only builds the runtime and
  reads/applies campaign state.
* Both commands use `--offline`; no external Moltbook/GitHub call was observed.
* `federation=False` is passed by Campaign CLI; Slice-04 and Federation V1
  activation remain untouched.

## Joint fix decision and smallest implementation plan

The two surfaces must not be fixed by one timeout bump or one broad runtime
rewrite. They share an initialization cost but have different correctness
boundaries.

### Plan A1 — Heartbeat contract execution policy (Agent-B review required)

Before product code, decide and specify one of these bounded choices:

1. A one-cycle CLI smoke mode does not synchronously run the repository-wide
   `tests_pass` contract; contract evaluation is explicitly requested or
   supplied through a bounded, precomputed evidence path.
2. Governance retains synchronous contract checking, but the check scope is an
   explicitly provided target rather than implicit `Path.cwd()` and cannot
   recursively execute the full repository from inside the smoke path.

The choice must preserve contract failure semantics, local audit evidence, and
authority gates. It must include an adversarial test proving that production
Heartbeat/daemon mode cannot silently skip required governance checks. No
pytest timeout change is part of this plan.

### Plan A2 — Campaign CLI lightweight bootstrap (separate reviewable slice)

Specify a read/write-minimal campaign service boundary for `apply`, `list`, and
`show` that opens only the authoritative campaign persistence and required
schema services. It must not materialize agents, start a Scheduler/Worker,
invoke Mission/Tool/LLM/Git code, or change campaign persistence semantics.

The implementation must retain a full-runtime integration test separately and
prove that `apply` persistence is durable while `list`/`show` remain read-only.
The first slice should measure the new boundary against the current 24–44 s
sequence before changing any test timeout.

### Recommendation

Treat A1 as the first implementation plan because it is the deterministic
production-liveness defect and directly controls the reliability gate. Treat A2
as a second, independent performance/CLI architecture slice. Do not merge A1
and A2, do not raise the global timeout, and do not touch Federation code.

## Open decisions (maximum five)

1. Is `tests_pass` allowed synchronously inside a one-cycle Heartbeat, or must
   it become an explicit/bounded contract operation?
2. What exact evidence and authority gate replaces an implicit `Path.cwd()` if
   A1 scopes the contract target?
3. Which minimal persisted campaign schema/services are sufficient for A2?
4. How should full-runtime materialization remain covered after A2 without
   making every CLI read pay that cost?
5. What CI-specific cold-start budget should be measured after A1/A2, without
   changing the global pytest deadline as a masking tactic?

## Definition of Done for Slice A

* A1 and A2 decisions are separately reviewed and implementation-ready.
* No global timeout increase, skip, marker, or pytest configuration weakening.
* Heartbeat no longer recursively launches an unbounded repository test from
  the one-cycle smoke path, or the decision explicitly proves why it must.
* Campaign CLI has a measured minimal bootstrap or an evidence-backed decision
  to retain full bootstrap.
* Scheduler, Worker, Mission, Queue, Federation, external Receipt and
  activation paths remain unchanged and disabled.

