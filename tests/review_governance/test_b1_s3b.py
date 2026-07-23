from __future__ import annotations

import ast
import json

import pytest

from city.review_governance import (
    FinalMergeSnapshotB1,
    DisabledBreakGlass,
    MergeAuthorityError,
    ReviewGovernanceMergeAuthority,
    TrustConfigError,
    load_trusted_producers,
)
from city.review_governance.live_evidence import (
    GitHubJSONClient,
    GitHubLiveEvidenceProvider,
)
from city.review_governance.schema import EvidenceRefB1
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


def _state(
    *, merged: bool = False, final_merge_sha: str | None = None, ledger_head: str | None = None
):
    return FinalMergeSnapshotB1(
        REPO,
        42,
        HEAD,
        BASE,
        MERGE,
        "open",
        "mergeable",
        "verified",
        "head-1",
        "verified",
        "merge-1",
        "not_required",
        "evaluation-1",
        False,
        ledger_head,
        merged,
        final_merge_sha,
        "2026-07-23T12:00:00Z",
    )


def test_merge_authority_is_disabled_by_default() -> None:
    with pytest.raises(MergeAuthorityError, match="MERGE_AUTHORITY_DISABLED"):
        ReviewGovernanceMergeAuthority().merge(
            evaluation=_evaluation(),
            final_resolver=object(),
            actor="test",
            request_base_sha=BASE,
        )


def test_merge_is_expected_head_bound_and_records_final_sha(tmp_path) -> None:
    runner = Runner()
    from city.review_governance.ledger import ShadowLedger

    ledger = ShadowLedger(tmp_path / "ledger.jsonl")
    # Seed the readiness lineage required by final revalidation.
    ledger.append(
        "merge_readiness_evaluated",
        "evaluation-1",
        {
            "repository": REPO,
            "pull_request_number": 42,
            "reviewed_head_sha": HEAD,
            "evaluation_id": "evaluation-1",
        },
    )
    states = iter(
        [
            _state(ledger_head=ledger.read()[-1]["event_digest"]),
            _state(ledger_head=None),
            _state(merged=True, final_merge_sha="d" * 40, ledger_head=None),
        ]
    )

    def final_state():
        state = next(states)
        return FinalMergeSnapshotB1(
            state.repository,
            state.pull_request_number,
            state.current_head_sha,
            state.current_base_sha,
            state.current_integration_check_sha,
            state.pr_state,
            state.mergeability_state,
            state.head_evidence_state,
            state.head_evidence_identity,
            state.integration_evidence_state,
            state.integration_evidence_identity,
            state.council_state,
            state.latest_readiness_evaluation_id,
            state.readiness_invalidated,
            ledger.read()[-1]["event_digest"],
            state.merged,
            state.final_merge_sha,
            state.observed_at,
        )

    class Resolver:
        def resolve(self):
            return final_state()

    result = ReviewGovernanceMergeAuthority(enabled=True, runner=runner, ledger=ledger).merge(
        evaluation=_evaluation(),
        final_resolver=Resolver(),
        actor="test",
        request_base_sha=BASE,
    )
    assert result.final_merge_sha == "d" * 40
    assert runner.calls == [
        ["pr", "merge", "42", "--repo", REPO, "--squash", "--match-head-commit", HEAD]
    ]
    event = next(event for event in ledger.read() if event["event_type"] == "merge_completed")
    assert event["event_type"] == "merge_completed"
    assert event["payload"]["reviewed_head_sha"] == HEAD
    assert event["payload"]["final_merge_sha"] == "d" * 40


def test_trust_configuration_is_explicit_and_scoped() -> None:
    with pytest.raises(TrustConfigError):
        load_trusted_producers(None)
    config = load_trusted_producers(
        json.dumps(
            [
                {
                    "repository": REPO,
                    "policy_name": "review-governance/head",
                    "provider": "github_check",
                    "producer_identity": "trusted-app",
                }
            ]
        )
    )
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


class PagedClient(GitHubJSONClient):
    def __init__(self):
        super().__init__(token="test")

    def _request(self, path):
        if "page=2" in path:
            return [{"id": 2}], {}
        return [{"id": 1}] * 100, {
            "Link": '<https://api.github.com/repos/x/y/statuses?page=2>; rel="next"'
        }


def test_github_collection_pagination_collects_page_two() -> None:
    assert [item["id"] for item in PagedClient().get_all("/repos/x/y/statuses?per_page=100")] == [
        *([1] * 100),
        2,
    ]


class EvidenceClient:
    def get_all(self, path, *, collection_key=None, max_pages=20):
        return [
            {
                "name": "review-governance/head",
                "head_sha": HEAD,
                "conclusion": "success",
                "id": 7,
                "app": {"slug": "trusted-app"},
                # Deliberately absent: provenance must not use local time.
            }
        ]


def test_missing_github_timestamp_is_unavailable() -> None:
    reference = EvidenceRefB1.from_mapping(
        {
            "kind": "head_security_evidence",
            "sha": HEAD,
            "provider": "github_check",
            "name": "review-governance/head",
            "evidence_digest": "sha256:" + "0" * 64,
        }
    )
    result = GitHubLiveEvidenceProvider(EvidenceClient()).resolve(
        repository=REPO,
        pull_request_number=42,
        reviewed_head_sha=HEAD,
        evidence_ref=reference,
    )
    assert result.state == "unavailable"
    assert result.error_code == "EVIDENCE_TIMESTAMP_UNAVAILABLE"
