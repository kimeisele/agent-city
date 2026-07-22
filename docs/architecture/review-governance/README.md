# Review Governance / B1

Status: **Proposed — Senior Lead accepted in principle**

Implementation status: **NOT AUTHORIZED**.

Controlling issue: [ADR-B1: Canonical review verdict and unified merge authority](https://github.com/kimeisele/agent-city/issues/2495).

This package was prepared from Agent City baseline `6bd06b5bed5707e114be059f703ce690397944de` (the verified A1 merge). The related Steward main observed during the CI/Base Binding Gate was `2d6d86ff9b99452f8d642d015e913b70b1d6aad9`. Related existing evidence includes `docs/PR_GATE_DESIGN.md`, `docs/SYSTEM_REVIEW.md`, and the accepted maintenance/recon findings.

## Documents

- [ADR — Review Verdict and Merge Authority](ADR_REVIEW_VERDICT_AND_MERGE_AUTHORITY.md)
- [B1 Verdict Schema](VERDICT_SCHEMA_B1.md)
- [B1 Sequences](B1_SEQUENCES.md)
- [B1 Impact and Test Plan](B1_IMPACT_TESTPLAN_SLICES.md)

## Required order

1. **B1-S1** — schema, validator, and append-only verdict ledger;
2. **B1-S2** — canonical request and Steward emitter;
3. **B1-S3** — merge-authority cutover and required pull-request CI.

No implementation issues for these slices are created by this package. They require a later explicit work order.

## Open gate

The **CI/Base Binding Gate remains open until resolved**. In particular, the package records how `pull_request` workflows bind `GITHUB_SHA` to GitHub's synthetic merge ref and how `github.event.pull_request.head.sha` identifies the raw head. The signed `ReviewVerdictB1` is immutable H-bound evidence; `MergeReadinessEvaluationB1` is mutable local current-base evidence. The final policy and merge-time identity chain are documented, but B1 implementation remains blocked until Senior Lead review accepts this amendment and B1-S3 selects the concrete native H-evidence producer.

Amendment 0.2 separates those records and clarifies that a standard `pull_request` Actions job must not be described as an H-bound check. Until B1-S3 chooses a push workflow, explicit Check Run, or commit status (with permissions and fork behavior), H-security evidence remains an independently verified reference in the signed verdict.

## Non-goals

This package changes no Python, workflow, configuration, protocol, Federation, runtime, or activation behavior. It does not fix G-07 and does not start Federation Slice 04.
