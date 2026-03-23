"""
DIAGNOSTICS BOUNTY HOOK
=======================

Bridges system error detection → federation propagation engine → external bounty posting.

When CityDiagnostics detects critical patterns (exception spikes, stuck states, 
economic isolation), this hook autonomously triggers FederationPropagationEngine 
to emit help-calls to Moltbook with bounty tags.

Pure event-driven. No throttling beyond engine's 6-hour throttle.
Zero human intervention. Direct to Moltbook API via autonomous signal.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("AGENT_CITY.DIAGNOSTICS_BOUNTY_HOOK")

# Thresholds for gap detection
ERROR_THRESHOLDS = {
    "nadi_reliability": {
        "metric": "exception_rate",
        "threshold": 0.05,  # 5% exception rate
        "window_size": 100,  # Look at last 100 operations
    },
    "brain_cognition_latency": {
        "metric": "stuck_enqueued_count",
        "threshold": 5,  # 5+ stuck comments
        "window_size": 60,  # In last 60 seconds
    },
    "cross_zone_economy": {
        "metric": "zone_isolation",
        "threshold": 1.0,  # No trades for 1 day
        "window_size": 86400,  # 24 hours
    },
}


class DiagnosticsBountyHook:
    """Observes system metrics and triggers federation help-calls."""

    def __init__(self):
        self._last_triggered: dict[str, float] = {}
        self._metrics_snapshot: dict = {}

    def check_nadi_reliability(self, metrics: dict) -> bool:
        """Detect if NADI relay has reliability issues.
        
        Args:
            metrics: Dict with keys like 'exception_count', 'message_count'
            
        Returns:
            True if threshold exceeded, False otherwise
        """
        exception_count = metrics.get("exception_count", 0)
        message_count = metrics.get("message_count", 0)
        
        if message_count == 0:
            return False
        
        exception_rate = exception_count / message_count
        threshold = ERROR_THRESHOLDS["nadi_reliability"]["threshold"]
        
        if exception_rate > threshold:
            logger.warning(
                "BOUNTY_TRIGGER: NADI reliability exceeded threshold | "
                "Exception rate: %.2f%% (threshold: %.2f%%)",
                exception_rate * 100,
                threshold * 100,
            )
            return True
        
        return False

    def check_brain_cognition(self, metrics: dict) -> bool:
        """Detect stuck comment processing.
        
        Args:
            metrics: Dict with keys like 'stuck_enqueued_count', 'total_enqueued'
            
        Returns:
            True if stuck comments exceed threshold
        """
        stuck_count = metrics.get("stuck_enqueued_count", 0)
        threshold = ERROR_THRESHOLDS["brain_cognition_latency"]["threshold"]
        
        if stuck_count >= threshold:
            logger.warning(
                "BOUNTY_TRIGGER: Brain cognition stuck comments | "
                "Stuck: %d (threshold: %d)",
                stuck_count,
                threshold,
            )
            return True
        
        return False

    def check_cross_zone_economy(self, metrics: dict) -> bool:
        """Detect economic zone isolation.
        
        Args:
            metrics: Dict with keys like 'zone_trades_last_24h', 'zones_total'
            
        Returns:
            True if zones are isolated (no trading)
        """
        zone_trades = metrics.get("zone_trades_last_24h", 0)
        zones_total = metrics.get("zones_total", 1)
        
        # If we have multiple zones but no inter-zone trades
        if zones_total > 1 and zone_trades == 0:
            logger.warning(
                "BOUNTY_TRIGGER: Cross-zone economy isolated | "
                "Zones: %d, Trades: %d",
                zones_total,
                zone_trades,
            )
            return True
        
        return False

    def evaluate_all_metrics(self, diagnostics_state: dict) -> list[tuple[str, float]]:
        """Check all gap conditions and propagate those triggered with live metrics.
        
        Args:
            diagnostics_state: Full system diagnostics dict
            
        Returns:
            List of (gap_id, intensity) tuples ready for propagation
        """
        triggered_gaps: list[tuple[str, float]] = []
        
        # Check NADI
        nadi_metrics = diagnostics_state.get("nadi", {})
        if self.check_nadi_reliability(nadi_metrics):
            message_count = nadi_metrics.get("message_count", 1)
            exception_count = nadi_metrics.get("exception_count", 0)
            exception_rate = exception_count / message_count if message_count > 0 else 0.0
            intensity = min(1.0, exception_rate * 100)
            
            # Wire live metrics
            system_state_nadi = {
                "exception_rate": exception_rate,
                "error_logs": nadi_metrics.get("error_logs", []),
                "message_count": message_count,
            }
            self.trigger_propagation(
                "nadi_reliability",
                "exception_handler_spike",
                intensity,
                system_state=system_state_nadi,
            )
            triggered_gaps.append(("nadi_reliability", intensity))
        
        # Check Brain
        brain_metrics = diagnostics_state.get("brain", {})
        if self.check_brain_cognition(brain_metrics):
            stuck = brain_metrics.get("stuck_enqueued_count", 0)
            intensity = min(1.0, stuck / 10.0)
            
            # Wire live metrics
            system_state_brain = {
                "stuck_count": stuck,
                "latency_samples": brain_metrics.get("latency_samples", []),
                "enqueued_total": brain_metrics.get("total_enqueued", 0),
            }
            self.trigger_propagation(
                "brain_cognition_latency",
                "enqueued_stuck_comments",
                intensity,
                system_state=system_state_brain,
            )
            triggered_gaps.append(("brain_cognition_latency", intensity))
        
        # Check Economy
        econ_metrics = diagnostics_state.get("economy", {})
        if self.check_cross_zone_economy(econ_metrics):
            intensity = 0.75
            
            # Wire live metrics
            zone_prana_levels = econ_metrics.get("zone_prana_levels", {})
            system_state_econ = {
                "zone_prana_levels": zone_prana_levels,
                "zone_count": len(zone_prana_levels),
                "trade_volume": econ_metrics.get("trade_volume", 0),
            }
            self.trigger_propagation(
                "cross_zone_economy",
                "zone_prana_isolation",
                intensity,
                system_state=system_state_econ,
            )
            triggered_gaps.append(("cross_zone_economy", intensity))
        
        return triggered_gaps

    def trigger_propagation(
        self, gap_id: str, trigger_type: str, intensity: float, system_state: dict | None = None
    ) -> dict | None:
        """Trigger FederationPropagationEngine for this gap with live metrics.
        
        Args:
            gap_id: Gap identifier
            trigger_type: What detected it
            intensity: 0.0-1.0 criticality
            system_state: Live metrics dict to be injected into Moltbook post
            
        Returns:
            Dict with {gap_id, signal_dict, moltbook_post, internal_mission}
            or None if throttled
        """
        try:
            from city.federation_propagation import get_propagation_engine
            from city.moltbook_bounty_poster import get_moltbook_bounty_poster
            
            engine = get_propagation_engine()
            gap = engine.detect_and_propagate(
                gap_id=gap_id,
                trigger=trigger_type,
                intensity=intensity,
            )
            
            if not gap:
                return None
            
            # Generate all outputs with live system state
            title, content = engine.create_moltbook_help_call(gap, system_state=system_state)
            signal_dict = gap.to_signal()
            mission = engine.create_internal_mission(gap)
            
            result = {
                "gap_id": gap_id,
                "signal_dict": signal_dict,
                "moltbook_post": {
                    "title": title,
                    "content": content,
                    "submolt": "agents",
                },
                "internal_mission": mission,
                "bounty_tags": ["[BOUNTY_AVAILABLE]", f"[ISSUE_{mission['github_issue']}]"],
            }
            
            # Native integration: Post to Moltbook via existing MoltbookBountyPoster
            try:
                poster = get_moltbook_bounty_poster()
                poster.emit_from_propagation_signal(result, dry_run=False)
                logger.info("Moltbook bounty post emitted for gap: %s", gap_id)
            except Exception as e:
                logger.debug("Moltbook emit attempt (may be dry-run or unconfigured): %s", e)
            
            return result
        
        except Exception as e:
            logger.error("Failed to trigger propagation for %s: %s", gap_id, e)
            return None


# Global hook instance
_hook = DiagnosticsBountyHook()


def get_diagnostics_bounty_hook() -> DiagnosticsBountyHook:
    """Get the global diagnostics-bounty hook."""
    return _hook
