"""
PathogenIndex — Pokedex for Code Diseases.

Dynamic registry of known code pathogens (anti-patterns, security
vulnerabilities, performance bottlenecks). Each pathogen maps a
detection pattern to a remedy and severity.

Replaces the old hardcoded _PATTERN_TO_REMEDY dict in CityImmune
with a proper registry that can learn new pathogens at runtime.

Also provides PainRules for the CityReactor nervous system,
bridging the immune system with the city's self-awareness.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from city.reactor import CityIntent, MetricStore, PainRule

logger = logging.getLogger("AGENT_CITY.PATHOGEN_INDEX")


# =============================================================================
# PATHOGEN ENTRY
# =============================================================================


@dataclass
class PathogenEntry:
    """A known code pathogen — like a Pokedex entry for diseases.

    keyword:     Detection pattern (matched case-insensitive in detail strings)
    remedy_id:   ShuddhiEngine rule_id that can heal this pathogen
    severity:    critical, high, medium, low
    description: Human-readable explanation
    """

    keyword: str
    remedy_id: str
    severity: str = "medium"
    description: str = ""


# =============================================================================
# BUILT-IN PATHOGENS (innate immunity)
# =============================================================================

_BUILTIN_PATHOGENS: List[PathogenEntry] = [
    PathogenEntry("any_type", "any_type_usage", "high",
                  "Untyped `Any` usage weakens type safety"),
    PathogenEntry(": any", "any_type_usage", "high",
                  "Explicit `: Any` annotation — use concrete types"),
    PathogenEntry("hardcoded", "hardcoded_constants", "medium",
                  "Hardcoded magic numbers/strings — extract to config"),
    PathogenEntry("magic number", "hardcoded_constants", "medium",
                  "Magic number literal — extract to named constant"),
    PathogenEntry("subprocess", "subprocess_timeout", "high",
                  "subprocess call without timeout — DoS risk"),
    PathogenEntry("f811", "f811_redefinition", "medium",
                  "Redefinition of unused variable (flake8 F811)"),
    PathogenEntry("redefinition", "f811_redefinition", "medium",
                  "Variable redefinition — potential logic error"),
    PathogenEntry("mahajana", "missing_mahajana", "low",
                  "Missing Mahajana docstring header"),
    PathogenEntry("unsafe io", "unsafe_io_write", "high",
                  "Unsafe file I/O without error handling"),
    PathogenEntry("unsafe_io", "unsafe_io_write", "high",
                  "Unsafe file I/O without error handling"),
    PathogenEntry("get_instance", "get_instance", "medium",
                  "Singleton get_instance anti-pattern"),
    PathogenEntry("null signature", "null_signature", "medium",
                  "Function with no type signature"),
    PathogenEntry("null_signature", "null_signature", "medium",
                  "Function with no type annotations"),
]


# =============================================================================
# PATHOGEN INDEX
# =============================================================================


class PathogenIndex:
    """Dynamic registry of known code pathogens.

    Like the Pokedex catalogs citizens, the PathogenIndex catalogs
    diseases. Any subsystem can register new pathogens at runtime.

    Usage:
        idx = PathogenIndex()
        idx.register("pickle_usage", "ban_pickle", severity="critical")
        result = idx.lookup("Found pickle.load in utils.py")
        # → PathogenEntry(keyword="pickle_usage", remedy_id="ban_pickle", ...)
    """

    def __init__(self, *, load_builtins: bool = True) -> None:
        self._entries: Dict[str, PathogenEntry] = {}  # keyword → entry
        self._order: List[str] = []  # insertion order for first-match
        self._lookups: int = 0
        self._hits: int = 0

        if load_builtins:
            for entry in _BUILTIN_PATHOGENS:
                self.register(
                    keyword=entry.keyword,
                    remedy_id=entry.remedy_id,
                    severity=entry.severity,
                    description=entry.description,
                )

    def register(
        self,
        keyword: str,
        remedy_id: str,
        severity: str = "medium",
        description: str = "",
    ) -> None:
        """Register a new pathogen (or overwrite existing).

        Args:
            keyword: Detection pattern (case-insensitive matching).
            remedy_id: ShuddhiEngine rule_id for healing.
            severity: critical, high, medium, low.
            description: Human-readable explanation.
        """
        entry = PathogenEntry(
            keyword=keyword,
            remedy_id=remedy_id,
            severity=severity,
            description=description,
        )
        if keyword not in self._entries:
            self._order.append(keyword)
        self._entries[keyword] = entry
        logger.debug("Registered pathogen: %s → %s (%s)", keyword, remedy_id, severity)

    def lookup(self, detail: str) -> Optional[PathogenEntry]:
        """Find the first matching pathogen for a detail string.

        Args:
            detail: Audit finding or error description.

        Returns:
            First matching PathogenEntry, or None.
        """
        self._lookups += 1
        detail_lower = detail.lower()
        for keyword in self._order:
            if keyword in detail_lower:
                self._hits += 1
                return self._entries[keyword]
        return None

    def lookup_all(self, detail: str) -> List[PathogenEntry]:
        """Find all matching pathogens for a detail string.

        Args:
            detail: Audit finding or error description.

        Returns:
            List of all matching PathogenEntries (may be empty).
        """
        self._lookups += 1
        detail_lower = detail.lower()
        matches = []
        for keyword in self._order:
            if keyword in detail_lower:
                matches.append(self._entries[keyword])
        if matches:
            self._hits += 1
        return matches

    def list_pathogens(self) -> List[PathogenEntry]:
        """List all registered pathogens in registration order."""
        return [self._entries[k] for k in self._order]

    def stats(self) -> Dict[str, Any]:
        """Registry statistics."""
        return {
            "registered": len(self._entries),
            "lookups": self._lookups,
            "hits": self._hits,
            "hit_rate": round(self._hits / self._lookups, 3) if self._lookups > 0 else 0.0,
        }

    # ── CityReactor Bridge ────────────────────────────────────────────

    def connect_reactor(self, reactor: object) -> None:
        """Wire immune PainRules into the CityReactor.

        Registers pain rules that detect immune-relevant metrics:
        - test_failures_spike: too many test failures
        - heal_effectiveness_low: healing success rate dropping
        - security_violation: security scan findings

        Args:
            reactor: CityReactor instance.
        """
        reactor.register_rule(TestFailureRule())
        reactor.register_rule(HealFailureRule())
        reactor.register_rule(SecurityViolationRule())
        logger.info(
            "PathogenIndex: connected 3 immune PainRules to CityReactor"
        )


# =============================================================================
# IMMUNE PAIN RULES (for CityReactor)
# =============================================================================


class TestFailureRule(PainRule):
    """Pain when test failure count exceeds threshold."""

    def __init__(self, threshold: int = 3) -> None:
        self._threshold = threshold

    @property
    def name(self) -> str:
        return "test_failures_spike"

    @property
    def listens_to(self) -> tuple[str, ...]:
        return ("test_failures",)

    def evaluate(self, metric: str, store: MetricStore, **kwargs: Any) -> Optional[CityIntent]:
        count = kwargs.get("count", 0)
        if count >= self._threshold:
            logger.warning("PAIN: %d test failures (threshold: %d)", count, self._threshold)
            return CityIntent(
                signal="test_failures_spike",
                priority="high",
                context={"failures": count, "threshold": self._threshold},
            )
        return None


class HealFailureRule(PainRule):
    """Pain when healing success rate drops below threshold.

    Tracks heal outcomes over a rolling window. If failure rate
    exceeds the threshold after min_attempts, fires pain.
    """

    def __init__(self, min_attempts: int = 3, failure_rate: float = 0.5) -> None:
        self._min_attempts = min_attempts
        self._failure_rate = failure_rate

    @property
    def name(self) -> str:
        return "heal_effectiveness_low"

    @property
    def listens_to(self) -> tuple[str, ...]:
        return ("heal_outcome",)

    def evaluate(self, metric: str, store: MetricStore, **kwargs: Any) -> Optional[CityIntent]:
        outcomes = store.series("heal_outcome_count")
        if len(outcomes) < self._min_attempts:
            return None

        failures = sum(1 for o in outcomes if o == 0)
        rate = failures / len(outcomes)
        if rate >= self._failure_rate:
            logger.warning(
                "PAIN: heal failure rate %.0f%% (%d/%d, threshold: %.0f%%)",
                rate * 100, failures, len(outcomes), self._failure_rate * 100,
            )
            return CityIntent(
                signal="heal_effectiveness_low",
                priority="high",
                context={
                    "failure_rate": round(rate, 3),
                    "failures": failures,
                    "total": len(outcomes),
                    "threshold": self._failure_rate,
                },
            )
        return None


class SecurityViolationRule(PainRule):
    """Pain on any security scan finding — always critical."""

    @property
    def name(self) -> str:
        return "security_violation"

    @property
    def listens_to(self) -> tuple[str, ...]:
        return ("security_violations",)

    def evaluate(self, metric: str, store: MetricStore, **kwargs: Any) -> Optional[CityIntent]:
        count = kwargs.get("count", 0)
        if count > 0:
            logger.warning("PAIN: %d security violations detected", count)
            return CityIntent(
                signal="security_violation",
                priority="critical",
                context={"violations": count},
            )
        return None
