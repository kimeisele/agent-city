"""
FEDERATION PROPAGATION ENGINE
==============================

Autonomous mission discovery → signal emission → Moltbook propagation.

When diagnostics.py detects a gap, this layer converts it into:
1. Internal Sankalpa mission (for own agents to solve)
2. Signal broadcast (for federation peers)
3. Moltbook Help-Call (for community recruitment)

NO human approval. NO pending queues. Pure event-driven propagation.

The three critical gaps are discovered from real system signals:
- Gap 1: Federation NADI reliability (empty exception handlers → dropped messages)
- Gap 2: Brain cognition latency (stuck ENQUEUED comments → memory leak)
- Gap 3: Cross-zone economy (isolated zones → no trading mechanism)

When any gap is detected (via error patterns, metrics, or diagnostics),
this engine autonomously emits a recruitment signal to Moltbook.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from city.signal import SemanticSignal, SignalCoords
from city.mission_router import MISSION_REQUIREMENTS

logger = logging.getLogger("AGENT_CITY.FEDERATION_PROPAGATION")

# Critical gap definitions — tied to real system diagnostics
DETECTABLE_GAPS = {
    "nadi_reliability": {
        "signal_trigger": "exception_handler_spike",  # When exception rates spike
        "mission_type": "fed_nadi_reliability",
        "title": "Federation NADI Message Reliability Under Load",
        "problem_statement": (
            "When >3 agents post simultaneously, NADI relay can drop messages silently. "
            "Root: federation_nadi.py has 11+ exception handlers that don't propagate failures. "
            "Evidence detected: Exception rate spikes during high heartbeat load."
        ),
        "required_capabilities": ["relay", "debug", "async"],
        "reward": "Karma x10 + Federation Architect status",
        "github_issue": 360,
        "moltbook_tags": ["federation", "infrastructure", "reliability"],
    },
    "brain_cognition_latency": {
        "signal_trigger": "enqueued_stuck_comments",
        "mission_type": "brain_cognition_fix",
        "title": "Brain Cognition Latency — Stuck Comment Processing",
        "problem_statement": (
            "Comments stuck in ENQUEUED status after 15 minutes don't retry. "
            "Root: city/cognition.py state machine has gaps. "
            "Impact: Brain can't process complex discussions, memory grows indefinitely."
        ),
        "required_capabilities": ["debug", "statemachine", "async"],
        "reward": "Karma x8 + Brain Health Steward role",
        "github_issue": 131,
        "moltbook_tags": ["brain", "cognition", "reliability"],
    },
    "cross_zone_economy": {
        "signal_trigger": "zone_prana_isolation",
        "mission_type": "zone_economy_bridge",
        "title": "Cross-Zone Prana Trading — No Market Mechanism",
        "problem_statement": (
            "5 economic zones exist with isolated prana pools. "
            "No exchange mechanism: rich zones can't invest in poor zones. "
            "Economy is fragmented, not federated. Need: Decentralized AMM or bridge."
        ),
        "required_capabilities": ["design", "economics", "jiva"],
        "reward": "Karma x12 + Economy Architect status + 100 prana/cycle",
        "github_issue": 348,
        "moltbook_tags": ["economy", "zones", "market-design"],
    },
}


@dataclass
class DetectedGap:
    """A gap detected by diagnostics, ready for propagation."""
    gap_id: str
    timestamp: str
    trigger: str  # What signal triggered detection
    intensity: float  # 0.0-1.0: how critical is this gap
    mission_type: str
    
    def to_signal(self) -> dict:
        """Convert to signal-compatible dict for routing.
        
        Returns a dict that can be fed to signal_router or used directly
        for mission creation. Does NOT require full SemanticSignal structure.
        """
        gap_def = DETECTABLE_GAPS.get(self.gap_id)
        if not gap_def:
            return None
        
        return {
            "signal_id": f"gap_{self.gap_id}_{int(float(self.timestamp[:10].replace('-', '')))}",
            "topic": "federation_gap",
            "severity": "critical" if self.intensity > 0.7 else "warning",
            "tags": gap_def["moltbook_tags"],
            "intent": gap_def["mission_type"],
            "gap_id": self.gap_id,
            "trigger": self.trigger,
            "intensity": self.intensity,
            "problem": gap_def["problem_statement"],
            "reward": gap_def["reward"],
            "github_issue": gap_def["github_issue"],
        }


class FederationPropagationEngine:
    """Autonomous gap detection → mission creation → Moltbook propagation."""

    def __init__(self, pokedex: Optional[object] = None):
        """
        Args:
            pokedex: Optional city.pokedex.Pokedex for persistent throttling.
        """
        self._propagation_log: list[DetectedGap] = []
        self._pokedex = pokedex
        self._last_propagation: dict[str, float] = {}  # In-memory fallback

    def set_pokedex(self, pokedex: object) -> None:
        """Set pokedex after initialization (if factory needs to wire it later)."""
        self._pokedex = pokedex

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def detect_and_propagate(
        self, gap_id: str, trigger: str, intensity: float = 0.8
    ) -> Optional[DetectedGap]:
        """Detect a gap and begin autonomous propagation.
        
        Args:
            gap_id: Key from DETECTABLE_GAPS
            trigger: What detected it (signal name)
            intensity: 0.0-1.0, criticality
            
        Returns:
            DetectedGap if propagation started, None if throttled
        """
        if gap_id not in DETECTABLE_GAPS:
            logger.warning("PROPAGATION: Unknown gap %s", gap_id)
            return None

        # Throttle: max 1 propagation per gap per 6 hours
        now_ts = datetime.now(timezone.utc).timestamp()
        
        # Use persistent throttle if pokedex is available
        last_ts = 0.0
        if self._pokedex and hasattr(self._pokedex, "get_last_propagation_time"):
            last_ts = self._pokedex.get_last_propagation_time(gap_id)
        else:
            last_ts = self._last_propagation.get(gap_id, 0.0)

        if now_ts - last_ts < 21600:  # 6 hours
            logger.debug(
                "PROPAGATION: %s throttled (last %.0f seconds ago)",
                gap_id,
                now_ts - last_ts,
            )
            return None

        gap = DetectedGap(
            gap_id=gap_id,
            timestamp=self._now_iso(),
            trigger=trigger,
            intensity=intensity,
            mission_type=DETECTABLE_GAPS[gap_id]["mission_type"],
        )

        self._propagation_log.append(gap)
        
        # Mark as propagated (persistently if possible)
        if self._pokedex and hasattr(self._pokedex, "mark_propagated"):
            self._pokedex.mark_propagated(gap_id)
        else:
            self._last_propagation[gap_id] = now_ts

        logger.warning(
            "PROPAGATION: Gap detected [%s] via %s | Intensity: %.1f | Propagating...",
            gap_id,
            trigger,
            intensity,
        )

        return gap

    def create_moltbook_help_call(self, gap: DetectedGap) -> tuple[str, str]:
        """Generate Moltbook post title + content from detected gap."""
        gap_def = DETECTABLE_GAPS[gap.gap_id]
        
        title = f"🆘 {gap_def['title']}"
        
        content = f"""{gap_def['problem_statement']}

**We're seeking:** Agents/developers skilled in {', '.join(gap_def['required_capabilities'])} to collaborate on solving this.

**Reward:** {gap_def['reward']}
**Contribute:** Fork github.com/kimeisele/agent-city and tackle issue #{gap_def['github_issue']}
**Federation:** Your solution becomes part of Agent-City governance

Interested? Reply here or open a PR. We move fast and reward builders.

---
*Detected: {gap.trigger} | Intensity: {gap.intensity:.1f} | SOS from Agent-City Federation*"""

        return title, content

    def create_internal_mission(self, gap: DetectedGap) -> dict:
        """Generate internal Sankalpa mission for federation peers."""
        gap_def = DETECTABLE_GAPS[gap.gap_id]
        return {
            "id": f"{gap_def['mission_type']}_{int(datetime.now(timezone.utc).timestamp())}",
            "type": gap_def["mission_type"],
            "name": gap_def["title"],
            "description": gap_def["problem_statement"],
            "required_capabilities": gap_def["required_capabilities"],
            "reward": gap_def["reward"],
            "github_issue": gap_def["github_issue"],
            "detected_via": gap.trigger,
            "intensity": gap.intensity,
        }

    def get_propagation_history(self) -> list[dict]:
        """Get log of all propagated gaps this session."""
        return [asdict(g) for g in self._propagation_log]


# Global instance
_engine = FederationPropagationEngine()


def get_propagation_engine() -> FederationPropagationEngine:
    """Get the global propagation engine."""
    return _engine
