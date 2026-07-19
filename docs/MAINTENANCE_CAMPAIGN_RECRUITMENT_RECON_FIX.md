# Maintenance Recon/Fix — Campaign Recruitment Collection Drift

## Scope and pin

Repository: `kimeisele/agent-city`

Recon baseline: Agent City `main` at
`128310d6e28d22d39013d12a85f4104da93230b5`.

Maintenance branch: `fix/maintenance-campaign-recruitment-import`.

Product/test fix commit:
`cbf7dbfae5173b1727389a2b60567792c25b9732`.

This is a separate maintenance change. It does not modify Federation code,
Federation wire models, fixtures, Slice 01A/02/03 behavior, or any Slice-04
surface.

## Read-only recon method

Git history was inspected with case-insensitive `heartbeat` commits excluded
from the relevant path logs:

```text
git log --regexp-ignore-case --invert-grep --grep=heartbeat \
  -- city/hooks/dharma/campaign_recruitment.py
git log --regexp-ignore-case --invert-grep --grep=heartbeat \
  -- tests/test_campaign_recruitment.py
```

Relevant non-heartbeat history:

* `4987d10c8b096e6f8446088eb329f97ffe756eea` introduced the original static
  `_RECRUITMENT_TARGETS` map, `_detect_recruitment_gap`, and tests importing
  both symbols.
* `029e4192505d0e24cab300db99cd449a7fccab4c` intentionally replaced that
  static keyword detector with `_detect_target_config(gap_text, campaign)`.
  The production hook then consumed campaign-owned `recruitment_targets` and
  compiler-generated `recruitment_gap:{id}:{issue}:{title}` records. The test
  file was not migrated in that commit.
* `d97d0e7750896ff85e1b906e734da5edffb0496b` removed the outbound Moltbook
  behavior but left three imports that became unused.

No current production caller imports `_detect_recruitment_gap` or
`_RECRUITMENT_TARGETS`. The only stale imports were in
`tests/test_campaign_recruitment.py`.

## Root cause

The full test run stopped during collection because the test imported two
symbols that were intentionally removed when the hook changed from a static
keyword registry to campaign-owned configuration. This was test/implementation
drift, not missing production functionality.

The current authoritative path is:

```text
CampaignRegistry._compute_gaps()
  -> recruitment_gap:{target_id}:{github_issue}:{title}
  -> CampaignRecruitmentHook._detect_target_config(gap, campaign)
  -> campaign.recruitment_targets
  -> _create_recruitment_bounty()
```

## Smallest correct fix

`cbf7dbf` makes only these changes:

1. Updates the tests to import and exercise `_detect_target_config`.
2. Uses the authoritative `campaigns/default.json` federation-recruitment
   manifest through `CampaignRecord.from_dict` rather than recreating the old
   removed static target map.
3. Uses compiler-shaped `recruitment_gap:` strings in hook tests.
4. Makes same-cycle deduplication assert exactly one bounty for the same
   target.
5. Removes three unused imports left in the production hook after the prior
   intentional behavior removal (`Any`, `SVC_MOLTBOOK_CLIENT`, and the unused
   Moltbook poster import).

No import shim, dummy function, `try/except ImportError`, skip, test
configuration change, or Federation change was introduced.

## Validation

Against the maintenance branch and the existing ignored synthetic Federation
test-key asset supplied only to the local test environment:

```text
ruff check city/hooks/dharma/campaign_recruitment.py \
  tests/test_campaign_recruitment.py
  All checks passed

python -m py_compile city/hooks/dharma/campaign_recruitment.py \
  tests/test_campaign_recruitment.py
  passed

pytest -q tests/test_campaign_recruitment.py
  14 passed, 1 warning

pytest -q tests/test_federation_v1_assignment.py \
  tests/test_federation_v1_admission.py \
  tests/test_federation_v1_hardening.py \
  tests/test_federation_nadi.py tests/test_federation_relay.py tests/federation_v1
  178 passed, 1 warning

pytest -q tests/test_mission_router.py tests/test_city_router.py \
  tests/test_federation_nadi.py tests/test_federation_relay.py tests/test_layer4.py
  144 passed, 184 warnings
```

The complete `pytest -q` now completes collection and executes the whole
repository. Its current result is:

```text
1922 passed, 23 failed, 1 skipped, 3153 warnings
```

The 23 failures are pre-existing, unrelated baseline failures in brain/action,
heartbeat CLI timeout, issue binding, governance/layer tests, Moltbook bridge,
PR-gate E2E, prompt registry, treasury, and Pokedex concurrency. The Campaign
Recruitment tests pass; no failure names point to the changed two files. The
full run is therefore no longer collection-blocked, but the repository-wide
gate is not green until those separate maintenance areas are addressed.

The ignored `tests/fixtures/federation_v1/keys/test_keys.json` is synthetic,
test-only material and was not changed or committed. No Slice-03 artifact or
Federation wire contract was altered.

## Explicit non-scope

This maintenance PR does not:

* begin Slice 04;
* add Worker, Scheduler, Lease, Claim, Reservation, Mission, Queue, Tool,
  LLM, Git, or external Receipt behavior;
* change Steward, agent-federation, agent-internet, Federation wire schemas,
  Golden Fixtures, or runtime activation;
* repair any of the 23 unrelated full-suite failures.

Feature-gate state remains `false`; disposition remains `disabled`.
