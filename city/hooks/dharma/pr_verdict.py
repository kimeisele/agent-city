"""Audit-only containment for legacy federation PR verdict messages.

Legacy ``pr_review_verdict`` messages are retained for observability while the
B1 consumer is not wired.  They cannot mutate GitHub, Council, or mission
state.  Compliance reports remain handled as before.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from config import get_config
from city.phase_hook import DHARMA, BasePhaseHook
from city.registry import SVC_IDENTITY

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.PR_VERDICT")


def _trusted_steward_config() -> tuple[str, str] | None:
    """Return the explicitly pinned legacy Steward identity, if configured."""
    federation = get_config().get("federation", {})
    if not isinstance(federation, dict):
        return None
    trusted = federation.get("trusted_steward")
    if trusted is None:
        identity = os.environ.get("STEWARD_TRUSTED_IDENTITY")
        public_key = os.environ.get("STEWARD_TRUSTED_PUBLIC_KEY")
    else:
        if not isinstance(trusted, dict):
            return None
        # A present configuration object is authoritative.  Do not repair a
        # malformed or incomplete object from ambient environment state.
        identity = trusted.get("identity")
        public_key = trusted.get("public_key")
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(public_key, str)
        or not public_key
    ):
        return None
    return identity, public_key


def _federation_messages(ctx: PhaseContext) -> list[dict]:
    messages = []
    queue = getattr(ctx, "gateway_queue", None)
    if queue is None:
        queue = getattr(ctx, "_gateway_queue", [])
    for item in queue:
        if item.get("membrane", {}).get("surface") == "federation":
            messages.append(item)
    return messages


def _record_compliance_report(ctx: PhaseContext, payload: dict, operations: list[str]) -> None:
    report = {
        "operation": "compliance_report",
        "status": str(payload.get("status", payload.get("compliance", "reported")))[:40],
        "subject": str(
            payload.get("subject", payload.get("target", payload.get("rule", "unknown")))
        )[:120],
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
    operations.append(f"compliance_report:{report['status']}:{report['subject'][:40]}")
    logger.info(
        "COMPLIANCE: %s from %s — %s",
        report["status"],
        report["source"],
        report["subject"],
    )


class PRVerdictHook(BasePhaseHook):
    """Process legacy verdicts without granting them mutation authority."""

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
        return (
            ctx.federation_nadi is not None
            and not ctx.offline_mode
            and bool(_federation_messages(ctx))
        )

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        for msg in _federation_messages(ctx):
            operation = msg.get("federation_operation", "")
            payload = msg.get("federation_payload", {})
            if operation == "compliance_report":
                if isinstance(payload, dict):
                    _record_compliance_report(ctx, payload, operations)
                continue
            if operation != "pr_review_verdict" or not isinstance(payload, dict):
                continue

            pr_number = payload.get("pr_number")
            if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
                logger.warning("PR_VERDICT: missing or malformed pr_number")
                continue
            touches_core = payload.get("touches_core")
            identity = ctx.registry.get(SVC_IDENTITY)
            signature = msg.get("signature")
            supplied_key = msg.get("signer_key")
            signer_identity = msg.get("signer_identity") or payload.get("signer_identity")
            trusted = _trusted_steward_config()
            if (
                trusted is None
                or identity is None
                or not isinstance(signature, str)
                or not isinstance(supplied_key, str)
                or supplied_key != trusted[1]
                or signer_identity != trusted[0]
                or not identity.verify(payload, signature, trusted[1])
            ):
                logger.warning(
                    "PR_VERDICT: pinned Steward trust verification failed for #%s",
                    pr_number,
                )
                operations.append(f"pr_verdict:blocked:#%s" % pr_number)
                continue
            if not isinstance(touches_core, bool):
                logger.warning(
                    "PR_VERDICT: missing or malformed touches_core blocks #%s",
                    pr_number,
                )
                operations.append(f"pr_verdict:blocked:#%s" % pr_number)
                continue

            audit = {
                "type": "legacy_pr_verdict_audit",
                "pr_number": pr_number,
                "verdict": payload.get("verdict"),
                "reason": str(payload.get("reason", ""))[:2000],
                "touches_core": touches_core,
                "signer_identity": trusted[0],
                "mutation": "none",
                "heartbeat": getattr(ctx, "heartbeat_count", 0),
            }
            events = getattr(ctx, "recent_events", None)
            if not isinstance(events, list):
                events = []
                ctx.recent_events = events
            events.append(audit)
            operations.append(f"pr_verdict:audit_only:#{pr_number}")
            logger.info("PR_VERDICT: legacy verdict recorded audit-only for #%s", pr_number)
