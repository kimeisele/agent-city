# Maintenance Baseline 22 — Triage

## Scope and authoritative pins

Repository: `kimeisele/agent-city`

* Maintenance PR #2247 merge commit: `9c6770e9ef8982971b8c39e1c21ab2fefacda3da`
* Final `main` tested: `9c6770e9ef8982971b8c39e1c21ab2fefacda3da`
* Exact Base used for the accepted comparison: `128310d6e28d22d39013d12a85f4104da93230b5`
* Exact pre-merge Head used for the accepted comparison: `95e5574b4ad926c77d8eb67b5f3baf32ae46b2bc`
* Baseline source: `docs/MAINTENANCE_CAMPAIGN_RECRUITMENT_BASELINE.json`

This is documentation-only. It does not repair any failure, change tests,
change Federation code, alter a pytest gate, or begin Slice 04. The feature
gate remains `false`; disposition remains `disabled`; no product activation
occurred.

## Evidence boundary

The accepted Base/Head comparison used the same ignored synthetic Federation
test-key setup and a temporary test-only migration on Base. It established 22
identical deterministic failure nodes and identical first failure classes. The
unmodified Base was collection-blocked by the known stale campaign import.

Post-merge smoke against final `main` produced:

* Campaign Recruitment focus: `14 passed`.
* Federation/Slice suites: `178 passed`.
* Legacy/Mission/Heal suites: `144 passed`.
* Ruff and `py_compile`: passed.
* Full `pytest -q`: `1922 passed, 23 failed, 1 skipped`.

The full post-merge run contained the 22 baseline nodes below plus one extra
timeout, `tests/test_campaign_cli.py::test_campaign_cli_apply_list_show`.
That additional test passed in two separate focused runs (`1 passed` each;
30.00 s and 27.58 s), so it is classified as a non-baseline timeout/flake and
not as a deterministic PR regression. It requires a separate timeout/runtime
investigation before the repository-wide gate can be considered reliable.

## Cluster summary and recommended order

| order | cluster | nodes | determinism | production risk | nearest boundary | smallest independent slice |
| ---: | --- | ---: | --- | --- | --- | --- |
| 1 | Heartbeat/CLI Timeout | 1 baseline + 1 post-merge observation | baseline deterministic; campaign CLI timeout flaky | high: runtime liveness and operator gate | heartbeat/runtime; indirect Federation | measure subprocess startup/teardown and isolate timeout budget; do not change Federation |
| 2 | Brain/Action | 2 | deterministic | medium/high: decision and action dispatch contracts | cognitive dispatch; indirect Worker | reconcile `ThoughtKind` tier mapping and `ActionVerb` cardinality in one contract-focused slice |
| 3 | Issue Binding | 1 | deterministic | medium: issue/task authorization binding | governance/task binding | correct `CityIssueManager.is_issue_open` semantics and focused state tests |
| 4 | PR-Gate E2E | 4 | deterministic | high: merge/review authority evidence | PR gate/governance | trace `_gh_run` wiring and restore mocked call contract without changing production authorization |
| 5 | Governance/Layer | 8 | deterministic | high: election, proposal, federation directive flow | governance; Layer 6 touches Federation behavior | split Layer 5 election/proposal and Layer 6 directive acknowledgement into separate focused slices |
| 6 | Moltbook Bridge | 4 | deterministic | medium: external communication only | external bridge, not Federation wire | decide whether removed bridge methods require test migration or an explicitly restored adapter contract |
| 7 | Prompt Registry | 1 | deterministic | medium: prompt selection | LLM/cognitive surface | reconcile registry cardinality with the current builder contract |
| 8 | Treasury | 1 | deterministic | medium: outbound fallback path | external side effect boundary | decide whether `MoltbookOutboundHook` was intentionally removed; migrate the stale test or restore the narrow adapter |
| 9 | Pokedex Concurrency | 0 in the accepted 22-set | not observed | unknown until reproduced | worker/state concurrency | no fix slice until a current reproducible node exists |

Recommended execution order is the table order. The timeout cluster comes
first because a non-deterministic full-run gate can mask every later result.
PR-Gate and governance findings precede external bridge/treasury cleanup because
they affect authority evidence. No cluster should be combined into a monster
PR.

## Exact deterministic baseline nodes

All rows below have `base_present=true`, `head_present=true`, identical first
failure classes, and `deterministic_second_run=true` in the machine-readable
baseline artifact.

### Brain/Action

* `tests/test_brain.py::TestModelTier::test_all_thought_kinds_have_tier` — `AssertionError`; `social_strategy` has no `_KIND_TIER` mapping. Owner candidates: `city/brain.py` tier registry and its contract tests. Production risk: missing model-tier routing. Smallest slice: add or explicitly retire the mapping after an ADR-like test contract decision.
* `tests/test_brain_action.py::TestActionVerb::test_all_9_verbs` — `AssertionError`; `ActionVerb` has 10 members while the test expects 9. Owner candidate: `city/brain_action.py` enum contract. Production risk: action-schema drift. Smallest slice: reconcile enum and test cardinality without changing Federation operations.

### Heartbeat/CLI Timeout

* `tests/test_heartbeat_campaign_bootstrap.py::test_heartbeat_cli_smoke_with_campaign_manifest` — `pytest_timeout`; heartbeat CLI exceeds the 30-second subprocess limit. Owner candidates: `scripts/heartbeat.py`, bootstrap and shutdown paths. Production risk: operational liveness and false-red CI. Smallest slice: profile startup/teardown and make the timeout budget explicit.

### Issue Binding

* `tests/test_issue_binding.py::test_issue_open_and_bound_helpers` — `AssertionError`; `is_issue_open(99)` returns true for an absent issue in the fixture state. Owner candidate: `city/issue_binding.py`. Production risk: incorrect task/issue authority. Smallest slice: fix absent-ID semantics and add state-boundary tests.

### Governance/Layer

* `tests/test_layer5.py::test_mayor_runs_election_in_dharma` — `AssertionError`; no election action is emitted.
* `tests/test_layer5.py::test_full_rotation_with_council` — `AssertionError`; no election operation is emitted.
* `tests/test_layer5.py::test_contract_failure_creates_proposal` — `AssertionError`; failing contract creates no open proposal.
* `tests/test_layer6.py::test_full_rotation_with_federation` — `AssertionError`; expected `DIR-FULL` directive acknowledgement is absent.
* `tests/test_layer6.py::test_create_mission_directive_creates_mission_and_proposal` — `AssertionError`; expected federation council proposal is absent.
* `tests/test_mayor_execution.py::test_execution_bridge_routes_genesis` — `AttributeError`; test context lacks `city_nadi`.
* `tests/test_mayor_execution.py::test_execution_bridge_runs_moksha_self_diagnostics` — `AttributeError`; test context lacks `city_nadi`.
* `tests/test_mayor_execution.py::test_heartbeat_updates_persisted_totals` — `AssertionError`; first event is `MURALI`, while the test expects `KARMA`.

Owner candidates are `city/phases/dharma.py`, Layer 5/6 orchestration and the
Mayor execution bridge. Production risk is governance and, for Layer 6,
Federation-adjacent directive flow. The smallest repair is two independent
slices: Layer 5 election/proposal semantics, then Layer 6 federation directive
and Mayor-context contracts. Do not connect Worker or Federation Delegation
execution as part of either repair.

### Moltbook Bridge

* `tests/test_layer6.py::test_bridge_post_cooldown` — `AttributeError`; `MoltbookBridge.post_city_update` is absent.
* `tests/test_layer6.py::test_bridge_post_format` — `AttributeError`; `MoltbookBridge.post_city_update` is absent.
* `tests/test_layer6.py::test_bridge_mission_result_post` — `AttributeError`; `MoltbookBridge.post_mission_results` is absent.
* `tests/test_layer6.py::test_bridge_directive_acks_in_content` — `AttributeError`; `MoltbookBridge.post_city_update` is absent.

Owner candidate: the Moltbook bridge adapter and its migrated public surface.
Production risk is bounded external communication, not Federation wire
correctness. The smallest slice is a read-only decision: migrate tests to the
current `post_agent_update` contract or restore only the explicitly intended
adapter methods. No automatic external posting should be enabled.

### PR-Gate E2E

* `tests/test_pr_gate_e2e.py::TestE2EPRGatePipeline::test_verdict_reads_from_real_nadi_inbox` — `AssertionError`; mocked `_gh_run` call count is 0 instead of 2.
* `tests/test_pr_gate_e2e.py::TestE2EPRGatePipeline::test_full_pipeline_scanner_to_verdict` — `AssertionError`; mocked `_gh_run` call count is 0 instead of 2.
* `tests/test_pr_gate_e2e.py::TestE2EPRGatePipeline::test_full_pipeline_core_file_escalation` — `AssertionError`; mocked `_gh_run` call count is 0 instead of 1.
* `tests/test_pr_gate_e2e.py::TestE2EPRGatePipeline::test_full_pipeline_rejection` — `AssertionError`; mocked `_gh_run` call count is 0 instead of 1.

Owner candidates: PR-gate pipeline, NADI inbox integration and the GitHub
adapter seam. Production risk is high because merge/review evidence may be
misreported. Smallest slice: trace the call path and reconcile the test double
with the current adapter; do not weaken authority gates or invoke real GitHub
side effects.

### Prompt Registry

* `tests/test_prompt_registry.py::TestGetPromptRegistry::test_singleton_has_all_6_builders` — `AssertionError`; registry contains 7 builders while the test expects 6. Owner candidate: `city/prompt_registry.py`. Production risk: prompt selection drift. Smallest slice: define the current builder set and update either registry or contract test.

### Treasury

* `tests/test_treasury.py::TestMoltbookOutboundFallback::test_fallback_path_exists` — `ImportError`; `MoltbookOutboundHook` is absent from `city.hooks.moksha.outbound`. Owner candidate: Moksha outbound adapter. Production risk: fallback-path observability; external posting remains disabled. Smallest slice: determine whether removal was intentional and migrate the test or restore the narrow symbol.

## Post-merge timeout observation outside the 22-node baseline

* `tests/test_campaign_cli.py::test_campaign_cli_apply_list_show` timed out
  during the full post-merge run while executing the `show` subprocess.
* Focused rerun 1: `1 passed` in `30.00s`.
* Focused rerun 2: `1 passed` in `27.58s`.

This is not evidence of a Campaign-Recruitment product regression. It is an
environment-sensitive subprocess-duration finding and belongs in the same
timeout/measurement maintenance slice as the heartbeat CLI timeout, with its
own node and timing evidence.

## Explicit non-goals and Slice-04 gate

No fixes are included here. The following remain locked:

* Slice 04 and any ownership/claim/lease work;
* Worker, Scheduler, Mission, Queue, Tool, LLM, Git or PR execution;
* external Assignment or Started receipts;
* Recovery automation, Status Query, terminal or Verification receipts;
* Context Bridge, Provider Failover and Execution-Spine expansion;
* productive activation or automatic merge authority.

Slice 04 may not begin until each baseline cluster has a reproducible owner and
decision, the timeout behavior is made a reliable gate, and no hidden
Scheduler/Worker/Governance/Federation foundation break remains unclassified.
