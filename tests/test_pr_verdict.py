"""Tests for PRVerdictHook — DHARMA phase verdict processing.

Verifies:
- Approve (non-core) → auto-merge + comment
- Approve (core) → council proposal + comment
- Request changes → comment posted
- Reject → PR closed with comment
- Unknown verdicts are ignored
- Missing pr_number is handled gracefully

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from city.federation_nadi import FederationMessage
from city.hooks.dharma.pr_verdict import PRVerdictHook


def _make_ctx(*, has_council: bool = True, mayor: str = "sys_vyasa") -> MagicMock:
    """Build a minimal PhaseContext mock."""
    ctx = MagicMock()
    ctx.offline_mode = False
    ctx.federation_nadi = MagicMock()
    ctx.heartbeat_count = 100

    if has_council:
        ctx.council = MagicMock()
        ctx.council._elected_mayor = mayor
        ctx.council.propose.return_value = MagicMock()  # successful proposal
    else:
        ctx.council = None

    return ctx


def _make_verdict_message(
    verdict: str,
    pr_number: int = 42,
    touches_core: bool = False,
    reason: str = "Looks good.",
    title: str = "Fix typo",
) -> FederationMessage:
    """Build a FederationMessage with pr_review_verdict operation."""
    return FederationMessage(
        source="steward-protocol",
        target="agent-city",
        operation="pr_review_verdict",
        payload={
            "pr_number": pr_number,
            "verdict": verdict,
            "reason": reason,
            "title": title,
            "touches_core": touches_core,
        },
    )


def _make_non_verdict_message() -> FederationMessage:
    """Build a FederationMessage with a non-verdict operation."""
    return FederationMessage(
        source="steward-protocol",
        target="agent-city",
        operation="heartbeat_sync",
        payload={"status": "alive"},
    )


class TestPRVerdictHook:
    def setup_method(self):
        self.hook = PRVerdictHook()

    def test_name_phase_priority(self):
        assert self.hook.name == "pr_verdict"
        assert self.hook.phase == "dharma"
        assert self.hook.priority == 50

    def test_should_run_requires_nadi_and_online(self):
        ctx = _make_ctx()
        assert self.hook.should_run(ctx) is True

        ctx.federation_nadi = None
        assert self.hook.should_run(ctx) is False

        ctx.federation_nadi = MagicMock()
        ctx.offline_mode = True
        assert self.hook.should_run(ctx) is False

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_approve_non_core_auto_merges(self, mock_gh):
        """Approve + non-core → comment + merge."""
        mock_gh.return_value = "merged"
        ctx = _make_ctx()
        ctx.federation_nadi.receive.return_value = [
            _make_verdict_message("approve", pr_number=10, touches_core=False),
        ]
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        # Should have called gh twice: comment + merge
        assert mock_gh.call_count == 2
        comment_call = mock_gh.call_args_list[0]
        merge_call = mock_gh.call_args_list[1]
        assert "comment" in comment_call[0][0]
        assert "merge" in merge_call[0][0]
        assert "pr_verdict:merged:#10" in ops

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_approve_core_triggers_council(self, mock_gh):
        """Approve + core files → comment + council proposal, NO merge."""
        mock_gh.return_value = "ok"
        ctx = _make_ctx(has_council=True, mayor="sys_vyasa")
        ctx.federation_nadi.receive.return_value = [
            _make_verdict_message("approve", pr_number=20, touches_core=True, title="Big refactor"),
        ]
        ops: list[str] = []

        # Mock the council import inside _create_council_proposal
        mock_proposal_type = MagicMock()
        mock_proposal_type.POLICY = "policy"
        with patch.dict("sys.modules", {"city.council": MagicMock(ProposalType=mock_proposal_type)}):
            self.hook.execute(ctx, ops)

        # Should have posted comment but NOT merged
        assert mock_gh.call_count == 1  # only the comment
        comment_call = mock_gh.call_args_list[0]
        args = comment_call[0][0]
        assert "comment" in args
        # Find the --body flag and check the value after it
        body_idx = args.index("--body")
        assert "Council vote required" in args[body_idx + 1]

        # Council proposal should have been created
        ctx.council.propose.assert_called_once()

        assert "pr_verdict:council_vote:#20" in ops

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_request_changes_posts_comment(self, mock_gh):
        """Request changes → comment with reason."""
        mock_gh.return_value = "ok"
        ctx = _make_ctx()
        ctx.federation_nadi.receive.return_value = [
            _make_verdict_message("request_changes", pr_number=30, reason="Needs tests"),
        ]
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        mock_gh.assert_called_once()
        args = mock_gh.call_args[0][0]
        assert "comment" in args
        assert "30" in args
        assert "pr_verdict:changes_requested:#30" in ops

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_reject_closes_pr(self, mock_gh):
        """Reject → close PR with comment."""
        mock_gh.return_value = "ok"
        ctx = _make_ctx()
        ctx.federation_nadi.receive.return_value = [
            _make_verdict_message("reject", pr_number=40, reason="Violates governance"),
        ]
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        mock_gh.assert_called_once()
        args = mock_gh.call_args[0][0]
        assert "close" in args
        assert "40" in args
        assert "pr_verdict:rejected:#40" in ops

    def test_non_verdict_messages_ignored(self):
        """Non-verdict NADI messages are silently skipped."""
        ctx = _make_ctx()
        ctx.federation_nadi.receive.return_value = [_make_non_verdict_message()]
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        assert len(ops) == 0

    def test_missing_pr_number_handled(self):
        """Verdict without pr_number → warning, no crash."""
        ctx = _make_ctx()
        msg = FederationMessage(
            source="steward",
            target="agent-city",
            operation="pr_review_verdict",
            payload={"verdict": "approve", "reason": "ok"},
        )
        ctx.federation_nadi.receive.return_value = [msg]
        ops: list[str] = []

        self.hook.execute(ctx, ops)
        assert len(ops) == 0

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_approve_core_without_council(self, mock_gh):
        """Approve + core + no council → comment only, no proposal."""
        mock_gh.return_value = "ok"
        ctx = _make_ctx(has_council=False)
        ctx.federation_nadi.receive.return_value = [
            _make_verdict_message("approve", pr_number=50, touches_core=True),
        ]
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        # Comment posted, no council interaction
        assert mock_gh.call_count == 1
        assert "pr_verdict:council_vote:#50" in ops

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_merge_failure_recorded(self, mock_gh):
        """Merge returning None → merge_failed operation."""
        # First call (comment) succeeds, second (merge) fails
        mock_gh.side_effect = ["ok", None]
        ctx = _make_ctx()
        ctx.federation_nadi.receive.return_value = [
            _make_verdict_message("approve", pr_number=60, touches_core=False),
        ]
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        assert "pr_verdict:merge_failed:#60" in ops
