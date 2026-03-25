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

from config import get_config
from city.phase_hook import DHARMA, BasePhaseHook
from city.registry import SVC_IDENTITY, SVC_SANKALPA

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.PR_VERDICT")


def _repo_name() -> str:
    cfg = get_config().get("discussions", {})
    owner = cfg.get("owner", "kimeisele")
    repo = cfg.get("repo", "agent-city")
    return f"{owner}/{repo}"


def _federation_messages(ctx: PhaseContext) -> list[dict]:
    messages = []
    queue = getattr(ctx, "gateway_queue", None)
    if queue is None:
        queue = getattr(ctx, "_gateway_queue", [])
    for item in queue:
        membrane = item.get("membrane", {})
        if membrane.get("surface") == "federation":
            messages.append(item)
    return messages


def _record_compliance_report(ctx: PhaseContext, payload: dict, operations: list[str]) -> None:
    report = {
        "operation": "compliance_report",
        "status": str(payload.get("status", payload.get("compliance", "reported")))[:40],
        "subject": str(payload.get("subject", payload.get("target", payload.get("rule", "unknown"))))[:120],
        "source": str(payload.get("source", payload.get("issuer", "steward")))[:80],
        "heartbeat": getattr(ctx, "heartbeat_count", 0),
        "payload": dict(payload),
    }
    reports = getattr(ctx, "_compliance_reports", None)
    if not isinstance(reports, list):
        reports = []
    reports.append(report)
    ctx._compliance_reports = reports

    events = getattr(ctx, "recent_events", None)
    if not isinstance(events, list):
        events = []
        ctx.recent_events = events
    events.append(report)

    operations.append(
        f"compliance_report:{report['status']}:{report['subject'][:40]}"
    )
    logger.info(
        "COMPLIANCE: %s from %s — %s",
        report["status"],
        report["source"],
        report["subject"],
    )


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
        return ctx.federation_nadi is not None and not ctx.offline_mode and bool(_federation_messages(ctx))

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        messages = _federation_messages(ctx)

        for msg in messages:
            operation = msg.get("federation_operation", "")
            payload = msg.get("federation_payload", {})

            if operation == "compliance_report":
                if isinstance(payload, dict):
                    _record_compliance_report(ctx, payload, operations)
                continue

            if operation != "pr_review_verdict":
                continue

            pr_number = payload.get("pr_number")
            verdict = payload.get("verdict", "")
            reason = payload.get("reason", "No reason provided.")
            title = payload.get("title", f"PR #{pr_number}")
            touches_core = payload.get("touches_core", False)

            if not pr_number:
                logger.warning("PR_VERDICT: Missing pr_number in verdict message")
                continue

            # 0. Zero Trust Signature Verification
            identity = ctx.registry.get(SVC_IDENTITY)
            signature = msg.get("signature")
            public_key = msg.get("signer_key")
            # The payload we sign is the inner federation_payload
            if not all([identity, signature, public_key]) or not identity.verify(payload, signature, public_key):
                logger.warning("PR_VERDICT: Signature verification FAILED for PR #%s. Zero Trust rejection.", pr_number)
                continue

            logger.info(
                "PR_VERDICT: Processing verified verdict=%s for PR #%d (core=%s)",
                verdict, pr_number, touches_core,
            )

            if verdict == "approve":
                self._handle_approve(ctx, pr_number, title, touches_core, reason, operations)
            elif verdict == "request_changes":
                self._handle_request_changes(pr_number, reason, operations)
            elif verdict == "reject":
                self._handle_reject(ctx, pr_number, reason, operations)
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
            repo = _repo_name()
            _gh_run(["pr", "comment", str(pr_number), "--repo", repo, "--body", comment])
            result = _gh_run(["pr", "merge", str(pr_number), "--repo", repo, "--merge"])
            if result is not None:
                operations.append(f"pr_verdict:merged:#{pr_number}")
                logger.info("PR_VERDICT: Auto-merged PR #%d", pr_number)
                
                # Karma Bridge: Update mission state to COMPLETED
                nadi_ref = payload.get("origin_nadi_ref")
                if nadi_ref:
                    self._update_mission_state(ctx, nadi_ref, "completed")
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
            _gh_run(["pr", "comment", str(pr_number), "--repo", _repo_name(), "--body", comment])

            # Create council proposal if council is available
            if ctx.council is not None:
                self._create_council_proposal(ctx, pr_number, title, reason)

            # Internal Signal Emission (Social-Blind)
            self._emit_governance_signal(ctx, {
                "op": "pr_escalation",
                "pr_number": pr_number,
                "title": title,
                "reason": reason,
                "status": "council_vote_required"
            })

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
        _gh_run(["pr", "comment", str(pr_number), "--repo", _repo_name(), "--body", comment])
        operations.append(f"pr_verdict:changes_requested:#{pr_number}")
        logger.info("PR_VERDICT: Changes requested on PR #%d", pr_number)

    def _handle_reject(
        self,
        ctx: PhaseContext,
        pr_number: int,
        reason: str,
        operations: list[str],
    ) -> None:
        """Close the PR with Steward's rejection reason."""
        comment = (
            f"**Steward Review: Rejected**\n\n"
            f"{reason}"
        )
        _gh_run(["pr", "close", str(pr_number), "--repo", _repo_name(), "--comment", comment])
        
        # Internal Signal Emission (Social-Blind)
        self._emit_governance_signal(ctx, {
            "op": "pr_rejection",
            "pr_number": pr_number,
            "reason": reason,
            "status": "closed"
        })

        operations.append(f"pr_verdict:rejected:#{pr_number}")
        logger.info("PR_VERDICT: Rejected and closed PR #%d", pr_number)

    def _emit_governance_signal(self, ctx: PhaseContext, payload: dict) -> None:
        """Emit a generic governance event to the internal recent_events bus."""
        event = {
            "type": "internal_governance_signal",
            "heartbeat": getattr(ctx, "heartbeat_count", 0),
            "payload": payload,
        }
        events = getattr(ctx, "recent_events", None)
        if not isinstance(events, list):
            events = []
            ctx.recent_events = events
        events.append(event)

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
                "repo": _repo_name(),
            },
            timestamp=time.time(),
            heartbeat=ctx.heartbeat_count,
        )
        if proposal:
            logger.info("PR_VERDICT: Council proposal created for PR #%d", pr_number)
        else:
            logger.warning("PR_VERDICT: Council proposal failed for PR #%d", pr_number)

    def _update_mission_state(self, ctx: PhaseContext, nadi_ref: str, status: str) -> None:
        """Update mission state in Sankalpa registry based on NADI_REF."""
        sankalpa = ctx.registry.get(SVC_SANKALPA)
        if not sankalpa:
            return

        try:
            from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
            
            # Find mission by NADI_REF (implicit matching in registry or searching)
            # For now, we search active missions for the matching ref in metadata
            all_missions = sankalpa.registry.list_missions()
            for m in all_missions:
                # We assume missions created via NADI have origin_nadi_ref in their metadata/id
                if nadi_ref in m.id or (hasattr(m, "metadata") and m.metadata.get("nadi_ref") == nadi_ref):
                    m.status = MissionStatus.COMPLETED if status == "completed" else m.status
                    if status == "completed":
                        if not hasattr(m, "metadata") or m.metadata is None:
                            m.metadata = {}
                        m.metadata["nadi_verified"] = True
                    
                    sankalpa.registry.add_mission(m)
                    logger.info("PR_VERDICT: Karma Bridge — Marked mission %s as %s (verified)", m.id, status)
                    break
        except Exception as e:
            logger.warning("PR_VERDICT: Karma Bridge failed updating mission %s: %s", nadi_ref, e)
