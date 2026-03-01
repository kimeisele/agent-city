"""
COGNITION LAYER — Knowledge + Events for Agent City.

Wraps steward-protocol's KnowledgeGraph and EventBus as city-level services.
Both are singletons. Graceful fallback if steward-protocol modules unavailable.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging

logger = logging.getLogger("AGENT_CITY.COGNITION")

# ── KnowledgeGraph ─────────────────────────────────────────────────


def get_city_knowledge():
    """Get the KnowledgeGraph singleton for agent-city context.

    Returns UnifiedKnowledgeGraph or None if unavailable.
    Use for: constraint checking, domain context, task enrichment.
    """
    try:
        from vibe_core.knowledge.graph import get_knowledge_graph

        graph = get_knowledge_graph()
        if graph is not None and getattr(graph, "_loaded", False):
            return graph
        return graph
    except Exception as e:
        logger.debug("KnowledgeGraph unavailable: %s", e)
        return None


def compile_context(task: str, depth: int = 1) -> str:
    """Get LLM-ready context for a task from the KnowledgeGraph.

    Returns formatted string or "" if unavailable.
    """
    graph = get_city_knowledge()
    if graph is None:
        return ""
    try:
        return graph.compile_prompt_context(task)
    except Exception as e:
        logger.debug("Context compilation failed: %s", e)
        return ""


def check_constraints(action: str, context: dict) -> list:
    """Check if an action violates any KnowledgeGraph constraints.

    Returns list of violated constraints or [].
    """
    graph = get_city_knowledge()
    if graph is None:
        return []
    try:
        return graph.check_constraints(action, context)
    except Exception:
        return []


# ── EventBus ───────────────────────────────────────────────────────


def get_city_bus():
    """Get the EventBus singleton for agent-city events.

    Returns EventBus or None if unavailable.
    Use for: inter-phase communication, violation tracking, reflection.
    """
    try:
        from vibe_core.mahamantra.substrate.services.event_bus import get_event_bus

        return get_event_bus()
    except Exception as e:
        logger.debug("EventBus unavailable: %s", e)
        return None


def emit_event(event_type: str, agent_id: str, message: str, data: dict | None = None) -> str:
    """Emit a city event to the EventBus.

    Returns event_id or "" if bus unavailable.
    """
    bus = get_city_bus()
    if bus is None:
        return ""
    try:
        from vibe_core.mahamantra.substrate.event_types import EventType

        etype = EventType(event_type) if isinstance(event_type, str) else event_type
        return bus.emit_sync(
            event_type=etype,
            agent_id=agent_id,
            message=message,
            data=data,
        )
    except Exception as e:
        logger.debug("Event emission failed: %s", e)
        return ""


def get_event_history(limit: int = 50, event_type: str | None = None) -> list:
    """Get recent events from the EventBus history.

    Returns list of Event objects or [].
    """
    bus = get_city_bus()
    if bus is None:
        return []
    try:
        return bus.get_history(limit=limit, event_type=event_type)
    except Exception:
        return []


def get_bus_stats() -> dict:
    """Get EventBus statistics."""
    bus = get_city_bus()
    if bus is None:
        return {}
    try:
        return bus.get_stats()
    except Exception:
        return {}
