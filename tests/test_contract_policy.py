"""Maintenance Slice A1 contract-policy tests."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from city.contracts import (
    BOUNDED_CONTRACT_IDS,
    ContractRegistry,
    ContractStatus,
    ContractResult,
    QualityContract,
)


def _result(name: str, status: ContractStatus = ContractStatus.PASSING) -> ContractResult:
    return ContractResult(name=name, status=status, message=status.value)


def _registry() -> ContractRegistry:
    registry = ContractRegistry()
    for name in ("ruff_clean", "tests_pass", "audit_clean", "integrity"):
        registry.register(
            QualityContract(
                name=name,
                description=name,
                check=lambda _cwd, name=name: _result(name),
            )
        )
    return registry


def test_full_runs_every_registered_contract_and_records_audit(tmp_path: Path):
    registry = _registry()
    results, audit = registry.check_all(
        tmp_path,
        invocation=registry.new_invocation("full", invocation_id="full-success"),
    )

    assert [result.name for result in results] == [
        "ruff_clean",
        "tests_pass",
        "audit_clean",
        "integrity",
    ]
    assert audit.policy_mode == "full"
    assert audit.terminal_result == "pass"
    assert audit.executed_check_ids == tuple(result.name for result in results)
    assert audit.contract_invocation_id == "full-success"


def test_full_failure_is_visible(tmp_path: Path):
    registry = _registry()
    registry._contracts["tests_pass"].check = lambda _cwd: _result(
        "tests_pass", ContractStatus.FAILING
    )

    results, audit = registry.check_all(
        tmp_path,
        invocation=registry.new_invocation("full", invocation_id="full-failure"),
    )

    assert any(result.status is ContractStatus.FAILING for result in results)
    assert audit.terminal_result == "fail"
    assert audit.reason_code == "contract_failed"


def test_bounded_runs_only_closed_allowlist(tmp_path: Path):
    registry = _registry()
    results, audit = registry.check_all(
        tmp_path,
        invocation=registry.new_invocation("bounded", invocation_id="bounded-success"),
    )

    assert [result.name for result in results] == list(BOUNDED_CONTRACT_IDS)
    assert audit.policy_mode == "bounded"
    assert audit.executed_check_ids == BOUNDED_CONTRACT_IDS


def test_bounded_never_runs_repository_pytest(tmp_path: Path):
    registry = _registry()
    registry._contracts["tests_pass"].check = lambda _cwd: (_ for _ in ()).throw(
        AssertionError("tests_pass must not run in bounded mode")
    )

    results, audit = registry.check_all(
        tmp_path,
        invocation=registry.new_invocation("bounded", invocation_id="bounded-no-pytest"),
    )

    assert [result.name for result in results] == ["ruff_clean", "integrity"]
    assert audit.terminal_result == "pass"


def test_missing_and_unknown_policy_fail_closed(tmp_path: Path):
    registry = _registry()

    missing, missing_audit = registry.check_all(tmp_path, invocation=None)
    assert missing_audit.terminal_result == "unavailable"
    assert missing_audit.reason_code == "missing_policy"
    assert missing[0].name == "contract_execution"

    unknown_invocation = registry.new_invocation("full", invocation_id="unknown-base")
    unknown_invocation = unknown_invocation.__class__(
        invocation_id=unknown_invocation.invocation_id,
        policy="sideways",
        contract_scope=unknown_invocation.contract_scope,
    )
    unknown, unknown_audit = registry.check_all(tmp_path, invocation=unknown_invocation)
    assert unknown_audit.reason_code == "unknown_policy"
    assert unknown[0].name == "contract_execution"


def test_scope_downgrade_attempt_fails_closed(tmp_path: Path):
    registry = _registry()
    full = registry.new_invocation("full", invocation_id="downgrade")
    downgraded = full.__class__(full.invocation_id, "bounded", full.contract_scope)

    results, audit = registry.check_all(tmp_path, invocation=downgraded)

    assert audit.reason_code == "invalid_invocation"
    assert results[0].name == "contract_execution"


def test_direct_recursion_is_rejected_without_child(tmp_path: Path):
    registry = _registry()
    invocation = registry.new_invocation("bounded", invocation_id="recursive")

    def recurse(_cwd: Path) -> ContractResult:
        nested, nested_audit = registry.check_all(tmp_path, invocation=invocation)
        assert nested_audit.reason_code == "reentrant_contract_execution"
        assert nested[0].name == "contract_execution"
        return _result("ruff_clean")

    registry._contracts["ruff_clean"].check = recurse
    results, audit = registry.check_all(tmp_path, invocation=invocation)

    assert audit.terminal_result == "pass"
    assert results[0].name == "ruff_clean"


def test_guard_cleanup_after_exception_allows_later_run(tmp_path: Path):
    registry = _registry()
    invocation = registry.new_invocation("bounded", invocation_id="cleanup")
    calls = {"count": 0}

    def fail_once(_cwd: Path) -> ContractResult:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("synthetic failure")
        return _result("ruff_clean")

    registry._contracts["ruff_clean"].check = fail_once
    first, first_audit = registry.check_all(tmp_path, invocation=invocation)
    second, second_audit = registry.check_all(tmp_path, invocation=invocation)

    assert first_audit.reason_code == "contract_exception"
    assert first[0].name == "contract_execution"
    assert second_audit.terminal_result == "pass"
    assert second[0].name == "ruff_clean"


def test_heartbeat_cli_requires_explicit_policy_for_governance():
    script = Path(__file__).parents[1] / "scripts" / "heartbeat.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--cycles",
            "0",
            "--offline",
            "--governance",
            "--db",
            "/tmp/contract-policy-missing.db",
        ],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--contract-policy is required" in result.stderr


def test_heartbeat_daemon_rejects_bounded_policy():
    script = Path(__file__).parents[1] / "scripts" / "heartbeat.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--daemon",
            "--governance",
            "--contract-policy",
            "bounded",
            "--db",
            "/tmp/contract-policy-daemon.db",
        ],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--daemon requires --contract-policy full" in result.stderr


def test_contracts_hook_propagates_explicit_bounded_invocation(tmp_path: Path):
    from city.hooks.dharma.contracts_issues import ContractsHook

    registry = _registry()
    ctx = SimpleNamespace(
        contracts=registry,
        state_path=tmp_path / "city.db",
        contract_invocation=registry.new_invocation("bounded", invocation_id="hook-bounded"),
    )
    operations: list[str] = []

    ContractsHook().execute(ctx, operations)

    assert any(
        op.startswith("contract_audit:hook-bounded:bounded:pass:ruff_clean,integrity")
        for op in operations
    )
