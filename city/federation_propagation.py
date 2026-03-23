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
        "signal_trigger": "exception_handler_spike",
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
        "required_metrics": ["exception_rate", "error_logs", "message_count"],
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
        "required_metrics": ["stuck_count", "latency_samples", "enqueued_total"],
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
        "required_metrics": ["zone_prana_levels", "zone_count", "trade_volume"],
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

    def __init__(self):
        self._propagation_log: list[DetectedGap] = []
        self._last_propagation: dict[str, float] = {}  # gap_id → timestamp

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
        last_ts = self._last_propagation.get(gap_id, 0)
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
        self._last_propagation[gap_id] = now_ts

        logger.warning(
            "PROPAGATION: Gap detected [%s] via %s | Intensity: %.1f | Propagating...",
            gap_id,
            trigger,
            intensity,
        )

        return gap

    def create_moltbook_help_call(
        self, 
        gap: DetectedGap, 
        system_state: dict | None = None,
    ) -> tuple[str, str]:
        """Generate Moltbook post title + content from detected gap + live metrics.
        
        Dynamically extracts required_metrics from gap_def and interpolates
        actual system_state values into technical context block.
        
        Args:
            gap: Detected gap
            system_state: Dict with metric keys matching gap_def["required_metrics"]
                         Missing keys handled gracefully
        """
        gap_def = DETECTABLE_GAPS[gap.gap_id]
        title = f"🆘 {gap_def['title']}"
        
        # Dynamically extract and format live metrics
        technical_lines = []
        required_metrics = gap_def.get("required_metrics", [])
        
        if system_state and required_metrics:
            for metric_key in required_metrics:
                metric_value = system_state.get(metric_key)
                
                if metric_value is None:
                    continue
                
                # Format metric based on type
                if isinstance(metric_value, float):
                    if "rate" in metric_key or "latency" in metric_key:
                        formatted_value = f"{metric_value:.2f}"
                    else:
                        formatted_value = f"{metric_value:.1f}"
                elif isinstance(metric_value, list):
                    if metric_key == "error_logs":
                        sample_errors = "; ".join(str(e)[:50] for e in metric_value[:3])
                        formatted_value = sample_errors
                    elif metric_key == "latency_samples":
                        avg = sum(metric_value) / len(metric_value) if metric_value else 0
                        max_val = max(metric_value) if metric_value else 0
                        formatted_value = f"avg {avg:.0f}ms, max {max_val:.0f}ms"
                    else:
                        formatted_value = str(metric_value)[:60]
                elif isinstance(metric_value, dict):
                    if metric_key == "zone_prana_levels":
                        zone_items = ", ".join(
                            f"{z}({p})" for z, p in list(metric_value.items())[:5]
                        )
                        formatted_value = f"[{zone_items}]"
                    else:
                        formatted_value = str(metric_value)[:60]
                else:
                    formatted_value = str(metric_value)
                
                # Humanize metric key
                label = metric_key.replace("_", " ").title()
                technical_lines.append(f"**{label}:** {formatted_value}")
        
        # Build technical block
        technical_block = ""
        if technical_lines:
            technical_block = "**Live System State:**\n" + "\n".join(technical_lines) + "\n\n"
        
        content = f"""{gap_def['problem_statement']}

{technical_block}**We're seeking:** Agents/developers skilled in {', '.join(gap_def['required_capabilities'])} to collaborate on solving this.

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
