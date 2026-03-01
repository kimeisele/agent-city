"""
CityLearning — Hebbian Cross-Session Memory for Agent City.

Wraps HebbianSynaptic from steward-protocol. Records outcomes
of gateway processing, DM replies, governance actions. Weight
trends inform (but never gate) future KARMA decisions.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.LEARNING")


@dataclass
class CityLearning:
    """Hebbian learning adapter for agent-city.

    Records trigger→action outcomes after each gateway item.
    Flush to disk in MOKSHA phase. Survives restarts.
    """

    _synaptic: object = field(default=None)
    _state_dir: Path = field(default_factory=lambda: Path("data/synapses"))

    def __post_init__(self) -> None:
        if self._synaptic is not None:
            return

        try:
            from vibe_core.mahamantra.substrate.manas.synaptic import (
                HebbianSynaptic,
            )

            self._synaptic = HebbianSynaptic(state_dir=self._state_dir)
            logger.info(
                "CityLearning initialized (%d synapses)",
                self._synaptic.weight_count,
            )
        except Exception as e:
            logger.warning("HebbianSynaptic unavailable: %s", e)
            self._synaptic = None

    @property
    def available(self) -> bool:
        """True if HebbianSynaptic backend is wired."""
        return self._synaptic is not None

    def record_outcome(
        self,
        source: str,
        action: str,
        success: bool,
    ) -> float:
        """Record a trigger→action outcome.

        Args:
            source: Origin of the message (e.g. 'dm', 'feed', 'submolt').
            action: What was done (e.g. 'process', 'dm_reply', 'heal').
            success: Whether the action succeeded.

        Returns:
            Updated weight (0.0-1.0), or 0.5 if backend unavailable.
        """
        if self._synaptic is None:
            return 0.5
        return self._synaptic.update(source, action, success)

    def get_confidence(self, source: str, action: str) -> float:
        """Get current confidence for a trigger→action pair.

        Returns weight (0.0-1.0). Default 0.5 (unknown).
        """
        if self._synaptic is None:
            return 0.5
        return self._synaptic.get_weight(source, action)

    def flush(self) -> None:
        """Persist weights to disk. Call in MOKSHA phase."""
        if self._synaptic is None:
            return
        self._synaptic.flush()

    def decay(self, factor: float = 0.01) -> int:
        """Apply temporal decay to all weights. Call once per MOKSHA.

        Each weight moves toward default (0.5) per cycle.
        Prevents rigidity — old patterns fade naturally.
        Returns number of weights decayed.
        """
        if self._synaptic is None:
            return 0
        return self._synaptic.decay(factor)

    def trim(self, max_entries: int = 500) -> int:
        """Forget weakest synapses when over capacity.

        Returns number of entries removed.
        """
        if self._synaptic is None:
            return 0
        return self._synaptic.trim(max_entries)

    def stats(self) -> dict:
        """Return learning stats for reflection output."""
        if self._synaptic is None:
            return {}

        weights = self._synaptic.snapshot()
        if not weights:
            return {"synapses": 0}

        values = list(weights.values())
        return {
            "synapses": len(values),
            "avg_weight": round(sum(values) / len(values), 3),
            "strongest": max(weights, key=weights.get),
            "weakest": min(weights, key=weights.get),
        }
