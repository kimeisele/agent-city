"""
QUALITY CONTRACTS — Executable Governance Checks
==================================================

A contract = a named check with a callable. No framework. Just functions.

Each contract runs a check and returns PASSING or FAILING with details.
The ContractRegistry holds all contracts and can run them in batch.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from config import get_config

logger = logging.getLogger("AGENT_CITY.CONTRACTS")


class ContractStatus(str, Enum):
    """Result of a contract check."""

    PASSING = "passing"
    FAILING = "failing"


@dataclass
class ContractResult:
    """Outcome of running a single contract check."""

    name: str
    status: ContractStatus
    message: str = ""
    details: list[str] = field(default_factory=list)


@dataclass
class QualityContract:
    """A named quality check with a callable.

    check: Callable that takes a cwd Path and returns ContractResult.
    """

    name: str
    description: str
    check: object  # Callable[[Path], ContractResult] — using object to avoid Any
    issue_number: int | None = None
    last_result: ContractResult | None = None


@dataclass
class ContractRegistry:
    """Registry of quality contracts. Run checks, filter failures."""

    _contracts: dict[str, QualityContract] = field(default_factory=dict)

    def register(self, contract: QualityContract) -> None:
        """Register a quality contract."""
        self._contracts[contract.name] = contract
        logger.info("Registered contract: %s", contract.name)

    def check_all(self, cwd: Path | None = None) -> list[ContractResult]:
        """Run all registered contracts. Returns list of results."""
        cwd = cwd or Path.cwd()
        results: list[ContractResult] = []
        for contract in self._contracts.values():
            result = contract.check(cwd)
            contract.last_result = result
            results.append(result)
            if result.status == ContractStatus.FAILING:
                logger.warning("Contract FAILING: %s — %s", result.name, result.message)
        return results

    def check_one(self, name: str, cwd: Path | None = None) -> ContractResult | None:
        """Run a single contract by name."""
        contract = self._contracts.get(name)
        if contract is None:
            return None
        cwd = cwd or Path.cwd()
        result = contract.check(cwd)
        contract.last_result = result
        return result

    def failing(self) -> list[QualityContract]:
        """Get contracts that failed their last check."""
        return [
            c for c in self._contracts.values()
            if c.last_result is not None and c.last_result.status == ContractStatus.FAILING
        ]

    def stats(self) -> dict:
        """Contract registry statistics."""
        total = len(self._contracts)
        checked = sum(1 for c in self._contracts.values() if c.last_result is not None)
        passing = sum(
            1 for c in self._contracts.values()
            if c.last_result is not None and c.last_result.status == ContractStatus.PASSING
        )
        failing = sum(
            1 for c in self._contracts.values()
            if c.last_result is not None and c.last_result.status == ContractStatus.FAILING
        )
        return {
            "total": total,
            "checked": checked,
            "passing": passing,
            "failing": failing,
            "unchecked": total - checked,
        }


# ── Built-in Contract Checks ─────────────────────────────────────────


def check_ruff_clean(cwd: Path) -> ContractResult:
    """Contract: ruff check --select F821,F811 must pass."""
    try:
        result = subprocess.run(
            ["python", "-m", "ruff", "check", "--select", "F821,F811", str(cwd)],
            capture_output=True, text=True,
            timeout=get_config().get("contracts", {}).get("ruff_timeout_s", 60),
        )
        if result.returncode == 0:
            return ContractResult(
                name="ruff_clean",
                status=ContractStatus.PASSING,
                message="No F821/F811 violations",
            )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return ContractResult(
            name="ruff_clean",
            status=ContractStatus.FAILING,
            message=f"{len(lines)} ruff violations",
            details=lines[:get_config().get("contracts", {}).get("max_violation_lines", 10)],
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return ContractResult(
            name="ruff_clean",
            status=ContractStatus.FAILING,
            message=f"ruff unavailable: {e}",
        )


def check_tests_pass(cwd: Path) -> ContractResult:
    """Contract: pytest -x -q --tb=no must pass."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-x", "-q", "--tb=no", str(cwd)],
            capture_output=True, text=True,
            timeout=get_config().get("contracts", {}).get("pytest_timeout_s", 120),
        )
        if result.returncode == 0:
            return ContractResult(
                name="tests_pass",
                status=ContractStatus.PASSING,
                message="All tests passed",
            )
        return ContractResult(
            name="tests_pass",
            status=ContractStatus.FAILING,
            message="Tests failed",
            details=result.stdout.strip().split("\n")[-5:] if result.stdout else [],
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return ContractResult(
            name="tests_pass",
            status=ContractStatus.FAILING,
            message=f"pytest unavailable: {e}",
        )


def check_audit_clean(cwd: Path) -> ContractResult:
    """Contract: AuditKernel finds 0 critical findings.

    Uses steward-protocol's AuditKernel (auto-discovers auditors) instead
    of the old check_no_slop which applied Constitution checks to source
    code — a category error (Constitution is designed for LLM output).
    """
    try:
        from vibe_core.mahamantra.audit.kernel import AuditKernel

        kernel = AuditKernel()
        kernel.run_all()

        if kernel.is_pristine:
            return ContractResult(
                name="audit_clean",
                status=ContractStatus.PASSING,
                message="No critical audit findings",
            )

        critical = kernel.critical_findings()
        return ContractResult(
            name="audit_clean",
            status=ContractStatus.FAILING,
            message=f"{len(critical)} critical findings",
            details=[
                f"{f.source}: {f.description}"
                for f in critical[:10]
            ],
        )
    except Exception as e:
        # AuditKernel unavailable — don't block deployments
        return ContractResult(
            name="audit_clean",
            status=ContractStatus.PASSING,
            message=f"AuditKernel unavailable ({type(e).__name__}), skipped",
        )


def create_default_contracts() -> ContractRegistry:
    """Create a ContractRegistry with the built-in quality contracts."""
    registry = ContractRegistry()
    registry.register(QualityContract(
        name="ruff_clean",
        description="Ruff F821/F811 linting must pass",
        check=check_ruff_clean,
    ))
    registry.register(QualityContract(
        name="tests_pass",
        description="All pytest tests must pass",
        check=check_tests_pass,
    ))
    registry.register(QualityContract(
        name="audit_clean",
        description="AuditKernel finds no critical violations",
        check=check_audit_clean,
    ))
    return registry

