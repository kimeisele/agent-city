from __future__ import annotations

import ast
import json

import pytest

from city.review_governance import (
    CurrentMergeStateB1,
    DisabledBreakGlass,
    MergeAuthorityError,
    ReviewGovernanceMergeAuthority,
    TrustConfigError,
    load_trusted_producers,
)
from city.review_governance.schema import MergeReadinessEvaluationB1

REPO = "kimeisele/agent-city"
HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40


def _evaluation() -> MergeReadinessEvaluationB1:
    return MergeReadinessEvaluationB1.from_mapping(
        {
            "schema": "merge-readiness-evaluation-b1.1",
            "evaluation_id": "evaluation-1",
            "verdict_id": "verdict-1",
            "repository": REPO,
            "pull_request_number": 42,
            "reviewed_head_sha": HEAD,
            "validated_current_base_sha": BASE,
            "integration_check_sha": MERGE,
            "required_check_results": [
                {
                    "name": "review-governance/merge-result",
                    "head_sha": MERGE,
                    "conclusion": "success",
                    "run_id": "run-1",
                }
            ],
            "base_drift_classification": "none",
            "scope_overlap_result": "none",
            "core_gate_state": "non_core",
            "council_state": "not_required",
            "merge_expected_head_sha": HEAD,
            "readiness_state": "ready",
            "evaluated_at": "2026-07-23T12:00:00Z",
        }
    )


class Runner:
    def __init__(self, merged: bool = True):
        self.calls: list[list[str]] = []
        self.merged = merged

    def run(self, args: list[str]) -> str | None:
        self.calls.append(args)
        return "ok" if self.merged else None


def test_merge_authority_is_disabled_by_default() -> None:
    with pytest.raises(MergeAuthorityError, match="MERGE_AUTHORITY_DISABLED"):
        ReviewGovernanceMergeAuthority().merge(
            evaluation=_evaluation(),
            current_state=lambda: CurrentMergeStateB1(REPO, 42, HEAD, BASE, MERGE),
            actor="test",
            request_base_sha=BASE,
        )


def test_merge_is_expected_head_bound_and_records_final_sha(tmp_path) -> None:
    runner = Runner()
    from city.review_governance.ledger import ShadowLedger

    ledger = ShadowLedger(tmp_path / "ledger.jsonl")
    states = iter(
        [
            CurrentMergeStateB1(REPO, 42, HEAD, BASE, MERGE),
            CurrentMergeStateB1(REPO, 42, HEAD, BASE, MERGE, True, "d" * 40),
        ]
    )
    result = ReviewGovernanceMergeAuthority(enabled=True, runner=runner, ledger=ledger).merge(
        evaluation=_evaluation(),
        current_state=lambda: next(states),
        actor="test",
        request_base_sha=BASE,
    )
    assert result.final_merge_sha == "d" * 40
    assert runner.calls == [[
        "pr", "merge", "42", "--repo", REPO, "--squash", "--match-head-commit", HEAD
    ]]
    event = ledger.read()[0]
    assert event["event_type"] == "merge_completed"
    assert event["payload"]["reviewed_head_sha"] == HEAD
    assert event["payload"]["final_merge_sha"] == "d" * 40


def test_trust_configuration_is_explicit_and_scoped() -> None:
    with pytest.raises(TrustConfigError):
        load_trusted_producers(None)
    config = load_trusted_producers(json.dumps([{
        "repository": REPO,
        "policy_name": "review-governance/head",
        "provider": "github_check",
        "producer_identity": "trusted-app",
    }]))
    assert config.policy().is_trusted(
        repository=REPO,
        policy_name="review-governance/head",
        provider="github_check",
        producer_identity="trusted-app",
    )
    assert not config.policy().is_trusted(
        repository="other/repo",
        policy_name="review-governance/head",
        provider="github_check",
        producer_identity="trusted-app",
    )


def test_break_glass_is_disabled() -> None:
    with pytest.raises(MergeAuthorityError, match="BREAK_GLASS_DISABLED"):
        DisabledBreakGlass().invoke(actor="admin", reason="test")


def test_only_merge_authority_contains_merge_mutation() -> None:
    lifecycle = ast.parse(open("city/pr_lifecycle.py", encoding="utf-8").read())
    verdict = ast.parse(open("city/hooks/dharma/pr_verdict.py", encoding="utf-8").read())
    for tree in (lifecycle, verdict):
        source = ast.unparse(tree)
        assert "gh pr merge" not in source
        assert "--match-head-commit" not in source
