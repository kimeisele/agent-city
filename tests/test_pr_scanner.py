"""Tests for PRScannerHook — GENESIS phase PR scanning.

Verifies:
- Open PRs are fetched and NADI review requests emitted
- Already-processed PRs are skipped
- Core file detection works correctly
- Citizen status is checked via Pokedex

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from city.hooks.genesis.pr_scanner import CORE_FILES, PRScannerHook, _processed_prs


@pytest.fixture(autouse=True)
def _clear_processed():
    """Reset processed PR set between tests."""
    _processed_prs.clear()
    yield
    _processed_prs.clear()


def _make_ctx(*, citizen_exists: bool = False) -> MagicMock:
    """Build a minimal PhaseContext mock."""
    ctx = MagicMock()
    ctx.offline_mode = False
    ctx.federation_nadi = MagicMock()
    ctx.pokedex = MagicMock()
    ctx.pokedex.get.return_value = {"name": "test-agent"} if citizen_exists else None
    return ctx


def _make_pr(
    number: int = 1,
    author: str = "alice",
    title: str = "Fix typo",
    files: list[str] | None = None,
) -> dict:
    """Build a PR dict matching the scanner's expected format."""
    if files is None:
        files = ["README.md"]
    return {
        "number": number,
        "author": {"login": author},
        "title": title,
        "body": "Some description",
        "files": [{"path": f} for f in files],
    }


class TestPRScannerHook:
    def setup_method(self):
        self.hook = PRScannerHook()

    def test_name_phase_priority(self):
        assert self.hook.name == "pr_scanner"
        assert self.hook.phase == "genesis"
        assert self.hook.priority == 56

    def test_should_run_requires_nadi_and_online(self):
        ctx = _make_ctx()
        assert self.hook.should_run(ctx) is True

        ctx.federation_nadi = None
        assert self.hook.should_run(ctx) is False

        ctx.federation_nadi = MagicMock()
        ctx.offline_mode = True
        assert self.hook.should_run(ctx) is False

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_emits_nadi_message_for_new_pr(self, mock_fetch):
        """New PR → NADI pr_review_request emitted."""
        mock_fetch.return_value = [_make_pr(number=42, author="bob", files=["city/foo.py"])]
        ctx = _make_ctx(citizen_exists=True)
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        ctx.federation_nadi.emit.assert_called_once()
        call_kwargs = ctx.federation_nadi.emit.call_args
        assert call_kwargs.kwargs["operation"] == "pr_review_request"

        payload = call_kwargs.kwargs["payload"]
        assert payload["pr_number"] == 42
        assert payload["author"] == "bob"
        assert payload["is_citizen"] is True
        assert payload["touches_core"] is False
        assert payload["core_files"] == []

        assert len(ops) == 1
        assert "pr_scanner:review_request:#42" in ops[0]

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_skips_already_processed_pr(self, mock_fetch):
        """Already-seen PRs are not re-emitted."""
        mock_fetch.return_value = [_make_pr(number=10)]
        ctx = _make_ctx()
        ops: list[str] = []

        self.hook.execute(ctx, ops)
        assert len(ops) == 1

        # Run again — same PR should be skipped
        ops.clear()
        self.hook.execute(ctx, ops)
        assert len(ops) == 0

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_detects_core_files(self, mock_fetch):
        """PR touching core files → touches_core=True in payload."""
        core_file = list(CORE_FILES)[0]
        mock_fetch.return_value = [
            _make_pr(number=99, files=[core_file, "city/utils.py"]),
        ]
        ctx = _make_ctx()
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        payload = ctx.federation_nadi.emit.call_args.kwargs["payload"]
        assert payload["touches_core"] is True
        assert core_file in payload["core_files"]

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_non_citizen_author(self, mock_fetch):
        """Non-citizen author → is_citizen=False."""
        mock_fetch.return_value = [_make_pr(number=7, author="outsider")]
        ctx = _make_ctx(citizen_exists=False)
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        payload = ctx.federation_nadi.emit.call_args.kwargs["payload"]
        assert payload["is_citizen"] is False

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_fetch_failure_is_non_fatal(self, mock_fetch):
        """GitHub API failure → no crash, no operations."""
        mock_fetch.side_effect = Exception("network error")
        ctx = _make_ctx()
        ops: list[str] = []

        self.hook.execute(ctx, ops)
        assert len(ops) == 0
        ctx.federation_nadi.emit.assert_not_called()

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_multiple_prs_all_emitted(self, mock_fetch):
        """Multiple new PRs → one NADI message each."""
        mock_fetch.return_value = [
            _make_pr(number=1, author="alice"),
            _make_pr(number=2, author="bob"),
            _make_pr(number=3, author="carol"),
        ]
        ctx = _make_ctx()
        ops: list[str] = []

        self.hook.execute(ctx, ops)

        assert ctx.federation_nadi.emit.call_count == 3
        assert len(ops) == 3
