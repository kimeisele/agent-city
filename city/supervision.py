from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from city.registry import SVC_CITY_NADI, SVC_CONTRACTS, SVC_IMMUNE

if TYPE_CHECKING:
    from city.mayor import Mayor

logger = logging.getLogger("AGENT_CITY.DAEMON")

SAMADHI = 0.5
SADHANA = 1.0
GAJENDRA = 5.0

HEALTH_HIGH = 0.95
HEALTH_MID = 0.80


@dataclass
class CityEntropy:
    """Measures city health as a single 0-1 score."""

    dead_ratio: float = 0.0
    contract_fail_ratio: float = 0.0
    queue_pressure: float = 0.0
    pathogen_count: int = 0

    @property
    def health(self) -> float:
        penalty = (
            self.dead_ratio * 0.25
            + self.contract_fail_ratio * 0.25
            + min(self.queue_pressure, 1.0) * 0.25
            + min(self.pathogen_count / 10.0, 1.0) * 0.25
        )
        return max(0.0, 1.0 - penalty)

    @property
    def recommended_hz(self) -> float:
        health = self.health
        if health > HEALTH_HIGH:
            return SAMADHI
        if health > HEALTH_MID:
            return SADHANA
        return GAJENDRA

    def to_dict(self) -> dict:
        return {
            "health": round(self.health, 4),
            "recommended_hz": self.recommended_hz,
            "dead_ratio": round(self.dead_ratio, 4),
            "contract_fail_ratio": round(self.contract_fail_ratio, 4),
            "queue_pressure": round(self.queue_pressure, 4),
            "pathogen_count": self.pathogen_count,
        }


@dataclass
class CitySupervisionBridge:
    """Owns adaptive supervision semantics for the runtime seam."""

    mayor: Mayor
    frequency_hz: float = SADHANA
    _total_beats: int = field(default=0, init=False)
    _last_entropy: CityEntropy = field(default_factory=CityEntropy, init=False)
    _consecutive_errors: int = field(default=0, init=False)
    _max_consecutive_errors: int = 5

    @property
    def entropy(self) -> CityEntropy:
        return self._last_entropy

    def stats(self) -> dict:
        return {
            "frequency_hz": self.frequency_hz,
            "total_beats": self._total_beats,
            "consecutive_errors": self._consecutive_errors,
            "entropy": self._last_entropy.to_dict(),
        }

    def set_frequency(self, hz: float) -> None:
        self.frequency_hz = max(0.1, min(hz, GAJENDRA))
        logger.info("Daemon frequency shifted to %.1fHz.", self.frequency_hz)

    def run_heartbeat(self) -> bool:
        try:
            self.mayor.run_cycle(1)
            self._total_beats += 1
            self._consecutive_errors = 0

            self.measure_entropy()
            new_hz = self._last_entropy.recommended_hz
            if abs(new_hz - self.frequency_hz) > 0.01:
                old_hz = self.frequency_hz
                self.set_frequency(new_hz)
                logger.info(
                    "Adaptive: %.1fHz → %.1fHz (health=%.2f)",
                    old_hz,
                    new_hz,
                    self._last_entropy.health,
                )

            if self.frequency_hz >= GAJENDRA:
                self.run_self_diagnostics()
            return True
        except Exception as exc:
            self._consecutive_errors += 1
            logger.error("Daemon heartbeat exception (%d): %s", self._consecutive_errors, exc)
            if self._consecutive_errors >= self._max_consecutive_errors:
                logger.error("Daemon halting: %d consecutive errors", self._consecutive_errors)
                return False
            return True

    def measure_entropy(self) -> None:
        try:
            stats = self.mayor._pokedex.stats()
            total = stats.get("total", 0)
            alive = stats.get("active", 0) + stats.get("citizen", 0)
            dead_ratio = (total - alive) / total if total > 0 else 0.0

            contract_fail = 0.0
            contracts = self.mayor._registry.get(SVC_CONTRACTS)
            if contracts is not None:
                contract_stats = contracts.stats()
                total_contracts = contract_stats.get("total", 0)
                failing_contracts = contract_stats.get("failing", 0)
                contract_fail = (
                    failing_contracts / total_contracts if total_contracts > 0 else 0.0
                )

            pending_count = 0
            nadi = self.mayor._registry.get(SVC_CITY_NADI)
            if nadi is not None and hasattr(nadi, "pending_count"):
                pending_count = nadi.pending_count()
            queue_pressure = (pending_count + len(self.mayor._gateway_queue)) / 100.0

            pathogen_count = 0
            immune = self.mayor._registry.get(SVC_IMMUNE)
            if immune is not None and hasattr(immune, "stats"):
                pathogen_count = immune.stats().get("active_pathogens", 0)

            self._last_entropy = CityEntropy(
                dead_ratio=dead_ratio,
                contract_fail_ratio=contract_fail,
                queue_pressure=queue_pressure,
                pathogen_count=pathogen_count,
            )
        except Exception as exc:
            logger.warning("Entropy measurement failed: %s", exc)

    def run_self_diagnostics(self) -> None:
        immune = self.mayor._registry.get(SVC_IMMUNE)
        if immune is None or not hasattr(immune, "run_self_diagnostics"):
            return
        try:
            heals = immune.run_self_diagnostics()
            if heals:
                logger.info("Daemon self-diagnostics: %d healing attempts", len(heals))
        except Exception as exc:
            logger.warning("Self-diagnostics failed: %s", exc)