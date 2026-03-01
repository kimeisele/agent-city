"""
GH RATE LIMITER — Central Throttle for GitHub CLI Calls
=========================================================

All `gh` subprocess calls go through GhRateLimiter.call().
Sliding time window + exponential backoff on 403/429.

Prevents GAJENDRA mode (5Hz) from burning through GitHub's
secondary rate limit (~80 calls/min).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field

from config import get_config

logger = logging.getLogger("AGENT_CITY.GH_RATE")

_gh_cfg = get_config().get("gh_rate", {})
MAX_PER_MINUTE: int = _gh_cfg.get("max_per_minute", 30)
GAJENDRA_CHECK_INTERVAL: int = _gh_cfg.get("gajendra_check_interval", 10)
WINDOW_SECONDS: float = 60.0


@dataclass
class GhRateLimiter:
    """Sliding-window rate limiter for gh CLI calls.

    Features:
    - Max N calls per 60s window (default 30)
    - Exponential backoff on 403/429 (30s, 60s, 120s)
    - Passthrough in dry_run mode (no subprocess calls)
    """

    max_per_minute: int = MAX_PER_MINUTE
    _call_times: deque[float] = field(default_factory=deque)
    _backoff_until: float = 0.0
    _backoff_step: int = 0  # 0=none, 1=30s, 2=60s, 3=120s
    _total_calls: int = 0
    _throttled_calls: int = 0

    def call(self, args: list[str], timeout: int = 30) -> str | None:
        """Execute a gh CLI command through the rate limiter.

        Returns stdout or None on failure/throttle.
        """
        now = time.monotonic()

        # Check backoff
        if now < self._backoff_until:
            remaining = self._backoff_until - now
            logger.warning("gh rate-limited: backoff %.0fs remaining", remaining)
            self._throttled_calls += 1
            return None

        # Purge expired entries from sliding window
        while self._call_times and self._call_times[0] < now - WINDOW_SECONDS:
            self._call_times.popleft()

        # Check window limit
        if len(self._call_times) >= self.max_per_minute:
            oldest = self._call_times[0]
            wait = WINDOW_SECONDS - (now - oldest)
            logger.warning(
                "gh rate limit reached (%d/%d), wait %.1fs",
                len(self._call_times),
                self.max_per_minute,
                wait,
            )
            self._throttled_calls += 1
            return None

        # Execute
        self._call_times.append(now)
        self._total_calls += 1

        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()

                # Detect rate limit responses
                if "403" in stderr or "429" in stderr or "rate limit" in stderr.lower():
                    self._apply_backoff()
                    logger.warning("gh rate limit hit (403/429): %s", stderr[:100])
                    return None

                logger.warning("gh %s failed: %s", " ".join(args[:3]), stderr[:100])
                return None

            # Success — reset backoff
            self._backoff_step = 0
            return result.stdout.strip()

        except FileNotFoundError:
            logger.warning("gh CLI not found")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh CLI timed out after %ds", timeout)
            return None

    def _apply_backoff(self) -> None:
        """Apply exponential backoff: 30s → 60s → 120s."""
        self._backoff_step = min(self._backoff_step + 1, 3)
        delay = 30 * (2 ** (self._backoff_step - 1))  # 30, 60, 120
        self._backoff_until = time.monotonic() + delay
        logger.warning("gh backoff step %d: waiting %ds", self._backoff_step, delay)

    def should_check_prs(self, heartbeat: int, frequency_hz: float) -> bool:
        """Determine if PR checks should run this heartbeat.

        In GAJENDRA mode (5Hz), skip checks except every N heartbeats.
        In SAMADHI/SADHANA, check every heartbeat.
        """
        if frequency_hz < 2.0:
            return True  # SAMADHI/SADHANA — always check
        # GAJENDRA — throttle to every N heartbeats
        return heartbeat % GAJENDRA_CHECK_INTERVAL == 0

    def stats(self) -> dict:
        """Rate limiter stats for reflection."""
        now = time.monotonic()
        while self._call_times and self._call_times[0] < now - WINDOW_SECONDS:
            self._call_times.popleft()
        return {
            "total_calls": self._total_calls,
            "throttled_calls": self._throttled_calls,
            "calls_in_window": len(self._call_times),
            "max_per_minute": self.max_per_minute,
            "backoff_active": now < self._backoff_until,
            "backoff_step": self._backoff_step,
        }


# Module-level singleton (shared across issues.py and pr_lifecycle.py)
_limiter: GhRateLimiter | None = None


def get_gh_limiter() -> GhRateLimiter:
    """Get the shared GhRateLimiter singleton."""
    global _limiter
    if _limiter is None:
        _limiter = GhRateLimiter()
    return _limiter
