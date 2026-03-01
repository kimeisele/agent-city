"""
DAEMON SERVICE — Long-running autonomous heartbeat
==================================================

Manages the Mayor's active lifecycle with entropy-based frequency.

Frequencies:
  SAMADHI: 0.5Hz (slow, steady pace)
  SADHANA: 1.0Hz (normal processing pace)
  GAJENDRA: 5.0Hz (emergency burst mode)
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from city.mayor import Mayor

logger = logging.getLogger("AGENT_CITY.DAEMON")

SAMADHI = 0.5
SADHANA = 1.0
GAJENDRA = 5.0


@dataclass
class DaemonService:
    """Long-running autonomous heartbeat for the Mayor."""

    mayor: Mayor
    frequency_hz: float = SADHANA
    _running: bool = field(default=False, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)

    def start(self, block: bool = False) -> None:
        """Start the autonomous heartbeat."""
        if self._running:
            return

        self._running = True
        logger.info(f"Daemon starting at {self.frequency_hz}Hz.")

        if block:
            self._loop()
        else:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the heartbeat gracefully."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()
            self._thread = None
        logger.info("Daemon stopped.")

    def set_frequency(self, hz: float) -> None:
        """Update the heartbeat frequency dynamically."""
        self.frequency_hz = max(0.1, hz)
        logger.info(f"Daemon frequency shifted to {self.frequency_hz}Hz.")

    def _loop(self) -> None:
        """Internal execution loop."""
        while self._running:
            start_t = time.time()

            try:
                # Advance the city by exactly 1 heartbeat (1 department)
                self.mayor.run_cycle(1)
            except Exception as e:
                logger.error(f"Daemon heartbeat exception: {e}")

            # Sleep to maintain frequency
            elapsed = time.time() - start_t
            sleep_time = max(0.01, (1.0 / self.frequency_hz) - elapsed)

            # Sub-sleep periodically to allow rapid shutdown if stop() is called
            end_t = time.time() + sleep_time
            while time.time() < end_t and self._running:
                time.sleep(0.01)
