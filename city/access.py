"""
AccessClass — Capability-based access levels for Agent City operators.

Adapted from steward-protocol's LifecycleStatus (Vedic Varna System),
simplified for CLI-driven tool operators.

    OBSERVER  → read-only (steward: BRAHMACHARI)
    OPERATOR  → read + write code (steward: GRIHASTHA)
    STEWARD   → read + write + protected files (steward: GRIHASTHA + ADMIN)
    SOVEREIGN → full access, human root (beyond lifecycle)

Not hardcoded to CLI — designed as abstract capability levels
that any access boundary (CLI, API, webhook) can resolve against.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger("AGENT_CITY.ACCESS")


class AccessClass(Enum):
    """Capability-based access levels for operators."""

    OBSERVER = "observer"
    OPERATOR = "operator"
    STEWARD = "steward"
    SOVEREIGN = "sovereign"

    @property
    def level(self) -> int:
        """Numeric level for comparison. Higher = more access."""
        return _LEVELS[self]

    @property
    def can_write(self) -> bool:
        """Can this access class write files?"""
        return self.level >= AccessClass.OPERATOR.level

    @property
    def can_modify_protected(self) -> bool:
        """Can this access class modify protected files (with Council approval)?"""
        return self.level >= AccessClass.STEWARD.level


_LEVELS = {
    AccessClass.OBSERVER: 0,
    AccessClass.OPERATOR: 1,
    AccessClass.STEWARD: 2,
    AccessClass.SOVEREIGN: 3,
}
