"""
DAEMON SERVICE — Adaptive Entropy-Driven Heartbeat
====================================================

Manages the Mayor's active lifecycle with entropy-based frequency.

City entropy = dead agent ratio + failing contracts + queue depth + pathogen count.
Higher entropy → faster heartbeat → more responsive healing.

Frequencies:
  SAMADHI:  0.5Hz — health > 0.95 (calm city, slow steady pace)
  SADHANA:  1.0Hz — health > 0.80 (normal processing pace)
  GAJENDRA: 5.0Hz — health < 0.80 (emergency burst + self-diagnostics)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass, field

from city.mayor import Mayor

logger = logging.getLogger("AGENT_CITY.DAEMON")

# Frequency constants (Hz)
SAMADHI = 0.5
SADHANA = 1.0
GAJENDRA = 5.0

# Health thresholds for frequency transitions
HEALTH_HIGH = 0.95  # Above → SAMADHI
HEALTH_MID = 0.80  # Above → SADHANA, below → GAJENDRA


@dataclass
class CityEntropy:
    """Measures city health as a single 0-1 score.

    1.0 = perfect health (no dead agents, all contracts pass, empty queues).
    0.0 = total chaos (everything failing).
    """

    dead_ratio: float = 0.0
    contract_fail_ratio: float = 0.0
    queue_pressure: float = 0.0
    pathogen_count: int = 0

    @property
    def health(self) -> float:
        """City health score (0-1). Higher = healthier."""
        # Each factor contributes 25% max penalty
        penalty = (
            self.dead_ratio * 0.25
            + self.contract_fail_ratio * 0.25
            + min(self.queue_pressure, 1.0) * 0.25
            + min(self.pathogen_count / 10.0, 1.0) * 0.25
        )
        return max(0.0, 1.0 - penalty)

    @property
    def recommended_hz(self) -> float:
        """Recommended heartbeat frequency based on health."""
        h = self.health
        if h > HEALTH_HIGH:
            return SAMADHI
        if h > HEALTH_MID:
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
class DaemonService:
    """Adaptive entropy-driven daemon for the Mayor."""

    mayor: Mayor
    frequency_hz: float = SADHANA
    _running: bool = field(default=False, init=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _total_beats: int = field(default=0, init=False)
    _last_entropy: CityEntropy = field(default_factory=CityEntropy, init=False)
    _consecutive_errors: int = field(default=0, init=False)
    _max_consecutive_errors: int = 5

    def start(self, block: bool = False) -> None:
        """Start the autonomous heartbeat."""
        if self._running:
            return

        self._running = True
        self._install_signal_handlers()
        logger.info("Daemon starting at %.1fHz.", self.frequency_hz)

        if block:
            self._loop()
        else:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the heartbeat gracefully."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
            self._thread = None
        logger.info(
            "Daemon stopped after %d beats (last health=%.2f).",
            self._total_beats,
            self._last_entropy.health,
        )

    def set_frequency(self, hz: float) -> None:
        """Update the heartbeat frequency dynamically."""
        self.frequency_hz = max(0.1, min(hz, GAJENDRA))
        logger.info("Daemon frequency shifted to %.1fHz.", self.frequency_hz)

    @property
    def entropy(self) -> CityEntropy:
        """Last measured city entropy."""
        return self._last_entropy

    def stats(self) -> dict:
        """Daemon runtime stats for MOKSHA reflection."""
        return {
            "running": self._running,
            "frequency_hz": self.frequency_hz,
            "total_beats": self._total_beats,
            "consecutive_errors": self._consecutive_errors,
            "entropy": self._last_entropy.to_dict(),
        }

    def _loop(self) -> None:
        """Internal execution loop with adaptive frequency."""
        while self._running:
            start_t = time.time()

            try:
                self.mayor.run_cycle(1)
                self._total_beats += 1
                self._consecutive_errors = 0

                # Measure entropy and adapt frequency
                self._measure_entropy()
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

                # Self-healing at GAJENDRA frequency
                if self.frequency_hz >= GAJENDRA:
                    self._run_self_diagnostics()

            except Exception as e:
                self._consecutive_errors += 1
                logger.error("Daemon heartbeat exception (%d): %s", self._consecutive_errors, e)
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.error(
                        "Daemon halting: %d consecutive errors",
                        self._consecutive_errors,
                    )
                    self._running = False
                    break

            # Sleep to maintain frequency
            elapsed = time.time() - start_t
            sleep_time = max(0.01, (1.0 / self.frequency_hz) - elapsed)

            # Sub-sleep for rapid shutdown on stop()
            end_t = time.time() + sleep_time
            while time.time() < end_t and self._running:
                time.sleep(0.05)

    def _measure_entropy(self) -> None:
        """Measure city entropy from Mayor state."""
        try:
            stats = self.mayor._pokedex.stats()
            total = stats.get("total", 0)
            alive = stats.get("active", 0) + stats.get("citizen", 0)
            dead_ratio = (total - alive) / total if total > 0 else 0.0

            # Contract failures
            contract_fail = 0.0
            contracts = self.mayor._registry.get("contracts")
            if contracts is not None:
                cs = contracts.stats()
                total_c = cs.get("total", 0)
                failing_c = cs.get("failing", 0)
                contract_fail = failing_c / total_c if total_c > 0 else 0.0

            # Queue pressure (gateway queue depth)
            queue_pressure = len(self.mayor._gateway_queue) / 100.0

            # Pathogen count from immune system
            pathogen_count = 0
            immune = self.mayor._registry.get("immune")
            if immune is not None and hasattr(immune, "stats"):
                immune_stats = immune.stats()
                pathogen_count = immune_stats.get("active_pathogens", 0)

            self._last_entropy = CityEntropy(
                dead_ratio=dead_ratio,
                contract_fail_ratio=contract_fail,
                queue_pressure=queue_pressure,
                pathogen_count=pathogen_count,
            )
        except Exception as e:
            logger.warning("Entropy measurement failed: %s", e)

    def _run_self_diagnostics(self) -> None:
        """Run immune self-diagnostics in GAJENDRA mode."""
        immune = self.mayor._registry.get("immune")
        if immune is not None and hasattr(immune, "run_self_diagnostics"):
            try:
                heals = immune.run_self_diagnostics()
                if heals:
                    logger.info(
                        "Daemon self-diagnostics: %d healing attempts",
                        len(heals),
                    )
            except Exception as e:
                logger.warning("Self-diagnostics failed: %s", e)

    def _install_signal_handlers(self) -> None:
        """Install SIGTERM/SIGINT handlers for graceful shutdown."""
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (ValueError, OSError):
            # Can't install signals from non-main thread
            pass

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals."""
        logger.info("Received signal %d, stopping daemon...", signum)
        self._running = False
