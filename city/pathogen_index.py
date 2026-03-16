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

import ast
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from city.reactor import CityIntent, MetricStore, PainRule

logger = logging.getLogger("AGENT_CITY.PATHOGEN_INDEX")


# =============================================================================
# PATHOGEN ENTRY
# =============================================================================


@dataclass
class Antidote:
    """The cure for a pathogen.

    test_id:   The test that verifies this pathogen is gone (e.g. 'tests/test_foo.py::test_bar')
    remedy_id: ShuddhiEngine rule_id for automated CST fix
    strategy:  How to apply — 'test_first' (TDD), 'auto_fix', 'escalate'
    """

    test_id: str = ""
    remedy_id: str = ""
    strategy: str = "escalate"  # test_first | auto_fix | escalate


@dataclass
class PathogenEntry:
    """A known code pathogen — like a Pokedex entry for diseases.

    keyword:        Detection pattern (matched case-insensitive in detail strings)
    remedy_id:      ShuddhiEngine rule_id (backward compat, also in antidote)
    severity:       critical, high, medium, low
    description:    Human-readable explanation
    antidote:       The cure — test + remedy + strategy
    auto_discovered: True if the immune system found this itself
    first_seen:     Unix timestamp of first encounter
    last_seen:      Unix timestamp of most recent encounter
    encounter_count: How many times this pathogen was seen
    """

    keyword: str
    remedy_id: str
    severity: str = "medium"
    description: str = ""
    antidote: Antidote = field(default_factory=Antidote)
    auto_discovered: bool = False
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    encounter_count: int = 1


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
        antidote: Antidote | None = None,
        auto_discovered: bool = False,
    ) -> PathogenEntry:
        """Register a new pathogen (or update encounter on existing).

        Args:
            keyword: Detection pattern (case-insensitive matching).
            remedy_id: ShuddhiEngine rule_id for healing.
            severity: critical, high, medium, low.
            description: Human-readable explanation.
            antidote: The cure — test_id + remedy_id + strategy.
            auto_discovered: True if found by the immune system itself.

        Returns:
            The registered (or updated) PathogenEntry.
        """
        now = time.time()
        if antidote is None:
            antidote = Antidote(remedy_id=remedy_id)

        if keyword in self._entries:
            # Update existing — bump encounter, keep first_seen
            existing = self._entries[keyword]
            existing.last_seen = now
            existing.encounter_count += 1
            if antidote.remedy_id:
                existing.antidote = antidote
                existing.remedy_id = antidote.remedy_id
            logger.debug(
                "Pathogen re-encountered: %s (count=%d)",
                keyword, existing.encounter_count,
            )
            return existing

        entry = PathogenEntry(
            keyword=keyword,
            remedy_id=remedy_id,
            severity=severity,
            description=description,
            antidote=antidote,
            auto_discovered=auto_discovered,
            first_seen=now,
            last_seen=now,
            encounter_count=1,
        )
        self._order.append(keyword)
        self._entries[keyword] = entry
        logger.debug("Registered pathogen: %s → %s (%s)", keyword, remedy_id, severity)
        return entry

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
        auto_count = sum(1 for e in self._entries.values() if e.auto_discovered)
        return {
            "registered": len(self._entries),
            "innate": len(self._entries) - auto_count,
            "learned": auto_count,
            "lookups": self._lookups,
            "hits": self._hits,
            "hit_rate": round(self._hits / self._lookups, 3) if self._lookups > 0 else 0.0,
        }

    # ── Adaptive Immune Loop ──────────────────────────────────────────

    def ingest_diagnostics(self, report: Dict[str, Any]) -> List[PathogenEntry]:
        """Auto-discover pathogens from pytest JSON report.

        For each test failure:
        1. Try lookup() — if known, bump encounter_count
        2. If unknown — auto-register as new pathogen
           The failed test IS the antidote (test_id)

        Args:
            report: pytest-json-report dict with 'tests' key.

        Returns:
            List of new or updated PathogenEntries.
        """
        discovered: List[PathogenEntry] = []

        for test in report.get("tests", []):
            if test.get("outcome") != "failed":
                continue

            test_id = test.get("nodeid", "")
            crash = test.get("call", {}).get("crash", {})
            path = crash.get("path", "")
            message = crash.get("message", "")

            if not test_id:
                continue

            # Build a detail string for lookup
            detail = f"{test_id}: {message}" if message else test_id

            # Known pathogen? Bump encounter.
            existing = self.lookup(detail)
            if existing is not None:
                existing.last_seen = time.time()
                existing.encounter_count += 1
                discovered.append(existing)
                continue

            # Unknown pathogen — auto-discover!
            # Extract a keyword from the test node ID
            keyword = _extract_keyword(test_id, message)

            entry = self.register(
                keyword=keyword,
                remedy_id="",  # no auto-fix yet — needs learning
                severity="high",
                description=f"Auto-discovered from test failure: {message[:200]}",
                antidote=Antidote(
                    test_id=test_id,
                    remedy_id="",
                    strategy="test_first",  # the test IS the cure
                ),
                auto_discovered=True,
            )
            discovered.append(entry)
            logger.info(
                "Immune: auto-discovered pathogen '%s' (antidote: %s)",
                keyword, test_id,
            )

        if discovered:
            logger.info(
                "Immune: ingested %d pathogens (%d new) from diagnostics",
                len(discovered),
                sum(1 for d in discovered if d.encounter_count == 1),
            )
        return discovered

    def scan_source(self, source_code: str, file_path: str = "<unknown>") -> List[PathogenEntry]:
        """AST-based security scan — Narasimha pattern from the Blueprint.

        Scans Python source code for security anti-patterns:
        - pickle/dill/cPickle imports (RCE risk)
        - subprocess without timeout (DoS risk)
        - eval/exec usage (code injection)
        - xml.etree without defusedxml (XXE risk)

        Each finding is auto-registered as a pathogen.

        Args:
            source_code: Python source code string.
            file_path: Path for reporting.

        Returns:
            List of discovered PathogenEntries.
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        visitor = _NarasimhaVisitor(file_path)
        visitor.visit(tree)

        discovered: List[PathogenEntry] = []
        for finding in visitor.findings:
            keyword = finding["keyword"]
            entry = self.register(
                keyword=keyword,
                remedy_id=finding["remedy_id"],
                severity=finding["severity"],
                description=finding["description"],
                antidote=Antidote(
                    remedy_id=finding["remedy_id"],
                    strategy="auto_fix" if finding["remedy_id"] else "escalate",
                ),
                auto_discovered=True,
            )
            discovered.append(entry)

        return discovered

    # ── CityReactor Bridge ────────────────────────────────────────────

    def get_antidote(self, detail: str) -> Optional[Antidote]:
        """Find the antidote for a pathogen matching the detail string.

        Returns:
            The Antidote if a matching pathogen exists, else None.
        """
        entry = self.lookup(detail)
        if entry is not None:
            return entry.antidote
        return None

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


# =============================================================================
# NARASIMHA — AST Security Visitor (from the Blueprint)
# =============================================================================

# Banned imports → (code, severity, remedy_id, description)
_BANNED_IMPORTS: Dict[str, tuple] = {
    "pickle": ("SEC001", "critical", "ban_pickle",
               "Pickle allows RCE via __reduce__. Use JSON."),
    "cPickle": ("SEC001", "critical", "ban_pickle",
                "cPickle allows RCE. Use JSON."),
    "dill": ("SEC001", "critical", "ban_pickle",
             "Dill allows RCE. Use JSON."),
    "shelve": ("SEC001", "critical", "ban_pickle",
               "Shelve uses pickle internally. Use JSON."),
    "xml.etree.ElementTree": ("SEC002", "high", "ban_xml_stdlib",
                               "XML parser vulnerable to XXE. Use defusedxml."),
    "xml.sax": ("SEC002", "high", "ban_xml_stdlib",
                "XML parser vulnerable to XXE. Use defusedxml."),
    "xml.dom.minidom": ("SEC002", "high", "ban_xml_stdlib",
                        "XML parser vulnerable to XXE. Use defusedxml."),
    "telnetlib": ("SEC003", "medium", "",
                  "Telnet is insecure. Use SSH."),
}

# Subprocess functions that need timeout
_SUBPROCESS_FUNCS = {"call", "run", "check_output", "check_call", "Popen"}


class _NarasimhaVisitor(ast.NodeVisitor):
    """AST-based security scanner — Narasimha pattern.

    Detects:
    - Banned imports (pickle, xml.etree, etc.)
    - subprocess without timeout
    - eval/exec usage
    """

    def __init__(self, file_path: str = "<unknown>") -> None:
        self.file_path = file_path
        self.findings: List[Dict[str, str]] = []
        self._aliases: Dict[str, str] = {}  # alias → real module name

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            asname = alias.asname or alias.name
            self._aliases[asname] = name

            if name in _BANNED_IMPORTS:
                code, severity, remedy_id, desc = _BANNED_IMPORTS[name]
                self.findings.append({
                    "keyword": f"{code.lower()}:{name}:{self.file_path}:{node.lineno}",
                    "severity": severity,
                    "remedy_id": remedy_id,
                    "description": f"[{code}] L{node.lineno} {self.file_path}: {desc}",
                })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module in _BANNED_IMPORTS:
            code, severity, remedy_id, desc = _BANNED_IMPORTS[module]
            self.findings.append({
                "keyword": f"{code.lower()}:{module}:{self.file_path}:{node.lineno}",
                "severity": severity,
                "remedy_id": remedy_id,
                "description": f"[{code}] L{node.lineno} {self.file_path}: {desc}",
            })
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = _resolve_call_name(node.func)

        # subprocess without timeout
        if func_name and "subprocess" in func_name:
            method = func_name.split(".")[-1]
            if method in _SUBPROCESS_FUNCS:
                has_timeout = any(
                    getattr(k, "arg", None) == "timeout" for k in node.keywords
                )
                if not has_timeout:
                    self.findings.append({
                        "keyword": f"sec004:subprocess_no_timeout:{self.file_path}:{node.lineno}",
                        "severity": "high",
                        "remedy_id": "subprocess_timeout",
                        "description": (
                            f"[SEC004] L{node.lineno} {self.file_path}: "
                            f"DoS risk — {func_name}() without timeout"
                        ),
                    })

        # eval/exec
        if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            self.findings.append({
                "keyword": f"sec005:{node.func.id}:{self.file_path}:{node.lineno}",
                "severity": "critical",
                "remedy_id": "",
                "description": (
                    f"[SEC005] L{node.lineno} {self.file_path}: "
                    f"Code injection risk — {node.func.id}()"
                ),
            })

        self.generic_visit(node)


def _resolve_call_name(func_node: ast.expr) -> str | None:
    """Flatten AST Attribute nodes into dotted names (e.g. os.path.join)."""
    if isinstance(func_node, ast.Name):
        return func_node.id
    elif isinstance(func_node, ast.Attribute):
        value = _resolve_call_name(func_node.value)
        if value:
            return f"{value}.{func_node.attr}"
    return None


def _extract_keyword(test_id: str, message: str) -> str:
    """Extract a unique keyword from a test failure for pathogen registration.

    Uses test_id as the primary keyword (unique per test).
    Falls back to a sanitized message fragment.
    """
    # Use the test node ID directly — it's unique and stable
    # e.g. "tests/test_foo.py::TestBar::test_baz"
    return test_id.lower().replace(" ", "_")
