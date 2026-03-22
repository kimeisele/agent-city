"""
END-TO-END Test: PR Gate Pipeline — Scanner → NADI → Verdict → Action.

Simulates the full flow:
1. PRScannerHook detects a PR (mocked GitHub API)
2. NADI outbox receives pr_review_request
3. Steward verdict arrives in NADI inbox
4. PRVerdictHook processes verdict → correct action

This proves the fourth membrane surface works end-to-end.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from city.federation_nadi import FederationMessage, FederationNadi
from city.hooks.dharma.pr_verdict import PRVerdictHook
from city.hooks.genesis.pr_scanner import PRScannerHook, _processed_prs
from city.hooks.genesis.federation import FederationNadiHook


@pytest.fixture(autouse=True)
def _clear_state():
    """Reset processed PR set between tests."""
    _processed_prs.clear()
    yield
    _processed_prs.clear()


def _make_ctx_with_real_nadi(tmp_path: Path, *, citizen: bool = False) -> MagicMock:
    """Build a PhaseContext with a REAL FederationNadi (file-based)."""
    fed_dir = tmp_path / "federation"
    fed_dir.mkdir()

    # Write a minimal peer.json for federation identity
    (fed_dir / "peer.json").write_text(json.dumps({
        "identity": {"city_id": "agent-city", "slug": "agent-city"},
    }))

    nadi = FederationNadi(_federation_dir=fed_dir)

    ctx = MagicMock()
    ctx.offline_mode = False
    ctx.federation_nadi = nadi
    ctx.city_nadi = None
    ctx._city_nadi = None
    ctx.pokedex = MagicMock()
    ctx.pokedex.get.return_value = {"name": "test-citizen"} if citizen else None
    ctx.council = None
    ctx.heartbeat_count = 42
    ctx.gateway_queue = []

    return ctx


class TestE2EPRGatePipeline:
    """Full pipeline: Scanner → NADI → Verdict → Action."""

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_scanner_writes_to_real_nadi_outbox(self, mock_fetch, tmp_path):
        """GENESIS: Scanner detects PR → writes pr_review_request to NADI outbox."""
        mock_fetch.return_value = [{
            "number": 99,
            "author": {"login": "alice"},
            "title": "test: PR Gate E2E",
            "body": "Testing the PR review pipeline.",
            "files": [{"path": "README.md"}],
        }]

        ctx = _make_ctx_with_real_nadi(tmp_path, citizen=True)
        scanner = PRScannerHook()
        ops: list[str] = []

        # GENESIS phase: scanner runs
        scanner.execute(ctx, ops)

        # Verify NADI outbox has the message
        ctx.federation_nadi.flush()

        outbox_data = json.loads(ctx.federation_nadi.outbox_path.read_text())
        assert len(outbox_data) == 1

        msg = outbox_data[0]
        assert msg["operation"] == "pr_review_request"
        assert msg["payload"]["pr_number"] == 99
        assert msg["payload"]["author"] == "alice"
        assert msg["payload"]["is_citizen"] is True
        assert msg["payload"]["touches_core"] is False

        assert len(ops) == 1
        assert "pr_scanner:review_request:#99" in ops[0]

    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_scanner_detects_core_file_in_real_nadi(self, mock_fetch, tmp_path):
        """GENESIS: Scanner flags core files in NADI message."""
        mock_fetch.return_value = [{
            "number": 100,
            "author": {"login": "mallory"},
            "title": "refactor: rewrite immune system",
            "body": "Big changes.",
            "files": [{"path": "city/immune.py"}, {"path": "city/immigration.py"}],
        }]

        ctx = _make_ctx_with_real_nadi(tmp_path, citizen=False)
        scanner = PRScannerHook()
        ops: list[str] = []

        scanner.execute(ctx, ops)
        ctx.federation_nadi.flush()

        outbox_data = json.loads(ctx.federation_nadi.outbox_path.read_text())
        payload = outbox_data[0]["payload"]

        assert payload["touches_core"] is True
        assert "city/immune.py" in payload["core_files"]
        assert "city/immigration.py" in payload["core_files"]
        assert payload["is_citizen"] is False

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    def test_verdict_reads_from_real_nadi_inbox(self, mock_gh, tmp_path):
        """DHARMA: Verdict handler reads from NADI inbox → auto-merges."""
        mock_gh.return_value = "merged"

        ctx = _make_ctx_with_real_nadi(tmp_path)

        # Simulate Steward writing a verdict to the inbox
        verdict_msg = FederationMessage(
            source="steward-protocol",
            target="agent-city",
            operation="pr_review_verdict",
            payload={
                "pr_number": 99,
                "verdict": "approve",
                "reason": "Clean PR. No issues found.",
                "title": "test: PR Gate E2E",
                "touches_core": False,
            },
        )
        inbox_path = ctx.federation_nadi.inbox_path
        inbox_path.write_text(json.dumps([verdict_msg.to_dict()]))

        ops: list[str] = []
        FederationNadiHook().execute(ctx, ops)

        handler = PRVerdictHook()
        # DHARMA phase: verdict handler runs
        handler.execute(ctx, ops)

        # Should have auto-merged (comment + merge)
        assert mock_gh.call_count == 2
        assert "pr_verdict:merged:#99" in ops

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_full_pipeline_scanner_to_verdict(self, mock_fetch, mock_gh, tmp_path):
        """FULL E2E: Scanner → NADI outbox → (simulate transport) → NADI inbox → Verdict → Action.

        This is the money test. Proves the fourth membrane surface works.
        """
        mock_gh.return_value = "merged"

        # ── Step 1: GENESIS — Scanner detects PR ──
        mock_fetch.return_value = [{
            "number": 42,
            "author": {"login": "bob"},
            "title": "fix: typo in README",
            "body": "Fixed a typo.",
            "files": [{"path": "README.md"}],
        }]

        ctx = _make_ctx_with_real_nadi(tmp_path, citizen=True)
        scanner = PRScannerHook()
        genesis_ops: list[str] = []

        scanner.execute(ctx, genesis_ops)
        flush_count = ctx.federation_nadi.flush()

        assert flush_count == 1
        assert len(genesis_ops) == 1

        # ── Step 2: Read what Scanner wrote to outbox ──
        outbox_data = json.loads(ctx.federation_nadi.outbox_path.read_text())
        assert len(outbox_data) == 1
        request = outbox_data[0]
        assert request["operation"] == "pr_review_request"
        assert request["payload"]["pr_number"] == 42
        assert request["payload"]["author"] == "bob"

        # ── Step 3: Simulate Steward processing ──
        # (In production, Steward reads outbox, evaluates, writes verdict to inbox)
        steward_verdict = FederationMessage(
            source="steward-protocol",
            target="agent-city",
            operation="pr_review_verdict",
            payload={
                "pr_number": request["payload"]["pr_number"],
                "verdict": "approve",
                "reason": "Steward review: Clean change, citizen author, no core files.",
                "title": request["payload"]["title"],
                "touches_core": request["payload"]["touches_core"],
            },
        )
        ctx.federation_nadi.inbox_path.write_text(
            json.dumps([steward_verdict.to_dict()])
        )

        # Simulate GENESIS NADI inbox read
        FederationNadiHook().execute(ctx, genesis_ops)

        # ── Step 4: DHARMA — Verdict handler processes ──
        handler = PRVerdictHook()
        dharma_ops: list[str] = []

        handler.execute(ctx, dharma_ops)

        # ── Step 5: Verify end state ──
        # Comment posted + PR merged
        assert mock_gh.call_count == 2

        # Check the comment contains steward's reason
        comment_args = mock_gh.call_args_list[0][0][0]
        assert "comment" in comment_args
        body_idx = comment_args.index("--body")
        assert "Steward Approved" in comment_args[body_idx + 1]
        assert "citizen author" in comment_args[body_idx + 1]

        # Check merge was called
        merge_args = mock_gh.call_args_list[1][0][0]
        assert "merge" in merge_args
        assert "42" in merge_args

        assert "pr_verdict:merged:#42" in dharma_ops

        # Full pipeline proven:
        # Scanner → NADI outbox ✓
        # (Steward processes) simulated ✓
        # NADI inbox → Verdict handler ✓
        # Auto-merge executed ✓

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_full_pipeline_core_file_escalation(self, mock_fetch, mock_gh, tmp_path):
        """FULL E2E with core files: Scanner → NADI → Steward approve → Council escalation."""
        mock_gh.return_value = "ok"

        # ── GENESIS: Scanner detects PR touching core ──
        mock_fetch.return_value = [{
            "number": 77,
            "author": {"login": "eve"},
            "title": "refactor: governance overhaul",
            "body": "Changing civic protocol.",
            "files": [{"path": "city/civic_protocol.py"}, {"path": "city/utils.py"}],
        }]

        ctx = _make_ctx_with_real_nadi(tmp_path, citizen=True)
        scanner = PRScannerHook()
        genesis_ops: list[str] = []

        scanner.execute(ctx, genesis_ops)
        ctx.federation_nadi.flush()

        outbox_data = json.loads(ctx.federation_nadi.outbox_path.read_text())
        request = outbox_data[0]
        assert request["payload"]["touches_core"] is True
        assert "city/civic_protocol.py" in request["payload"]["core_files"]

        # ── Steward approves but notes core files ──
        steward_verdict = FederationMessage(
            source="steward-protocol",
            target="agent-city",
            operation="pr_review_verdict",
            payload={
                "pr_number": 77,
                "verdict": "approve",
                "reason": "Code quality good, but touches civic_protocol — council must decide.",
                "title": "refactor: governance overhaul",
                "touches_core": True,
            },
        )
        ctx.federation_nadi.inbox_path.write_text(
            json.dumps([steward_verdict.to_dict()])
        )

        FederationNadiHook().execute(ctx, genesis_ops)

        # ── DHARMA: Verdict handler escalates to council ──
        handler = PRVerdictHook()
        dharma_ops: list[str] = []

        handler.execute(ctx, dharma_ops)

        # Should NOT have merged — only commented
        assert mock_gh.call_count == 1
        comment_args = mock_gh.call_args_list[0][0][0]
        assert "comment" in comment_args
        body_idx = comment_args.index("--body")
        assert "Council vote required" in comment_args[body_idx + 1]

        assert "pr_verdict:council_vote:#77" in dharma_ops

    @patch("city.hooks.dharma.pr_verdict._gh_run")
    @patch.object(PRScannerHook, "_fetch_open_prs")
    def test_full_pipeline_rejection(self, mock_fetch, mock_gh, tmp_path):
        """FULL E2E rejection: Scanner → NADI → Steward rejects → PR closed."""
        mock_gh.return_value = "ok"

        # ── GENESIS ──
        mock_fetch.return_value = [{
            "number": 13,
            "author": {"login": "spam-bot"},
            "title": "URGENT: free crypto",
            "body": "Buy now!",
            "files": [{"path": "README.md"}],
        }]

        ctx = _make_ctx_with_real_nadi(tmp_path, citizen=False)
        scanner = PRScannerHook()
        genesis_ops: list[str] = []

        scanner.execute(ctx, genesis_ops)
        ctx.federation_nadi.flush()

        # ── Steward rejects ──
        steward_verdict = FederationMessage(
            source="steward-protocol",
            target="agent-city",
            operation="pr_review_verdict",
            payload={
                "pr_number": 13,
                "verdict": "reject",
                "reason": "Spam. Non-citizen. Irrelevant content.",
                "title": "URGENT: free crypto",
                "touches_core": False,
            },
        )
        ctx.federation_nadi.inbox_path.write_text(
            json.dumps([steward_verdict.to_dict()])
        )

        FederationNadiHook().execute(ctx, genesis_ops)

        # ── DHARMA: PR closed ──
        handler = PRVerdictHook()
        dharma_ops: list[str] = []

        handler.execute(ctx, dharma_ops)

        assert mock_gh.call_count == 1
        close_args = mock_gh.call_args_list[0][0][0]
        assert "close" in close_args
        assert "13" in close_args

        assert "pr_verdict:rejected:#13" in dharma_ops
