"""
Mission Creators — Sankalpa mission factories for Mayor phases.

Extracted from Mayor to keep mission creation DRY across phases.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

logger = logging.getLogger("AGENT_CITY.MISSIONS")


def create_healing_mission(ctx: object, contract_result: object) -> None:
    """Create a Sankalpa mission from a failing contract.

    Deduplicates: skips if an active mission for the same contract.name exists.
    """
    if ctx.sankalpa is None:
        return

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    # Dedup: skip if active mission for same contract already exists
    prefix = f"heal_{contract_result.name}_"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.id.startswith(prefix) or (
            existing.name == f"Heal: {contract_result.name}"
            and existing.status == MissionStatus.ACTIVE
        ):
            logger.debug(
                "Healing mission for %s already exists (%s), skipping",
                contract_result.name,
                existing.id,
            )
            return

    mission_id = f"heal_{contract_result.name}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Heal: {contract_result.name}",
        description=f"Quality contract failing: {contract_result.message}",
        priority=MissionPriority.HIGH,
        status=MissionStatus.ACTIVE,
        owner="mayor",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created healing mission %s", mission_id)


def create_audit_mission(ctx: object, finding: object) -> None:
    """Create a Sankalpa mission from a critical audit finding.

    Deduplicates: skips if an active mission for the same finding.source exists.
    """
    if ctx.sankalpa is None:
        return

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    # Dedup: skip if active mission for same finding source already exists
    prefix = f"audit_{finding.source}_"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.id.startswith(prefix) or (
            existing.name == f"Audit: {finding.source}" and existing.status == MissionStatus.ACTIVE
        ):
            logger.debug(
                "Audit mission for %s already exists (%s), skipping", finding.source, existing.id
            )
            return

    mission_id = f"audit_{finding.source}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Audit: {finding.source}",
        description=f"Critical finding: {finding.description}",
        priority=MissionPriority.CRITICAL,
        status=MissionStatus.ACTIVE,
        owner="mayor",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created audit mission %s", mission_id)


def create_improvement_mission(ctx: object, proposal: object) -> None:
    """Create a Sankalpa mission from a reflection improvement proposal.

    Deduplicates: skips if an active mission for the same proposal.id exists.
    """
    if ctx.sankalpa is None:
        return

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    # Dedup: skip if active mission for same proposal already exists
    prefix = f"improve_{proposal.id}_"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.id.startswith(prefix) and existing.status == MissionStatus.ACTIVE:
            logger.debug(
                "Improvement mission for %s already exists (%s), skipping",
                proposal.id,
                existing.id,
            )
            return

    mission_id = f"improve_{proposal.id}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Improve: {proposal.title}",
        description=proposal.description,
        priority=MissionPriority.MEDIUM,
        status=MissionStatus.ACTIVE,
        owner="mayor",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created improvement mission %s", mission_id)


def create_issue_mission(
    ctx: object,
    issue_number: int,
    title: str,
    action_type: str,
) -> str | None:
    """Create a Sankalpa mission from an issue lifecycle action.

    Args:
        ctx: PhaseContext
        issue_number: GitHub Issue number
        title: Issue title (for mission name)
        action_type: "intent_needed" or "audit_needed"

    Returns:
        Mission ID if created, None if sankalpa unavailable.
    """
    if ctx.sankalpa is None:
        return None

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    if action_type == "audit_needed":
        priority = MissionPriority.HIGH
        prefix = "IssueAudit"
    else:
        priority = MissionPriority.MEDIUM
        prefix = "IssueHeal"

    # Dedup: skip if active mission for same issue already exists
    expected_name = f"{prefix}: #{issue_number}"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.name == expected_name and existing.status == MissionStatus.ACTIVE:
            logger.debug(
                "Issue mission for #%d already exists (%s), skipping",
                issue_number,
                existing.id,
            )
            return existing.id

    mission_id = f"issue_{issue_number}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=expected_name,
        description=f"GitHub Issue #{issue_number} ({title}) needs attention: {action_type}",
        priority=priority,
        status=MissionStatus.ACTIVE,
        owner="mayor",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created issue mission %s from #%d (%s)", mission_id, issue_number, action_type)
    return mission_id


def create_a2a_signal_mission(
    ctx: object,
    decoded: object,
    receiver_name: str,
) -> str | None:
    """Create a Sankalpa mission from a high-affinity A2A signal.

    Signals with affinity > 0.8 represent strong semantic alignment —
    the receiver agent should ACT on this, not just acknowledge.
    Deduplicates by correlation_id prefix.
    """
    if ctx.sankalpa is None:
        return None

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    corr = decoded.signal.correlation_id
    prefix = f"a2a_{corr}_"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.id.startswith(prefix) and existing.status == MissionStatus.ACTIVE:
            return existing.id

    concepts = ", ".join(decoded.resonant_concepts[:3]) or "signal response"
    mission_id = f"a2a_{corr}_{receiver_name}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"A2A Signal: {concepts[:50]}",
        description=(
            f"High-affinity signal (score={decoded.affinity:.2f}) from "
            f"{decoded.signal.sender_name}. Domain: {decoded.receiver_domain}. "
            f"Concepts: {concepts}. "
            f"Transitions: {', '.join(decoded.element_transitions[:2])}."
        ),
        priority=MissionPriority.HIGH,
        status=MissionStatus.ACTIVE,
        owner=receiver_name,
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info(
        "Created A2A signal mission %s (affinity=%.2f, from=%s)",
        mission_id,
        decoded.affinity,
        decoded.signal.sender_name,
    )
    return mission_id


def create_signal_mission(
    ctx: object,
    signal_keywords: list[str],
    post_id: str,
    author: str,
    title: str,
    structured: bool = False,
) -> str | None:
    """Create a Sankalpa mission from a submolt code signal.

    Structured [Signal] posts (from steward-protocol) get HIGH priority.
    Normal word-match signals get MEDIUM.
    """
    if ctx.sankalpa is None:
        return None

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    keywords_str = "_".join(signal_keywords[:2]) if signal_keywords else "unknown"
    mission_id = f"signal_{keywords_str}_{post_id[:8]}"
    priority = MissionPriority.HIGH if structured else MissionPriority.MEDIUM

    mission = SankalpaMission(
        id=mission_id,
        name=f"Signal: {keywords_str}",
        description=f"Submolt signal from {author}: {title}",
        priority=priority,
        status=MissionStatus.ACTIVE,
        owner="submolt",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info(
        "Created signal mission %s from %s (post %s, priority=%s)",
        mission_id,
        author,
        post_id[:8],
        priority.name,
    )
    return mission_id


def create_execution_mission(ctx: object, directive: object) -> bool:
    """Create a Sankalpa mission from a federation execute_code directive."""
    if ctx.sankalpa is None:
        return False

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    params = directive.params
    contract = params.get("contract", "ruff_clean")
    mission_id = f"exec_{directive.id}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Execute: {contract}",
        description=f"Federation directive: {contract} ({params.get('source', 'unknown')})",
        priority=MissionPriority.HIGH,
        status=MissionStatus.ACTIVE,
        owner="federation",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created execution mission %s from directive %s", mission_id, directive.id)
    return True


def create_discussion_mission(
    ctx: object,
    discussion_number: int,
    title: str,
    intent: str,
) -> str | None:
    """Create a Sankalpa mission from a GitHub Discussion thread.

    Deduplicates: skips if an active mission for the same discussion exists.
    """
    if ctx.sankalpa is None:
        return None

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    prefix = f"disc_{discussion_number}_"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.id.startswith(prefix) and existing.status == MissionStatus.ACTIVE:
            logger.debug(
                "Discussion mission for #%d already exists (%s), skipping",
                discussion_number,
                existing.id,
            )
            return existing.id

    priority = (
        MissionPriority.HIGH
        if intent in ("propose", "inquiry")
        else MissionPriority.MEDIUM
    )
    mission_id = f"disc_{discussion_number}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Discussion: #{discussion_number}",
        description=f"GitHub Discussion #{discussion_number}: {title}",
        priority=priority,
        status=MissionStatus.ACTIVE,
        owner="mayor",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created discussion mission %s from #%d", mission_id, discussion_number)
    return mission_id


def create_community_mission(
    ctx: object,
    description: str,
    *,
    author: str = "",
    discussion_number: int = 0,
) -> str | None:
    """Create a Sankalpa mission from a human /mission command in Discussions.

    Deduplicates: skips if an active community mission with the same description exists.
    """
    if ctx.sankalpa is None:
        return None

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    # Dedup: check for active community missions with similar descriptions
    short_desc = description[:40].lower()
    for existing in ctx.sankalpa.registry.get_active_missions():
        if (
            existing.id.startswith("community_")
            and existing.status == MissionStatus.ACTIVE
            and short_desc in existing.description.lower()
        ):
            logger.debug(
                "Community mission already exists (%s), skipping",
                existing.id,
            )
            return existing.id

    mission_id = f"community_{ctx.heartbeat_count}_{discussion_number}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Community: {description[:60]}",
        description=f"{description} (requested by @{author} in #{discussion_number})",
        priority=MissionPriority.HIGH,
        status=MissionStatus.ACTIVE,
        owner=author or "community",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info(
        "Created community mission %s from @%s in #%d",
        mission_id, author, discussion_number,
    )
    return mission_id


def create_brain_mission(
    ctx: object,
    verb: str,
    target: str,
    detail: str = "",
    severity: str = "medium",
) -> str | None:
    """Create a Sankalpa mission from a Brain action (bottleneck, health check, escalation).

    These handlers previously emitted reactor pain that nobody consumed.
    Now they create real missions that the system processes.

    Deduplicates: skips if an active brain mission for the same verb+target exists.
    """
    if ctx.sankalpa is None:
        return None

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    target_key = target.replace(" ", "_")[:30]
    prefix = f"brain_{verb}_{target_key}"
    for existing in ctx.sankalpa.registry.get_active_missions():
        if existing.id.startswith(prefix) and existing.status == MissionStatus.ACTIVE:
            logger.debug(
                "Brain mission for %s/%s already exists (%s), skipping",
                verb, target, existing.id,
            )
            return existing.id

    priority_map = {"high": MissionPriority.HIGH, "critical": MissionPriority.CRITICAL}
    priority = priority_map.get(severity, MissionPriority.MEDIUM)
    hb = getattr(ctx, "heartbeat_count", 0)
    mission_id = f"brain_{verb}_{target_key}_{hb}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Brain {verb}: {target[:50]}",
        description=detail or f"Brain detected {verb}: {target}",
        priority=priority,
        status=MissionStatus.ACTIVE,
        owner="mayor",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created brain mission %s", mission_id)
    return mission_id


def create_federation_mission(ctx: object, directive: object) -> bool:
    """Create a Sankalpa mission from a federation directive."""
    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    params = directive.params
    topic = params.get("topic", "unknown")
    priority_str = params.get("priority", "medium").upper()
    priority = getattr(MissionPriority, priority_str, MissionPriority.MEDIUM)
    mission_id = f"fed_{directive.id}_{ctx.heartbeat_count}"
    mission = SankalpaMission(
        id=mission_id,
        name=f"Federation: {topic}",
        description=params.get("context", topic),
        priority=priority,
        status=MissionStatus.ACTIVE,
        owner="federation",
    )
    ctx.sankalpa.registry.add_mission(mission)
    logger.info("Created federation mission %s from %s", mission_id, topic)
    return True
