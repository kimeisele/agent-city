"""
DHARMA Hook: Bottleneck Resolution — Receive steward resolution via NADI.

When agent-city escalates a code-fix bottleneck to steward, steward creates a
[BOTTLENECK_ESCALATION] task. Once resolved, steward emits a
`bottleneck_resolution` message back via NADI. This hook receives it and
marks the corresponding brain_bottleneck mission as COMPLETED, unblocking
the scope gate so agent-city stops re-escalating.

Priority 56: after PRVerdictHook (55), before CommunityTriage (60).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.BOTTLENECK_RESOLUTION")


def _federation_messages(ctx: PhaseContext) -> list[dict]:
    """Extract federation-surface messages from the gateway queue."""
    messages = []
    queue = getattr(ctx, "gateway_queue", None)
    if queue is None:
        queue = getattr(ctx, "_gateway_queue", [])
    for item in queue:
        membrane = item.get("membrane", {})
        if membrane.get("surface") == "federation":
            messages.append(item)
    return messages


class BottleneckResolutionHook(BasePhaseHook):
    """Receive bottleneck_resolution from steward and unblock missions."""

    @property
    def name(self) -> str:
        return "bottleneck_resolution"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 56  # After pr_verdict (55), before community_triage (60)

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation_nadi is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        messages = _federation_messages(ctx)
        if not messages:
            return

        resolved = 0
        for msg in messages:
            operation = msg.get("federation_operation", "")
            if operation != "bottleneck_resolution":
                continue

            payload = msg.get("federation_payload", {})
            if not isinstance(payload, dict):
                continue

            dedup_key = payload.get("dedup_key", "")
            if not dedup_key:
                logger.warning(
                    "BOTTLENECK_RESOLUTION: received message with no dedup_key"
                )
                continue

            # Find and complete matching brain_bottleneck missions
            if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
                resolved += self._resolve_missions(ctx, dedup_key, operations)

            source = payload.get("source_agent", "steward")
            logger.info(
                "BOTTLENECK_RESOLUTION: received from %s (dedup_key=%s, resolved=%d)",
                source,
                dedup_key,
                resolved,
            )

        if resolved:
            operations.append(f"bottleneck_resolution:resolved={resolved}")

    def _resolve_missions(
        self,
        ctx: PhaseContext,
        dedup_key: str,
        operations: list[str],
    ) -> int:
        """Mark matching brain_bottleneck missions as COMPLETED.

        Matches by:
        1. Mission name contains the dedup_key's contract/target component
        2. Mission id starts with 'brain_bottleneck_'
        """
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus

        active = ctx.sankalpa.registry.get_active_missions()
        resolved = 0

        # Extract the contract name from the dedup_key
        # dedup_key format: "owner/repo:contract_name:token" or "owner/repo:contract_name"
        contract_part = ""
        parts = dedup_key.split(":")
        if len(parts) >= 2:
            contract_part = parts[1]  # e.g. "ruff_clean"

        for mission in active:
            mid = getattr(mission, "id", "")
            mname = getattr(mission, "name", "")

            # Match: brain_bottleneck missions whose id or name correlates
            if not mid.startswith("brain_bottleneck_"):
                continue

            # Check if the contract part matches the mission name
            # Mission names: "Brain bottleneck: {target[:50]}"
            if contract_part and contract_part.lower() in mname.lower():
                mission.status = MissionStatus.COMPLETED
                resolved += 1
                logger.info(
                    "BOTTLENECK_RESOLUTION: completed mission '%s' (%s)",
                    mname,
                    mid,
                )
                continue

            # Fallback: check if full dedup_key appears in mission description
            mdesc = getattr(mission, "description", "") or ""
            if dedup_key in mdesc:
                mission.status = MissionStatus.COMPLETED
                resolved += 1
                logger.info(
                    "BOTTLENECK_RESOLUTION: completed mission '%s' via description match (%s)",
                    mname,
                    mid,
                )

        return resolved
