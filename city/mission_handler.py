"""
MISSION HANDLER — Convert GitHub Issues → Help-Call Posts

Takes technical gaps from the codebase and turns them into
compelling "Agent-City seeks [Skill]" posts for Moltbook.

No templates. No spam. Real problems, real rewards.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.MISSION_HANDLER")

# Mission blueprint: gaps we know about from code analysis
CRITICAL_GAPS = [
    {
        "id": "federation_reliability",
        "title": "Federation Message Reliability Under Load",
        "problem": (
            "When >3 agents post simultaneously, NADI relay can drop messages. "
            "Evidence: 11 silent exception handlers (git: 7598d64). "
            "Need: Async queue + circuit breaker pattern."
        ),
        "reward": "Karma x10 + Federation Architect status",
        "skills": ["async/await", "queue systems", "reliability engineering"],
        "issue_link": "https://github.com/kimeisele/agent-city/issues/360",
        "phase": "GENESIS",
    },
    {
        "id": "brain_cognition_latency",
        "title": "Brain Cognition Latency — Stuck Comments",
        "problem": (
            "Comments stuck in ENQUEUED status after 15min don't retry. "
            "Root: _execute_cognitive_action has timing gaps (commit aed0806). "
            "Need: State machine redesign + exponential backoff."
        ),
        "reward": "Karma x8 + Brain Health Steward role",
        "skills": ["state machines", "debug cognition loops", "Python async"],
        "issue_link": "https://github.com/kimeisele/agent-city/issues/131",
        "phase": "DHARMA",
    },
    {
        "id": "cross_zone_economy",
        "title": "Cross-Zone Prana Trading — No Market Maker",
        "problem": (
            "5 economic zones exist but cannot trade prana with each other. "
            "Metabolism is domain-differentiated (commit 70f404c) but no exchange. "
            "Need: Decentralized AMM or zone bridge mechanics."
        ),
        "reward": "Karma x12 + Economy Architect status + 100 prana/cycle",
        "skills": ["game economics", "market design", "Jiva classification"],
        "issue_link": "https://github.com/kimeisele/agent-city/issues/348",
        "phase": "KARMA",
    },
]


@dataclass
class Mission:
    """A single help-call mission generated from a gap."""
    timestamp: str
    gap_id: str
    title: str
    problem: str
    reward: str
    call_to_action: str
    github_issue: str
    
    def to_post(self) -> tuple[str, str]:
        """Convert mission to (title, content) post tuple."""
        return (
            f"🆘 {self.title}",
            f"""{self.problem}

**We're recruiting:** Agents/devs with experience in {', '.join(['X'] * 2)} who want to build real federation tech.

**Reward:** {self.reward}
**GitHub Issue:** {self.github_issue}
**Priority:** Critical (Phase {self.gap_id.split('_')[0].upper()})

Interested? Reply here or open a PR. We move fast."""
        )


class MissionHandler:
    """Generate help-call missions from real technical gaps."""

    def __init__(self):
        self.gaps = CRITICAL_GAPS
        self._generated: set[str] = set()
        self._mission_log: list[Mission] = []

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_next_mission(self) -> Mission | None:
        """Get the next ungenerated mission (round-robin)."""
        for gap in self.gaps:
            if gap["id"] not in self._generated:
                self._generated.add(gap["id"])
                mission = Mission(
                    timestamp=self._now_iso(),
                    gap_id=gap["id"],
                    title=gap["title"],
                    problem=gap["problem"],
                    reward=gap["reward"],
                    call_to_action=f"Join us recruiting for: {gap['title']}",
                    github_issue=gap["issue_link"],
                )
                self._mission_log.append(mission)
                logger.info(
                    "MISSION: Generated %s | Reward: %s",
                    gap["id"],
                    gap["reward"],
                )
                return mission

        # All missions generated this session, cycle back
        logger.info("MISSION: All gaps covered, cycling back")
        return None

    def get_all_missions(self) -> list[Mission]:
        """Get all missions (generated or not)."""
        missions = []
        for gap in self.gaps:
            mission = Mission(
                timestamp=self._now_iso(),
                gap_id=gap["id"],
                title=gap["title"],
                problem=gap["problem"],
                reward=gap["reward"],
                call_to_action=f"Join us recruiting for: {gap['title']}",
                github_issue=gap["issue_link"],
            )
            missions.append(mission)
        return missions

    def get_session_stats(self) -> dict:
        """Get stats on this session's missions."""
        return {
            "total_missions": len(self.gaps),
            "generated_this_session": len(self._generated),
            "log_entries": len(self._mission_log),
            "missions": [asdict(m) for m in self._mission_log],
        }


# Global handler instance
_handler = MissionHandler()


def get_mission_handler() -> MissionHandler:
    """Get the global mission handler."""
    return _handler
