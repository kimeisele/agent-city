"""
COMMUNITY TRIAGE — Thread Prioritization and Moderation Decisions
===================================================================

Pure-function triage layer sitting between ThreadStateEngine and KARMA.
Called in DHARMA to plan which threads need attention this cycle.

No hardcoding of thread numbers or categories. All decisions are
data-driven from ThreadState + Pokedex + config.

Triage output is a list of TriageAction dicts consumed by KARMA:
  - respond: post agent response to unresolved thread
  - moderate: add label, close thread, or archive
  - escalate: repetition alert → pain signal
  - cross_post: share content to Moltbook/Twitter

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("AGENT_CITY.COMMUNITY_TRIAGE")


class TriageAction(StrEnum):
    """What to do with a triaged thread."""
    RESPOND = "respond"
    ESCALATE = "escalate"
    LABEL = "label"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class TriageItem:
    """A single triage decision for a thread."""
    action: str
    discussion_number: int
    title: str
    energy: float
    priority: float
    reason: str
    suggested_agent: str = ""
    suggested_label: str = ""


def triage_threads(
    thread_state: object,
    pokedex: object,
    *,
    max_actions: int = 5,
    seed_threads: dict[str, int] | None = None,
    exclude_threads: set[int] | None = None,
) -> list[TriageItem]:
    """Plan community actions for this DHARMA cycle.

    Reads ThreadState for thread energy + status, Pokedex for
    agent domain matching. Returns prioritized list of actions.

    Args:
        thread_state: ThreadStateEngine instance
        pokedex: Pokedex instance (for agent matching)
        max_actions: Max triage items to return (budget)
        seed_threads: Known seed thread numbers to exclude from triage
        exclude_threads: Discussion numbers already queued for Gateway
            (have AgentRuntime+Browser — Triage must not steal them)

    Returns:
        List of TriageItem, sorted by priority (highest first).
    """
    items: list[TriageItem] = []
    seed_numbers = set((seed_threads or {}).values())
    skip_numbers = (exclude_threads or set()) | seed_numbers

    # 1. Repetition alerts → RESPOND with MicroBrain (not ESCALATE forever)
    # Old behavior: escalate = give up. New behavior: try the new cognitive
    # path (MicroBrain + AgentRuntime). If that also fails, THEN escalate.
    alerts = thread_state.repetition_alerts()
    for snap in alerts:
        if snap.discussion_number in skip_numbers:
            continue
        # Give MicroBrain a chance on stuck threads instead of giving up
        items.append(TriageItem(
            action=TriageAction.RESPOND,
            discussion_number=snap.discussion_number,
            title=snap.title,
            energy=snap.energy,
            priority=1.5,  # High but below original 2.0 escalation
            reason=f"Retry with MicroBrain — {snap.human_comment_count} unanswered (was: escalate)",
            suggested_agent="mayor",
        ))

    # 2. Unresolved threads → RESPOND (high priority)
    needing = thread_state.threads_needing_response()
    for snap in needing:
        if snap.discussion_number in skip_numbers:
            continue  # Don't triage threads queued for Gateway or seed threads
        agent = _match_agent_for_thread(snap, pokedex)
        items.append(TriageItem(
            action=TriageAction.RESPOND,
            discussion_number=snap.discussion_number,
            title=snap.title,
            energy=snap.energy,
            priority=snap.energy,  # Higher energy = more urgent
            reason="Unresolved human comment",
            suggested_agent=agent,
        ))

    # 3. Archived threads that had activity → LABEL for posterity
    # (Not implemented yet — would need a "recently archived" query)

    # Sort by priority descending, cap at budget
    items.sort(key=lambda x: -x.priority)
    result = items[:max_actions]

    if result:
        logger.info(
            "TRIAGE: %d actions planned (from %d candidates)",
            len(result), len(items),
        )
        for item in result:
            logger.debug(
                "  → %s #%d (priority=%.2f, agent=%s): %s",
                item.action, item.discussion_number,
                item.priority, item.suggested_agent or "unassigned",
                item.reason,
            )

    return result


def _match_agent_for_thread(
    snap: object,
    pokedex: object,
) -> str:
    """Find the best agent to respond to a thread.

    Simple domain matching based on thread title/category keywords.
    Falls back to mayor if no match.
    """
    title_lower = snap.title.lower()
    category_lower = snap.category.lower()
    combined = f"{title_lower} {category_lower}"

    # Domain keyword → agent domain mapping
    domain_hints = {
        "engineering": ["code", "bug", "fix", "build", "test", "ci", "deploy"],
        "governance": ["proposal", "vote", "council", "rule", "policy", "constitution"],
        "research": ["idea", "research", "explore", "experiment", "discover"],
        "discovery": ["agent", "register", "new", "welcome", "intro"],
    }

    best_domain = ""
    best_score = 0
    for domain, keywords in domain_hints.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score = score
            best_domain = domain

    if best_domain and hasattr(pokedex, "list_by_zone"):
        agents = pokedex.list_by_zone(best_domain)
        # Prefer active citizens
        active = [a for a in agents if a.get("status") == "citizen"]
        if active:
            return active[0].get("name", "mayor")

    return "mayor"
