"""Layer 4 Tests — Action Delegation (Self-Healing Loop)."""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Phase 1: IntentExecutor Unit Tests ────────────────────────────────


def test_ruff_fix_runs_subprocess():
    """Ruff fix runs subprocess with correct args."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))

    with patch("city.executor.subprocess.run") as mock_run:
        # First call: ruff --fix (success)
        # Second call: ruff re-check (success, returncode=0)
        # Third call: git diff --name-only (changed files)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # ruff --fix
            MagicMock(returncode=0, stdout="", stderr=""),  # ruff re-check
            MagicMock(returncode=0, stdout="fixed.py\n", stderr=""),  # git diff
        ]

        result = executor.execute_heal("ruff_clean", ["F811 test.py:1"])

    assert result.action_taken == "ruff_fix"
    assert result.success is True
    assert result.contract_name == "ruff_clean"

    # Verify ruff --fix was called
    first_call = mock_run.call_args_list[0]
    assert "ruff" in first_call.args[0][2]
    assert "--fix" in first_call.args[0]


def test_ruff_fix_still_failing_escalates():
    """Ruff fix runs but re-check still fails — escalate."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))

    with patch("city.executor.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # ruff --fix
            MagicMock(returncode=1, stdout="test.py:1: F821\n", stderr=""),  # re-check fails
        ]

        result = executor.execute_heal("ruff_clean", [])

    assert result.success is False
    assert result.action_taken == "escalate"
    assert "violations remain" in result.message


def test_audit_clean_tries_healer_then_escalates():
    """audit_clean attempts CellularHealer, escalates if no match."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))
    # Detail text doesn't match any known remedy → falls through to escalate
    result = executor.execute_heal("audit_clean", ["DriftAuditor: lineage broken"])

    assert result.action_taken == "escalate"
    assert result.contract_name == "audit_clean"


def test_tests_escalate():
    """tests_pass always escalates (cannot auto-fix test failures)."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))
    result = executor.execute_heal("tests_pass", ["FAILED test_foo.py"])

    assert result.success is False
    assert result.action_taken == "escalate"
    assert result.contract_name == "tests_pass"


def test_unknown_contract_escalates():
    """Unknown contract name escalates."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))
    result = executor.execute_heal("unknown_contract", ["something"])

    assert result.success is False
    assert result.action_taken == "escalate"
    assert result.contract_name == "unknown_contract"


def test_dry_run_no_subprocess():
    """dry_run=True skips all subprocess calls."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"), _dry_run=True)

    with patch("city.executor.subprocess.run") as mock_run:
        result = executor.execute_heal("ruff_clean", ["F811 test.py:1"])

    # No subprocess calls in dry_run mode
    mock_run.assert_not_called()
    assert result.success is True
    assert result.action_taken == "ruff_fix"
    assert "(dry_run)" in result.files_changed


# ── Phase 1b: CellularHealer Integration ─────────────────────────────


def test_cellular_heal_available():
    """CellularHealer initializes and lists remedies."""
    from vibe_core.mahamantra.dharma.kumaras.healing_intent import get_cellular_healer

    healer = get_cellular_healer()
    remedies = healer.list_remedies()
    assert isinstance(remedies, list)
    assert len(remedies) > 0
    # Known remedies from steward-protocol
    assert "f811_redefinition" in remedies or "any_type_usage" in remedies


def test_audit_clean_dry_run_uses_healer():
    """audit_clean in dry_run mode confirms healer is available."""
    from city.executor import IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"), _dry_run=True)
    result = executor.execute_heal("audit_clean", ["DriftAuditor: f811 redefinition"])

    assert result.contract_name == "audit_clean"
    assert result.action_taken == "cellular_heal"
    assert result.success is True
    assert "remedies available" in result.message


def test_extract_rule_id_mapping():
    """_extract_rule_id maps audit details to remedy rule_ids."""
    from city.executor import _extract_rule_id

    assert _extract_rule_id("TypeAuditor: any_type usage detected") == "any_type_usage"
    assert _extract_rule_id("RuffAuditor: F811 redefinition in module.py") == "f811_redefinition"
    assert _extract_rule_id("IOAuditor: unsafe_io_write found") == "unsafe_io_write"
    assert _extract_rule_id("DriftAuditor: lineage broken") is None


# ── Phase 2: PR Workflow Unit Tests ───────────────────────────────────


def test_create_pr_success():
    """Successful fix creates branch, commit, and PR."""
    from city.executor import FixResult, IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))

    fix = FixResult(
        contract_name="ruff_clean",
        success=True,
        action_taken="ruff_fix",
        files_changed=["fixed.py"],
        message="Fixed",
    )

    with patch.object(executor, "_run_git") as mock_git, \
         patch("city.executor.subprocess.run") as mock_run:
        # git checkout -b → ok
        # git add -A → ok
        # git diff --staged --quiet → returncode=1 (changes exist)
        # git commit → ok
        # git push → ok
        # git checkout main → ok
        mock_git.side_effect = [
            MagicMock(returncode=0),  # checkout -b
            MagicMock(returncode=0),  # add -A
            MagicMock(returncode=1),  # diff --staged --quiet (has changes)
            MagicMock(returncode=0, stdout="[fix/ruff_clean_5 abc1234] fix\n"),  # commit
            MagicMock(returncode=0),  # push
            MagicMock(returncode=0),  # checkout main
        ]
        # gh pr create
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/test/repo/pull/42\n",
        )

        pr = executor.create_fix_pr(fix, heartbeat_count=5)

    assert pr is not None
    assert pr.success is True
    assert pr.branch == "fix/ruff_clean_5"
    assert "pull/42" in pr.pr_url


def test_create_pr_no_changes_aborts():
    """No staged changes → no PR created."""
    from city.executor import FixResult, IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"))

    fix = FixResult(
        contract_name="ruff_clean",
        success=True,
        action_taken="ruff_fix",
        files_changed=["fixed.py"],
        message="Fixed",
    )

    with patch.object(executor, "_run_git") as mock_git:
        mock_git.side_effect = [
            MagicMock(returncode=0),  # checkout -b
            MagicMock(returncode=0),  # add -A
            MagicMock(returncode=0),  # diff --staged --quiet → NO changes
            MagicMock(returncode=0),  # checkout main
            MagicMock(returncode=0),  # branch -D (cleanup)
        ]

        pr = executor.create_fix_pr(fix, heartbeat_count=5)

    assert pr is not None
    assert pr.success is False
    assert "No changes" in pr.message


def test_create_pr_dry_run():
    """dry_run returns mock PRResult without git calls."""
    from city.executor import FixResult, IntentExecutor

    executor = IntentExecutor(_cwd=Path("/tmp/test"), _dry_run=True)

    fix = FixResult(
        contract_name="ruff_clean",
        success=True,
        action_taken="ruff_fix",
        files_changed=["fixed.py"],
        message="Fixed",
    )

    with patch("city.executor.subprocess.run") as mock_run:
        pr = executor.create_fix_pr(fix, heartbeat_count=3)

    mock_run.assert_not_called()
    assert pr is not None
    assert pr.success is True
    assert pr.branch == "fix/ruff_clean_3"
    assert "(dry_run)" in pr.pr_url


# ── Phase 3: Mayor Integration Tests ─────────────────────────────────


def _make_mayor(tmpdir: Path, **kwargs):
    """Helper: create a Mayor with temporary state."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    return Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
        **kwargs,
    )


def test_karma_executes_heal_on_failing_contract():
    """Failing contract in DHARMA → fix attempted in KARMA."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )
    from city.executor import IntentExecutor

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(
            name="ruff_clean",
            status=ContractStatus.FAILING,
            message="2 violations",
            details=["test.py:1: F811"],
        )

    contracts = ContractRegistry()
    contracts.register(QualityContract(
        name="ruff_clean", description="Ruff", check=fail_check,
    ))

    executor = IntentExecutor(_cwd=tmpdir, _dry_run=True)
    mayor = _make_mayor(tmpdir, _contracts=contracts, _executor=executor)

    # Run GENESIS + DHARMA (contracts checked) + KARMA (heal attempted)
    results = mayor.run_cycle(3)

    karma = results[2]
    assert karma["department"] == "KARMA"

    heal_ops = [o for o in karma["operations"] if o.startswith("heal:")]
    assert len(heal_ops) >= 1
    assert "ruff_clean" in heal_ops[0]

    shutil.rmtree(tmpdir)


def test_karma_creates_pr_after_fix():
    """Successful fix → PR created in KARMA operations."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )
    from city.executor import IntentExecutor

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(
            name="ruff_clean",
            status=ContractStatus.FAILING,
            message="violations",
            details=["test.py:1: F811"],
        )

    contracts = ContractRegistry()
    contracts.register(QualityContract(
        name="ruff_clean", description="Ruff", check=fail_check,
    ))

    # dry_run executor returns success with files_changed
    executor = IntentExecutor(_cwd=tmpdir, _dry_run=True)
    mayor = _make_mayor(tmpdir, _contracts=contracts, _executor=executor)

    results = mayor.run_cycle(3)
    karma = results[2]

    # Should have both heal and pr_created operations
    pr_ops = [o for o in karma["operations"] if o.startswith("pr_created:")]
    assert len(pr_ops) >= 1

    shutil.rmtree(tmpdir)


def test_karma_no_executor_backward_compatible():
    """_executor=None → old KARMA behavior (no heal attempts)."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(
            name="ruff_clean",
            status=ContractStatus.FAILING,
            message="violations",
        )

    contracts = ContractRegistry()
    contracts.register(QualityContract(
        name="ruff_clean", description="Ruff", check=fail_check,
    ))

    # No executor wired — backward compatible
    mayor = _make_mayor(tmpdir, _contracts=contracts)

    results = mayor.run_cycle(3)
    karma = results[2]

    # No heal operations
    heal_ops = [o for o in karma["operations"] if o.startswith("heal:")]
    assert len(heal_ops) == 0

    shutil.rmtree(tmpdir)


def test_full_rotation_heal_cycle():
    """Full MURALI rotation: DHARMA detects → KARMA fixes → operations logged."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )
    from city.executor import IntentExecutor
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(
            name="audit_clean",
            status=ContractStatus.FAILING,
            message="1 critical finding",
            details=["DriftAuditor: lineage broken"],
        )

    contracts = ContractRegistry()
    contracts.register(QualityContract(
        name="audit_clean", description="Audit clean", check=fail_check,
    ))

    executor = IntentExecutor(_cwd=tmpdir, _dry_run=True)
    sankalpa = SankalpaOrchestrator(workspace=tmpdir)

    mayor = _make_mayor(
        tmpdir,
        _contracts=contracts,
        _executor=executor,
        _sankalpa=sankalpa,
    )

    results = mayor.run_cycle(4)

    # DHARMA: contract detected as failing
    dharma = results[1]
    assert dharma["department"] == "DHARMA"
    contract_ops = [a for a in dharma["governance_actions"] if "contract_failing" in a]
    assert len(contract_ops) >= 1

    # KARMA: heal attempted (CellularHealer invoked in dry_run → success)
    karma = results[2]
    assert karma["department"] == "KARMA"
    heal_ops = [o for o in karma["operations"] if o.startswith("heal:")]
    assert len(heal_ops) >= 1
    assert "audit_clean" in heal_ops[0]
    # In dry_run mode, CellularHealer reports success (remedies available)
    assert "cellular_heal" in heal_ops[0] or "escalate" in heal_ops[0]

    # MOKSHA: reflection runs
    moksha = results[3]
    assert moksha["department"] == "MOKSHA"

    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        # Phase 1: Executor unit tests
        test_ruff_fix_runs_subprocess,
        test_ruff_fix_still_failing_escalates,
        test_audit_clean_tries_healer_then_escalates,
        test_tests_escalate,
        test_unknown_contract_escalates,
        test_dry_run_no_subprocess,
        # Phase 1b: CellularHealer
        test_cellular_heal_available,
        test_audit_clean_dry_run_uses_healer,
        test_extract_rule_id_mapping,
        # Phase 2: PR workflow
        test_create_pr_success,
        test_create_pr_no_changes_aborts,
        test_create_pr_dry_run,
        # Phase 3: Mayor integration
        test_karma_executes_heal_on_failing_contract,
        test_karma_creates_pr_after_fix,
        test_karma_no_executor_backward_compatible,
        test_full_rotation_heal_cycle,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            failed += 1

    print(f"\n=== {passed}/{passed + failed} LAYER 4 TESTS PASSED ===")
    if failed:
        print(f"    {failed} FAILED")
        sys.exit(1)
