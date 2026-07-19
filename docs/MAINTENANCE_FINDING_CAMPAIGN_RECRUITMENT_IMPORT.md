# Maintenance Finding — Campaign Recruitment Test Import

## Status

Open, separate from Federation Delegation Slice 03. No product or test fix is
included in the Slice-03 merge or its documentation pin.

## Reproduction

From a clean Agent City checkout at `main`:

```text
pytest -q
```

Collection stops with:

```text
ImportError while importing test module tests/test_campaign_recruitment.py
cannot import name '_detect_recruitment_gap'
from city.hooks.dharma.campaign_recruitment
```

The test imports `_detect_recruitment_gap` at
`tests/test_campaign_recruitment.py:11`; the symbol is absent from
`city/hooks/dharma/campaign_recruitment.py`.

## Scope and disposition

* This is unrelated to `city/federation_v1.py` and
  `tests/test_federation_v1_ready_work_item.py`.
* It does not invalidate the measured Slice-03 Federation and legacy smoke
  suites, which pass independently.
* It should receive a later small, separately reviewed maintenance PR.
* No automatic fix, import shim, or test exclusion is authorized as part of
  Slice 03.

## Evidence pin

Observed against final Agent City `main`:

`e4682c28905f6202eb6a92124b1eee3d01b0e3d2`
