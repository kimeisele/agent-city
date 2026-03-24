"""
MOKSHA Hook: Mission Lifecycle — PR results, terminal missions, rewards, hygiene.

Extracted from moksha.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.MISSIONS")

# Max heartbeats a mission can stay active with owner=mayor before being abandoned.
# Breaks the Awareness Gate deadlock: brain creates mission → no agent executes →
# mission blocks new ones forever. 10 HBs ≈ 2.5 hours at 15-min intervals.
_MISSION_TTL_HEARTBEATS = 10


class PRLifecycleHook(BasePhaseHook):
    """Collect PR results + check CI status, auto-merge, close stale."""

    @property
    def name(self) -> str:
        return "pr_lifecycle"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 30

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # PR results from KARMA issue/exec missions
        pr_results = _collect_pr_results(ctx)
        if pr_results:
            reflection["pr_results"] = pr_results

        # PR Lifecycle: check CI status, auto-merge, close stale
        from city.registry import SVC_PR_LIFECYCLE

        pr_mgr = ctx.registry.get(SVC_PR_LIFECYCLE)
        if pr_mgr is not None:
            pr_changes = pr_mgr.check_all(ctx.heartbeat_count)
            if pr_changes:
                reflection["pr_lifecycle_changes"] = pr_changes
            pr_stats = pr_mgr.stats()
            if pr_stats.get("total_tracked", 0) > 0:
                reflection["pr_lifecycle_stats"] = pr_stats


class MissionResultsHook(BasePhaseHook):
    """Collect terminal missions, mint rewards, purge stale duplicates."""

    @property
    def name(self) -> str:
        return "mission_results"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 35

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # Collect terminal missions (completed/failed)
        terminal_missions = _collect_terminal_missions(ctx)
        if terminal_missions:
            reflection["mission_results_terminal"] = terminal_missions

            # Mint rewards for completed missions
            mint_results = _mint_mission_rewards(ctx, terminal_missions)
            if mint_results:
                reflection["assets_minted"] = mint_results

        # Mission hygiene: purge stale duplicates
        if ctx.sankalpa is not None:
            purged = _purge_stale_missions(ctx)
            if purged > 0:
                reflection["missions_purged"] = purged

        # Close resolved issues
        if ctx.issues is not None and ctx.sankalpa is not None:
            closed_count = _close_resolved_issues(ctx)
            if closed_count > 0:
                reflection["issues_closed"] = closed_count


# ── Helpers ──────────────────────────────────────────────────────────


def _collect_pr_results(ctx: PhaseContext) -> list[dict]:
    """Collect PR creation events from recent_events (set by KARMA)."""
    results: list[dict] = []
    for event in ctx.recent_events:
        if isinstance(event, dict) and event.get("type") == "pr_created":
            results.append(
                {
                    "issue_number": event.get("issue_number", 0),
                    "pr_url": event.get("pr_url", ""),
                    "branch": event.get("branch", ""),
                    "heartbeat": event.get("heartbeat", 0),
                }
            )
    return results


def _collect_terminal_missions(ctx: PhaseContext) -> list[dict]:
    """Collect completed/failed missions for [Mission Result] posts.

    Returns dicts with: id, name, status, owner, pr_url (if any).
    """
    if ctx.sankalpa is None:
        return []

    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus

        all_missions = ctx.sankalpa.registry.list_missions()
    except Exception as e:
        logger.warning("Failed to list missions: %s", e)
        return []

    terminal: list[dict] = []
    for m in all_missions:
        if m.status == MissionStatus.ABANDONED:
            pass # report these as usual
        elif m.status == MissionStatus.COMPLETED:
            # Deterministic Karma: ONLY for missions verified via NADI merge
            if not getattr(m, "metadata", {}).get("nadi_verified"):
                logger.debug("MISSION_LIFECYCLE: Skipping unverified completion for %s", m.id)
                continue
        else:
            continue
        # Only report missions we haven't already reported
        # Convention: owner changes to "reported" after posting
        if getattr(m, "owner", "") == "reported":
            continue
        terminal.append(
            {
                "id": m.id,
                "name": m.name,
                "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                "owner": getattr(m, "owner", "unknown"),
            }
        )
        # Mark as reported to prevent re-posting
        m.owner = "reported"
        ctx.sankalpa.registry.add_mission(m)

    return terminal


def _close_resolved_issues(ctx: PhaseContext) -> int:
    """Close GitHub Issues whose Sankalpa missions completed successfully.

    Only auto-closes EPHEMERAL issues. Returns count of issues closed.
    """
    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
    except Exception as e:
        logger.warning("MissionStatus import failed: %s", e)
        return 0

    try:
        all_missions = ctx.sankalpa.registry.list_missions()
    except Exception as e:
        logger.warning("Failed to list missions for hygiene: %s", e)
        return 0

    closed = 0
    for mission in all_missions:
        if not mission.id.startswith("issue_"):
            continue
        if mission.status != MissionStatus.COMPLETED:
            continue

        # Extract issue number
        parts = mission.id.split("_")
        if len(parts) < 2:
            continue
        try:
            issue_number = int(parts[1])
        except ValueError:
            continue

        # Only auto-close EPHEMERAL issues
        from city.issues import IssueType, _gh_run

        issue_type = ctx.issues.get_issue_type(issue_number)
        if issue_type == IssueType.EPHEMERAL:
            _gh_run(
                [
                    "issue",
                    "close",
                    str(issue_number),
                    "--comment",
                    f"Auto-resolved: Mission {mission.id} completed.",
                ]
            )
            closed += 1
            logger.info("MOKSHA: Closed issue #%d (mission %s completed)", issue_number, mission.id)

        # Mark mission as processed to prevent re-processing
        mission.status = MissionStatus.ABANDONED
        ctx.sankalpa.registry.add_mission(mission)

    return closed


def _purge_stale_missions(ctx: PhaseContext) -> int:
    """Purge duplicate and stale missions.

    Two hygiene passes:
    1. Dedup: same failing contract creating new mission every heartbeat —
       keep only the latest per unique mission name, abandon rest.
    2. TTL: missions stuck on active with owner=mayor for more than
       _MISSION_TTL_HEARTBEATS get abandoned. This breaks the Awareness Gate
       deadlock where brain-created missions block new ones forever because
       no agent executes them.
    """
    try:
        from vibe_core.mahamantra.protocols.sankalpa.types import MissionStatus
    except Exception as e:
        logger.warning("MissionStatus import failed (dedup): %s", e)
        return 0

    try:
        all_missions = ctx.sankalpa.registry.list_missions()
    except Exception as e:
        logger.warning("Failed to list missions for dedup: %s", e)
        return 0

    # Group active missions by name
    by_name: dict[str, list] = {}
    for m in all_missions:
        if m.status != MissionStatus.ACTIVE:
            continue
        by_name.setdefault(m.name, []).append(m)

    purged = 0

    # Pass 1: Dedup — keep only newest per name
    for name, missions in by_name.items():
        if len(missions) <= 1:
            continue

        missions.sort(key=_heartbeat_suffix, reverse=True)
        # Keep first (newest), abandon rest
        for m in missions[1:]:
            m.status = MissionStatus.ABANDONED
            ctx.sankalpa.registry.add_mission(m)
            purged += 1

    # Pass 2: TTL — abandon missions stuck too long without agent execution.
    # Only targets unassigned missions (owner=mayor/dharma) to avoid killing
    # missions that an agent is actively working on.
    current_hb = ctx.heartbeat_count
    for m in all_missions:
        if m.status != MissionStatus.ACTIVE:
            continue
        if getattr(m, "owner", "") not in ("mayor", "dharma"):
            continue
        created_hb = _heartbeat_suffix(m)
        if created_hb <= 0:
            continue
        age = current_hb - created_hb
        if age >= _MISSION_TTL_HEARTBEATS:
            m.status = MissionStatus.ABANDONED
            ctx.sankalpa.registry.add_mission(m)
            purged += 1
            logger.info(
                "MOKSHA: Abandoned stale mission %s (age=%d heartbeats, owner=%s)",
                m.id, age, getattr(m, "owner", "?"),
            )

    if purged:
        logger.info("MOKSHA: Purged %d stale/expired missions", purged)
    return purged


def _heartbeat_suffix(m: object) -> int:
    """Extract the heartbeat number from a mission ID suffix."""
    parts = getattr(m, "id", "").rsplit("_", 1)
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def _mint_mission_rewards(ctx: PhaseContext, terminal_missions: list[dict]) -> list[dict]:
    """Mint semantic assets + prana rewards for terminal missions.

    Each completed mission → MISSION_REWARD_TOKENS (1) capability_token
    + MISSION_COMPLETION_PRANA (27) prana for the mission's owner agent.
    Failed missions → MISSION_FAILED_PRANA (3) participation reward.

    12B: Prana income — without this, the economy is purely deflationary.
    """
    from city.seed_constants import (
        MISSION_COMPLETION_PRANA,
        MISSION_FAILED_PRANA,
        MISSION_REWARD_TOKENS,
    )

    _REWARD_CAP: dict[str, str] = {
        "heal_": "validate",
        "audit_": "audit",
        "improve_": "propose",
        "issue_": "execute",
        "exec_": "execute",
        "signal_": "observe",
        "fed_": "relay",
    }

    minted: list[dict] = []
    try:
        from city.bounty import resolve_bounties_for_missions

        bounty_claims = resolve_bounties_for_missions(ctx, terminal_missions)
        if bounty_claims:
            minted.extend(bounty_claims)
    except Exception as e:
        logger.warning("MOKSHA: Failed to resolve bounties: %s", e)

    for mission in terminal_missions:
        owner = mission.get("owner", "")
        if not owner or owner in ("reported", "unknown"):
            continue

        mission_id = mission["id"]

        # 12B: Prana income for ALL terminal missions (completed or failed)
        if mission["status"] == "completed":
            prana_reward = MISSION_COMPLETION_PRANA
        elif mission["status"] in ("failed", "timeout"):
            prana_reward = MISSION_FAILED_PRANA
        else:
            prana_reward = 0

        if prana_reward > 0:
            try:
                ctx.pokedex.award_prana(
                    owner, prana_reward,
                    source=f"mission:{mission['status']}:{mission_id[:30]}",
                )
            except Exception as e:
                logger.warning("MOKSHA: Prana reward failed for %s: %s", owner, e)

        # Capability tokens only for completed missions
        if mission["status"] != "completed":
            continue

        # Determine reward type from mission prefix
        reward_cap = "propose"  # default
        for prefix, cap in _REWARD_CAP.items():
            if mission_id.startswith(prefix):
                reward_cap = cap
                break

        try:
            ctx.pokedex.grant_asset(
                owner,
                "capability_token",
                reward_cap,
                quantity=MISSION_REWARD_TOKENS,
                source="mission_reward",
            )
            minted.append({
                "agent": owner, "asset": reward_cap,
                "mission": mission_id, "prana": prana_reward,
            })
            logger.info(
                "MOKSHA: Minted %s token + %d prana for %s (mission %s)",
                reward_cap, prana_reward, owner, mission_id,
            )
        except Exception as e:
            logger.warning("MOKSHA: Failed to mint reward for %s: %s", owner, e)

    return minted
