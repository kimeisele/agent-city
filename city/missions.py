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
    """Create a Sankalpa mission from a failing contract."""
    if ctx.sankalpa is None:
        return

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

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
    """Create a Sankalpa mission from a critical audit finding."""
    if ctx.sankalpa is None:
        return

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

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
    """Create a Sankalpa mission from a reflection improvement proposal."""
    if ctx.sankalpa is None:
        return

    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

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
