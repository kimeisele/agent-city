"""
NET RETRY — Single-layer error handling for network-facing calls.

Replaces scattered try/except Exception catch-alls with one clean
boundary that distinguishes transient from fatal errors.

    safe_call():  Returns T | None — absorbs transient failures after
                  retry, logs FATAL on non-transient errors, never raises.

This is the ONLY error boundary callers need. No outer try/except.

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

# Exception types that are always transient (by type hierarchy)
_TRANSIENT_TYPES = (
    ConnectionError,     # ConnectionRefusedError, ConnectionResetError, BrokenPipeError
    TimeoutError,        # socket.timeout, etc.
    OSError,             # includes socket.error, DNS failures (gaierror)
)

# Substrings in error messages that indicate transient failure
_TRANSIENT_PATTERNS = (
    "429",
    "503",
    "502",
    "service unavailable",
    "too many requests",
    "rate limit",
    "temporarily",
    "try again",
)


def is_transient(exc: BaseException) -> bool:
    """True if the exception is a transient network failure worth retrying."""
    if isinstance(exc, _TRANSIENT_TYPES):
        return True
    msg = str(exc).lower()
    return any(p in msg for p in _TRANSIENT_PATTERNS)


def safe_call(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 2,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    label: str = "",
    **kwargs: Any,
) -> T | None:
    """Call fn with retry on transient errors. Returns None on any failure.

    This is a COMPLETE error boundary — callers should NOT wrap this
    in try/except. The contract:

    - Transient errors (timeout, connection, 429): retry up to max_retries,
      log WARNING on each retry, log WARNING on exhaustion, return None.
    - Non-transient errors (auth, 404, bad data): log ERROR immediately,
      return None. No retry.
    - Success: return the function's return value.

    Use this instead of scattered try/except Exception catch-alls.
    """
    tag = label or getattr(fn, "__name__", "call")

    for attempt in range(1 + max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not is_transient(exc):
                # Non-transient = broken config, auth, or programming error.
                # Log as ERROR so it's visible in monitoring.
                logger.error(
                    "%s: non-transient error — %s: %s",
                    tag, type(exc).__name__, exc,
                )
                return None

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                jitter = delay * 0.3 * (2 * random.random() - 1)
                sleep_time = max(0.1, delay + jitter)
                logger.warning(
                    "%s: transient error (attempt %d/%d), retrying in %.1fs — %s",
                    tag, attempt + 1, 1 + max_retries, sleep_time, exc,
                )
                time.sleep(sleep_time)
            else:
                logger.warning(
                    "%s: transient error after %d attempts, giving up — %s",
                    tag, 1 + max_retries, exc,
                )
                return None

    return None  # unreachable, satisfies mypy
