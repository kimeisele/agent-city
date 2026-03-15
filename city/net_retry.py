"""
NET RETRY — Lightweight retry utility for transient network failures.

Simple exponential backoff with jitter for Moltbook SDK calls,
federation transport, and other network-facing operations.

Does NOT retry application-level errors (auth failures, 404s, etc.)
— only transient failures: connection errors, timeouts, 429/503.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger("AGENT_CITY.NET_RETRY")

T = TypeVar("T")

# Transient error indicators (matched against exception message or type name)
_TRANSIENT_PATTERNS = (
    "timeout",
    "timed out",
    "connection",
    "connectionerror",
    "connectionreset",
    "brokenpipe",
    "remotedisconnected",
    "429",
    "503",
    "service unavailable",
    "too many requests",
    "temporary",
    "urlopen",
    "gaierror",
)


def is_transient(exc: BaseException) -> bool:
    """Heuristic: does this exception look like a transient network failure?"""
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    return any(p in exc_str or p in exc_type for p in _TRANSIENT_PATTERNS)


def retry_call(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    label: str = "",
    **kwargs: Any,
) -> T:
    """Call fn(*args, **kwargs) with retry on transient network errors.

    Args:
        fn: Callable to invoke.
        max_retries: Maximum retry attempts (0 = no retries, just call once).
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum backoff delay cap.
        label: Human-readable label for log messages.

    Returns:
        The return value of fn() on success.

    Raises:
        The last exception if all attempts fail, or immediately for
        non-transient errors.
    """
    tag = label or getattr(fn, "__name__", "call")
    last_exc: BaseException | None = None

    for attempt in range(1 + max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc

            # Non-transient → fail immediately (auth errors, 404, etc.)
            if not is_transient(exc):
                raise

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                jitter = delay * 0.3 * (2 * random.random() - 1)
                sleep_time = max(0.1, delay + jitter)
                logger.info(
                    "%s: transient error (attempt %d/%d), retrying in %.1fs: %s",
                    tag, attempt + 1, 1 + max_retries, sleep_time, exc,
                )
                time.sleep(sleep_time)
            else:
                logger.warning(
                    "%s: transient error after %d attempts, giving up: %s",
                    tag, 1 + max_retries, exc,
                )
                raise

    # Unreachable, but makes mypy happy
    raise last_exc  # type: ignore[misc]
