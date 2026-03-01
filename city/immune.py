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
from dataclasses import dataclass, field
from pathlib import Path

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


# Map audit finding keywords → ShuddhiEngine remedy rule_ids
_PATTERN_TO_REMEDY: dict[str, str] = {
    "any_type": "any_type_usage",
    ": any": "any_type_usage",
    "hardcoded": "hardcoded_constants",
    "magic number": "hardcoded_constants",
    "subprocess": "subprocess_timeout",
    "f811": "f811_redefinition",
    "redefinition": "f811_redefinition",
    "mahajana": "missing_mahajana",
    "unsafe io": "unsafe_io_write",
    "unsafe_io": "unsafe_io_write",
    "get_instance": "get_instance",
    "null signature": "null_signature",
    "null_signature": "null_signature",
}

# Minimum confidence to attempt healing (below = escalate)
_HEAL_THRESHOLD = 0.3


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
        """Diagnose + heal a batch of audit findings.

        Returns list of HealResults for all attempted heals.
        """
        results: list[HealResult] = []
        for detail in details:
            diagnosis = self.diagnose(detail)
            if diagnosis.healable:
                result = self.heal(diagnosis)
                results.append(result)
                logger.info(
                    "Immune: %s → %s (confidence=%.2f, success=%s)",
                    diagnosis.rule_id,
                    diagnosis.file_path,
                    diagnosis.confidence,
                    result.success,
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


def _match_rule_id(detail: str) -> str | None:
    """Map an audit finding detail to a remedy rule_id."""
    detail_lower = detail.lower()
    for keyword, rule_id in _PATTERN_TO_REMEDY.items():
        if keyword in detail_lower:
            return rule_id
    return None


def _extract_file_path(detail: str) -> Path | None:
    """Try to extract a .py file path from a detail string."""
    import re

    match = re.search(r"([\w/.]+\.py)", detail)
    if match:
        candidate = Path(match.group(1))
        if candidate.exists():
            return candidate
    return None
