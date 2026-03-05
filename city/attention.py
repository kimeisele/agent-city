"""
CityAttention — O(1) Intent Router for Agent City.

Issue #17 Stufe 2a: Uses MahaAttention from steward-protocol
for constant-time intent → handler routing.

No LLM. No linear scan. Deterministic hash → Lotus lookup.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from vibe_core.mahamantra.adapters.attention import MahaAttention

logger = logging.getLogger("AGENT_CITY.ATTENTION")

# =============================================================================
# BUILT-IN CITY INTENTS
# =============================================================================
# These are the pain signals that CityReactor can emit.
# Each maps to a handler name (string) that phases can resolve.

_BUILTIN_INTENTS: Dict[str, str] = {
    "metabolize_slow": "upgrade_prana_engine",
    "zone_empty": "spawn_agents",
    "agent_death_spike": "investigate_prana_drain",
    "contract_failing": "create_healing_mission",
    "heartbeat_timeout": "scale_down_cycles",
    "prana_underflow": "emergency_energy_injection",
}

# Schritt 2: Brain-originated intent signals (from BrainAction vocabulary).
# These are typed actions the Brain proposes, routable through CityAttention.
try:
    from city.brain_action import BRAIN_INTENT_SIGNALS as _BRAIN_INTENTS
except ImportError:
    _BRAIN_INTENTS: Dict[str, str] = {}  # type: ignore[no-redef]


# =============================================================================
# CITY ATTENTION
# =============================================================================


class CityAttention:
    """O(1) intent router for Agent City.

    Wraps MahaAttention (steward-protocol) with city-specific intents.
    Phases and CityReactor emit signals; CityAttention routes them
    to handlers in constant time regardless of how many intents exist.
    """

    def __init__(self) -> None:
        self._attention = MahaAttention()
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in city intents (Reactor pain + Brain actions)."""
        for intent, handler in _BUILTIN_INTENTS.items():
            self._attention.memorize(intent, handler)
        for intent, handler in _BRAIN_INTENTS.items():
            self._attention.memorize(intent, handler)
        total = len(_BUILTIN_INTENTS) + len(_BRAIN_INTENTS)
        logger.debug("Registered %d city intents (%d reactor + %d brain)",
                     total, len(_BUILTIN_INTENTS), len(_BRAIN_INTENTS))

    def register(self, intent: str, handler: Any) -> int:
        """Register a custom intent → handler mapping.

        Args:
            intent: Signal string (e.g. "custom_pain")
            handler: Any callable or string handler name

        Returns:
            Address where handler is stored
        """
        address = self._attention.memorize(intent, handler)
        logger.debug("Registered intent '%s' at address %d", intent, address)
        return address

    def route(self, signal: str) -> Optional[Any]:
        """Route a signal to its handler in O(1).

        Args:
            signal: Intent string to resolve

        Returns:
            Handler (callable or string) or None if no match
        """
        result = self._attention.attend(signal)
        if result.found:
            return result.handler
        return None

    def route_batch(self, signals: List[str]) -> List[Optional[Any]]:
        """Route multiple signals at once.

        Args:
            signals: List of intent strings

        Returns:
            List of handlers (None for unmatched signals)
        """
        results = self._attention.attend_batch(signals)
        return [r.handler if r.found else None for r in results]

    def stats(self) -> Dict[str, Any]:
        """Return attention mechanism stats."""
        s = self._attention.stats()
        return {
            "mechanism": s.mechanism,
            "registered": s.registered_intents,
            "queries": s.queries_resolved,
            "hits": s.cache_hits,
            "ops_saved": s.estimated_ops_saved,
        }
