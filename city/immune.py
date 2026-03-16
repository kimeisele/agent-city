"""
CityImmune — Structural Self-Healing with Hebbian Learning.

Wraps ShuddhiEngine (CST surgical healing) + HebbianSynaptic
(learning which remedies work for which failure patterns).

Pipeline:
  contract_failure → diagnose(pattern) → get_remedy_confidence(pattern, remedy)
      → heal(file, rule_id) → CST surgical fix
      → learn(pattern, remedy, success) → update synapse weight

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from city.pathogen_index import PathogenIndex

logger = logging.getLogger("AGENT_CITY.IMMUNE")


@dataclass
class DiagnosisResult:
    """Result of diagnosing a failure pattern."""

    pattern: str
    rule_id: str | None
    file_path: Path | None
    confidence: float  # Hebbian weight for this pattern→remedy
    healable: bool  # True if remedy exists + confidence > threshold


@dataclass
class HealResult:
    """Result of attempting to heal a diagnosed issue."""

    pattern: str
    rule_id: str
    success: bool
    message: str = ""
    diff: str = ""


# Pathogen catalog — dynamic registry replaces old hardcoded dict
_PATHOGEN_INDEX = PathogenIndex()  # singleton, loaded with built-in pathogens

# Minimum confidence to attempt healing (below = escalate)
_HEAL_THRESHOLD = 0.3

# Circuit Breaker defaults
_MAX_CASCADE_FAILURES = 0  # heal must not increase failures AT ALL
_BREAKER_COOLDOWN_S = 300  # 5 min cooldown after a cytokine event
_MAX_CONSECUTIVE_ROLLBACKS = 3  # trip breaker after N rollbacks in a row


@dataclass
class CytokineBreaker:
    """Circuit breaker state — prevents autoimmune cascades.

    If a heal attempt increases the total number of test failures,
    the fix is rolled back and the pathogen is escalated. After
    max_consecutive_rollbacks the breaker trips and ALL healing
    is suspended until cooldown expires.
    """

    rollbacks: int = 0
    consecutive_rollbacks: int = 0
    tripped: bool = False
    tripped_at: float = 0.0
    cooldown_s: float = _BREAKER_COOLDOWN_S
    max_consecutive: int = _MAX_CONSECUTIVE_ROLLBACKS
    last_baseline_failures: int = 0

    def record_rollback(self) -> None:
        """Record a rollback event. Trips breaker if too many in a row."""
        self.rollbacks += 1
        self.consecutive_rollbacks += 1
        if self.consecutive_rollbacks >= self.max_consecutive:
            self.tripped = True
            self.tripped_at = time.time()
            logger.critical(
                "CYTOKINE STORM: Circuit breaker TRIPPED after %d consecutive rollbacks. "
                "All healing suspended for %ds.",
                self.consecutive_rollbacks, int(self.cooldown_s),
            )

    def record_success(self) -> None:
        """Successful heal — reset consecutive counter."""
        self.consecutive_rollbacks = 0

    def is_open(self) -> bool:
        """True if breaker is tripped and cooldown has not expired."""
        if not self.tripped:
            return False
        elapsed = time.time() - self.tripped_at
        if elapsed >= self.cooldown_s:
            # Cooldown expired — half-open, allow one attempt
            self.tripped = False
            self.consecutive_rollbacks = 0
            logger.info("Circuit breaker: cooldown expired, healing re-enabled.")
            return False
        return True

    def stats(self) -> dict:
        return {
            "rollbacks": self.rollbacks,
            "consecutive_rollbacks": self.consecutive_rollbacks,
            "tripped": self.tripped,
            "cooldown_remaining": (
                max(0, self.cooldown_s - (time.time() - self.tripped_at))
                if self.tripped else 0
            ),
        }


@dataclass
class CityImmune:
    """Structural self-healing with learned remedy confidence.

    Uses ShuddhiEngine for CST surgical fixes.
    Uses HebbianSynaptic to learn which remedies work.
    """

    _engine: object = field(default=None)  # ShuddhiEngine
    _learning: object = field(default=None)  # CityLearning
    _available: bool = field(default=False)
    _heals_attempted: int = 0
    _heals_succeeded: int = 0
    _heals_rolled_back: int = 0
    _breaker: CytokineBreaker = field(default_factory=CytokineBreaker)

    def __post_init__(self) -> None:
        if self._engine is not None:
            self._available = True
            return

        try:
            from vibe_core.mahamantra.dharma.kumaras.engine import ShuddhiEngine

            self._engine = ShuddhiEngine()
            self._available = True
            remedies = self._engine.list_remedies()
            logger.info(
                "CityImmune initialized (%d remedies)",
                len(remedies),
            )
        except Exception as e:
            logger.warning("ShuddhiEngine unavailable: %s", e)
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def diagnose(self, detail: str) -> DiagnosisResult:
        """Diagnose a failure pattern → find matching remedy + confidence.

        Args:
            detail: Audit finding detail text (e.g. "any_type usage in foo.py").

        Returns:
            DiagnosisResult with rule_id, file_path, confidence, healable.
        """
        rule_id = _match_rule_id(detail)
        file_path = _extract_file_path(detail)
        confidence = 0.5  # default

        # Check Hebbian confidence for this pattern→remedy
        if rule_id and self._learning is not None:
            confidence = self._learning.get_confidence(
                f"immune:{rule_id}",
                "heal",
            )

        healable = (
            self._available
            and rule_id is not None
            and file_path is not None
            and confidence >= _HEAL_THRESHOLD
            and self._engine is not None
            and self._engine.can_heal(rule_id)
        )

        return DiagnosisResult(
            pattern=detail,
            rule_id=rule_id,
            file_path=file_path,
            confidence=confidence,
            healable=healable,
        )

    def heal(self, diagnosis: DiagnosisResult) -> HealResult:
        """Attempt CST surgical healing based on diagnosis.

        Records outcome in Hebbian learning if CityLearning is wired.
        """
        if not diagnosis.healable or diagnosis.rule_id is None or diagnosis.file_path is None:
            return HealResult(
                pattern=diagnosis.pattern,
                rule_id=diagnosis.rule_id or "unknown",
                success=False,
                message="Not healable (no remedy or low confidence)",
            )

        self._heals_attempted += 1

        try:
            result = self._engine.purify(diagnosis.file_path, diagnosis.rule_id)
            success = result.success
            diff = result.diff if hasattr(result, "diff") else ""
            message = result.message if hasattr(result, "message") else ""

            if success:
                self._heals_succeeded += 1

            # Learn from outcome
            self._learn(diagnosis.rule_id, success)

            return HealResult(
                pattern=diagnosis.pattern,
                rule_id=diagnosis.rule_id,
                success=success,
                message=message,
                diff=diff,
            )
        except Exception as e:
            self._learn(diagnosis.rule_id, False)
            logger.warning(
                "Immune heal failed for %s (%s): %s",
                diagnosis.file_path,
                diagnosis.rule_id,
                e,
            )
            return HealResult(
                pattern=diagnosis.pattern,
                rule_id=diagnosis.rule_id,
                success=False,
                message=str(e),
            )

    def scan_and_heal(self, details: list[str]) -> list[HealResult]:
        """Diagnose + heal with Circuit Breaker (Cytokine Storm Prevention).

        For each healable finding:
        1. Check circuit breaker — if tripped, skip all healing
        2. Snapshot test baseline (failure count BEFORE heal)
        3. Apply CST surgical fix
        4. Re-count test failures AFTER fix
        5. If failures increased → ROLLBACK + escalate pathogen
        6. If failures decreased or unchanged → accept fix

        Returns list of HealResults for all attempted heals.
        """
        # Circuit breaker check — are we in a cytokine storm?
        if self._breaker.is_open():
            logger.warning(
                "Immune: Circuit breaker OPEN — all healing suspended. "
                "Cooldown remaining: %ds",
                int(self._breaker.cooldown_s - (time.time() - self._breaker.tripped_at)),
            )
            return []

        results: list[HealResult] = []
        for detail in details:
            # Re-check breaker each iteration (may trip mid-batch)
            if self._breaker.is_open():
                logger.warning(
                    "Immune: Circuit breaker tripped mid-batch"
                    " — aborting remaining heals."
                )
                break

            diagnosis = self.diagnose(detail)
            if not diagnosis.healable:
                continue

            # Step 1: Snapshot baseline
            baseline = self._count_test_failures()
            if baseline is None:
                logger.warning("Immune: Cannot count test failures — skipping heal for safety.")
                continue
            self._breaker.last_baseline_failures = baseline

            # Step 2: Apply the fix
            result = self.heal(diagnosis)
            results.append(result)

            if not result.success:
                logger.info(
                    "Immune: heal failed for %s → %s (confidence=%.2f)",
                    diagnosis.rule_id, diagnosis.file_path, diagnosis.confidence,
                )
                continue

            # Step 3: Re-count failures after fix
            after = self._count_test_failures()
            if after is None:
                # Can't verify → rollback for safety
                logger.warning(
                    "Immune: Cannot verify fix — rolling back %s for safety.",
                    diagnosis.file_path,
                )
                self._rollback_file(diagnosis.file_path)
                result.success = False
                result.message = "Rolled back: verification unavailable"
                self._heals_rolled_back += 1
                self._breaker.record_rollback()
                self._learn(diagnosis.rule_id, False)
                continue

            delta = after - baseline

            if delta > _MAX_CASCADE_FAILURES:
                # CYTOKINE DETECTED — rollback!
                logger.error(
                    "CYTOKINE: heal of '%s' in %s INCREASED failures by %d "
                    "(%d → %d). ROLLING BACK.",
                    diagnosis.rule_id, diagnosis.file_path,
                    delta, baseline, after,
                )
                self._rollback_file(diagnosis.file_path)
                result.success = False
                result.message = (
                    f"Rolled back: fix increased failures by {delta} "
                    f"({baseline} → {after})"
                )
                self._heals_rolled_back += 1
                self._heals_succeeded -= 1  # undo the success count from heal()
                self._breaker.record_rollback()
                self._learn(diagnosis.rule_id, False)
            else:
                # Fix is safe — accept
                self._breaker.record_success()
                logger.info(
                    "Immune: %s → %s VERIFIED (failures: %d → %d, confidence=%.2f)",
                    diagnosis.rule_id, diagnosis.file_path,
                    baseline, after, diagnosis.confidence,
                )

        return results

    def run_self_diagnostics(self) -> list[HealResult]:
        """SOTA CI/CD: Autonomous Introspection.

        The immune system runs its own tests in an isolated subprocess,
        forcing strict JSON output so we can precisely extract tracebacks
        without brittle regex scanning of stdout.
        """
        logger.info("Immune: Initiating Autonomous Self-Diagnostic...")

        # Determine paths
        city_dir = Path(__file__).parent
        repo_root = city_dir.parent
        test_dir = repo_root / "tests"
        report_path = repo_root / ".introspection.json"

        if report_path.exists():
            report_path.unlink()

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_dir),
            "-q",
            "--json-report",
            f"--json-report-file={report_path}",
        ]

        try:
            # Execute the tests (The Mirror)
            subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if not report_path.exists():
                logger.error("Immune: Self-Diagnostic failed to generate JSON report.")
                return []

            # Digestion: Parse structured failures
            with open(report_path, "r") as f:
                report = json.load(f)

            summary = report.get("summary", {})
            failed_count = summary.get("failed", 0)

            if failed_count == 0:
                logger.info("Immune: Self-Diagnostic passed. Federation is Watertight.")
                # TODO: Boost MantraShield
                return []

            logger.warning("Immune: Bleeding detected! %d tests failed.", failed_count)

            # Adaptive immunity: auto-discover new pathogens from failures
            _PATHOGEN_INDEX.ingest_diagnostics(report)

            # Extract tracebacks as pathogens
            pathogens = []
            for test in report.get("tests", []):
                if test.get("outcome") == "failed":
                    crash = test.get("call", {}).get("crash", {})
                    path = crash.get("path", "")
                    message = crash.get("message", "")

                    if path and message:
                        # Reconstruct a generic audit-like detail string for our Hebbian parser
                        # e.g., "Failure in test_foo.py: some_error"
                        pathogens.append(f"Failure in {path}: {message}")

            # Push pathogens into the Healing System
            if pathogens:
                return self.scan_and_heal(pathogens)

            return []

        except subprocess.TimeoutExpired:
            logger.error("Immune: Self-Diagnostic TIMED OUT (120s).")
            return []
        except Exception as e:
            logger.error("Immune: Self-Diagnostic critical error: %s", e)
            return []

    def list_remedies(self) -> list[str]:
        """List available ShuddhiEngine remedy rule_ids."""
        if not self._available or self._engine is None:
            return []
        return self._engine.list_remedies()

    def stats(self) -> dict:
        """Immune system stats for reflection output."""
        remedy_count = len(self.list_remedies())

        result: dict = {
            "available": self._available,
            "remedies": remedy_count,
            "heals_attempted": self._heals_attempted,
            "heals_succeeded": self._heals_succeeded,
            "heals_rolled_back": self._heals_rolled_back,
            "circuit_breaker": self._breaker.stats(),
            "pathogen_index": _PATHOGEN_INDEX.stats(),
        }

        if self._heals_attempted > 0:
            result["success_rate"] = round(
                self._heals_succeeded / self._heals_attempted,
                3,
            )

        return result

    def _learn(self, rule_id: str, success: bool) -> None:
        """Record healing outcome in Hebbian learning."""
        if self._learning is not None:
            self._learning.record_outcome(
                f"immune:{rule_id}",
                "heal",
                success,
            )

    # ── Circuit Breaker Internals ────────────────────────────────────────

    def _count_test_failures(self) -> Optional[int]:
        """Run pytest in counting mode — returns number of failures, or None on error.

        Uses --co (collect-only) + a quick -x run to get failure count
        without full execution overhead when possible.
        """
        city_dir = Path(__file__).parent
        repo_root = city_dir.parent
        test_dir = repo_root / "tests"
        report_path = repo_root / ".breaker_check.json"

        if report_path.exists():
            report_path.unlink()

        cmd = [
            sys.executable, "-m", "pytest",
            str(test_dir), "-q",
            "--json-report",
            f"--json-report-file={report_path}",
            "--tb=no",  # skip tracebacks for speed
        ]

        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if not report_path.exists():
                return None
            with open(report_path, "r") as f:
                report = json.load(f)
            return report.get("summary", {}).get("failed", 0)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            logger.error("Circuit breaker: test count failed: %s", e)
            return None
        finally:
            if report_path.exists():
                try:
                    report_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _rollback_file(file_path: Optional[Path]) -> bool:
        """Surgical rollback — restore a single file from git HEAD.

        Does NOT use git reset --hard (too destructive for multi-agent).
        Only restores the specific file that was modified by the heal.
        """
        if file_path is None or not file_path.exists():
            return False

        try:
            subprocess.run(
                ["git", "checkout", "HEAD", "--", str(file_path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            logger.info("Circuit breaker: rolled back %s to HEAD", file_path)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Circuit breaker: rollback FAILED for %s: %s", file_path, e)
            return False


def _match_rule_id(detail: str) -> str | None:
    """Map an audit finding detail to a remedy rule_id via PathogenIndex."""
    entry = _PATHOGEN_INDEX.lookup(detail)
    return entry.remedy_id if entry is not None else None


def _extract_file_path(detail: str) -> Path | None:
    """Try to extract a .py file path from a detail string."""
    import re

    match = re.search(r"([\w/.]+\.py)", detail)
    if match:
        candidate = Path(match.group(1))
        if candidate.exists():
            return candidate
    return None
