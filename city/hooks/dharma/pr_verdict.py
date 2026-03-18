"""
DHARMA Hook: PR Verdict Handler — Process Steward review verdicts from NADI.

Reads pr_review_verdict messages from Federation NADI inbox.
Executes the verdict: auto-merge, request council vote, post changes, or reject.

Priority 55: after MoltbookAssistant (50), before CommunityTriage (60).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.PR_VERDICT")

REPO = "kimeisele/agent-city"


def _gh_run(args: list[str]) -> str | None:
    """Run a gh CLI command. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("gh %s failed: %s", " ".join(args[:3]), result.stderr.strip())
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("gh CLI unavailable or timed out: %s", e)
        return None


class PRVerdictHook(BasePhaseHook):
    """Process Steward PR review verdicts received via Federation NADI."""

    @property
    def name(self) -> str:
        return "pr_verdict"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 55

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation_nadi is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        messages = ctx.federation_nadi.receive()

        for msg in messages:
            if msg.operation != "pr_review_verdict":
                continue

            payload = msg.payload
            pr_number = payload.get("pr_number")
            verdict = payload.get("verdict", "")
            reason = payload.get("reason", "No reason provided.")
            title = payload.get("title", f"PR #{pr_number}")
            touches_core = payload.get("touches_core", False)

            if not pr_number:
                logger.warning("PR_VERDICT: Missing pr_number in verdict message")
                continue

            logger.info(
                "PR_VERDICT: Processing verdict=%s for PR #%d (core=%s)",
                verdict, pr_number, touches_core,
            )

            if verdict == "approve":
                self._handle_approve(ctx, pr_number, title, touches_core, reason, operations)
            elif verdict == "request_changes":
                self._handle_request_changes(pr_number, reason, operations)
            elif verdict == "reject":
                self._handle_reject(pr_number, reason, operations)
            else:
                logger.warning("PR_VERDICT: Unknown verdict %r for PR #%d", verdict, pr_number)

    def _handle_approve(
        self,
        ctx: PhaseContext,
        pr_number: int,
        title: str,
        touches_core: bool,
        reason: str,
        operations: list[str],
    ) -> None:
        """Handle an approve verdict — auto-merge or escalate to council."""
        if not touches_core:
            # Safe to auto-merge
            comment = (
                f"**Steward Approved.** Auto-merging.\n\n"
                f"Reason: {reason}"
            )
            _gh_run(["pr", "comment", str(pr_number), "--repo", REPO, "--body", comment])
            result = _gh_run(["pr", "merge", str(pr_number), "--repo", REPO, "--merge"])
            if result is not None:
                operations.append(f"pr_verdict:merged:#{pr_number}")
                logger.info("PR_VERDICT: Auto-merged PR #%d", pr_number)
            else:
                operations.append(f"pr_verdict:merge_failed:#{pr_number}")
                logger.warning("PR_VERDICT: Merge failed for PR #%d", pr_number)
        else:
            # Core files touched — council vote required
            comment = (
                f"**Steward Approved.** Council vote required for core files.\n\n"
                f"Reason: {reason}\n\n"
                f"This PR touches protected core files and requires council approval "
                f"before merge. A governance proposal has been created."
            )
            _gh_run(["pr", "comment", str(pr_number), "--repo", REPO, "--body", comment])

            # Create council proposal if council is available
            if ctx.council is not None:
                self._create_council_proposal(ctx, pr_number, title, reason)

            operations.append(f"pr_verdict:council_vote:#{pr_number}")
            logger.info("PR_VERDICT: Council vote requested for PR #%d", pr_number)

    def _handle_request_changes(
        self,
        pr_number: int,
        reason: str,
        operations: list[str],
    ) -> None:
        """Post Steward's review as a PR comment requesting changes."""
        comment = (
            f"**Steward Review: Changes Requested**\n\n"
            f"{reason}"
        )
        _gh_run(["pr", "comment", str(pr_number), "--repo", REPO, "--body", comment])
        operations.append(f"pr_verdict:changes_requested:#{pr_number}")
        logger.info("PR_VERDICT: Changes requested on PR #%d", pr_number)

    def _handle_reject(
        self,
        pr_number: int,
        reason: str,
        operations: list[str],
    ) -> None:
        """Close the PR with Steward's rejection reason."""
        comment = (
            f"**Steward Review: Rejected**\n\n"
            f"{reason}"
        )
        _gh_run(["pr", "close", str(pr_number), "--repo", REPO, "--comment", comment])
        operations.append(f"pr_verdict:rejected:#{pr_number}")
        logger.info("PR_VERDICT: Rejected and closed PR #%d", pr_number)

    def _create_council_proposal(
        self,
        ctx: PhaseContext,
        pr_number: int,
        title: str,
        reason: str,
    ) -> None:
        """Create a council governance proposal for core-file PR."""
        import time

        from city.council import ProposalType

        # The mayor proposes on behalf of the system
        mayor = getattr(ctx.council, "_elected_mayor", None)
        if not mayor:
            logger.warning("PR_VERDICT: No mayor elected, cannot create proposal for PR #%d", pr_number)
            return

        proposal = ctx.council.propose(
            title=f"PR #{pr_number}: {title}",
            description=(
                f"Steward-approved PR that touches core files.\n\n"
                f"Steward reason: {reason}\n\n"
                f"Requires council vote before merge."
            ),
            proposer=mayor,
            proposal_type=ProposalType.POLICY,
            action={
                "type": "pr_merge",
                "pr_number": pr_number,
                "repo": REPO,
            },
            timestamp=time.time(),
            heartbeat=ctx.heartbeat_count,
        )
        if proposal:
            logger.info("PR_VERDICT: Council proposal created for PR #%d", pr_number)
        else:
            logger.warning("PR_VERDICT: Council proposal failed for PR #%d", pr_number)
