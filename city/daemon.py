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
from city.supervision import (
    GAJENDRA,
    SAMADHI,
    SADHANA,
    CityEntropy,
    CitySupervisionBridge,
)

logger = logging.getLogger("AGENT_CITY.DAEMON")

__all__ = ["GAJENDRA", "SAMADHI", "SADHANA", "CityEntropy", "DaemonService"]


@dataclass
class DaemonService:
    """City-facing daemon wrapper over explicit supervision semantics."""

    mayor: Mayor
    frequency_hz: float = SADHANA
    supervision: CitySupervisionBridge | None = None
    _running: bool = field(default=False, init=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.supervision is None:
            self.supervision = CitySupervisionBridge(
                mayor=self.mayor,
                frequency_hz=self.frequency_hz,
            )
        self.frequency_hz = self.supervision.frequency_hz

    @property
    def _total_beats(self) -> int:
        return self.supervision._total_beats

    @property
    def _last_entropy(self) -> CityEntropy:
        return self.supervision.entropy

    @property
    def _consecutive_errors(self) -> int:
        return self.supervision._consecutive_errors

    @property
    def _max_consecutive_errors(self) -> int:
        return self.supervision._max_consecutive_errors

    @_max_consecutive_errors.setter
    def _max_consecutive_errors(self, value: int) -> None:
        self.supervision._max_consecutive_errors = value

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
        self.supervision.set_frequency(hz)
        self.frequency_hz = self.supervision.frequency_hz

    @property
    def entropy(self) -> CityEntropy:
        """Last measured city entropy."""
        return self.supervision.entropy

    def stats(self) -> dict:
        """Daemon runtime stats for MOKSHA reflection."""
        stats = self.supervision.stats()
        stats["running"] = self._running
        return stats

    def _loop(self) -> None:
        """Internal execution loop with adaptive frequency."""
        while self._running:
            start_t = time.time()

            if not self.supervision.run_heartbeat():
                self._running = False
                break
            self.frequency_hz = self.supervision.frequency_hz

            elapsed = time.time() - start_t
            sleep_time = max(0.01, (1.0 / self.frequency_hz) - elapsed)

            end_t = time.time() + sleep_time
            while time.time() < end_t and self._running:
                time.sleep(0.05)

    def _measure_entropy(self) -> None:
        """Measure city entropy from Mayor state."""
        self.supervision.measure_entropy()

    def _run_self_diagnostics(self) -> None:
        """Run immune self-diagnostics in GAJENDRA mode."""
        self.supervision.run_self_diagnostics()

    def _install_signal_handlers(self) -> None:
        """Install SIGTERM/SIGINT handlers for graceful shutdown."""
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (ValueError, OSError):
            pass

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals."""
        logger.info("Received signal %d, stopping daemon...", signum)
        self._running = False
