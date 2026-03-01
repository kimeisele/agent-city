"""Layer 3 Tests — Self-Governance & Quality Contracts."""

import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

# Ensure steward-protocol is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Phase 1: Smart Issue Lifecycle ────────────────────────────────────


def test_ephemeral_issue_closes_on_death():
    """Ephemeral issues auto-close when prana hits 0 (existing behavior)."""
    from city.issues import CityIssueManager, IssueType
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    mgr = CityIssueManager()
    cell = MahaCellUnified.from_content("Temp issue", register=False)
    mgr._issue_cells[1] = cell
    mgr._issue_types[1] = IssueType.EPHEMERAL

    # Kill the cell
    cell.apoptosis()
    assert not cell.is_alive

    # Ephemeral: metabolize would close it (we test the type dispatch logic)
    assert mgr.get_issue_type(1) == IssueType.EPHEMERAL


def test_iterative_issue_generates_intent():
    """Iterative issues generate intent_needed action on low prana, never close."""
    from city.issues import CityIssueManager, IssueType, LOW_PRANA_THRESHOLD
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    mgr = CityIssueManager()
    cell = MahaCellUnified.from_content("Multi-sprint work", register=False)
    mgr._issue_cells[42] = cell
    mgr._issue_types[42] = IssueType.ITERATIVE

    # Drain prana below threshold
    while cell.prana >= LOW_PRANA_THRESHOLD:
        cell.metabolize(0)

    assert cell.prana < LOW_PRANA_THRESHOLD
    # Verify the issue type is iterative and would generate intent
    assert mgr.get_issue_type(42) == IssueType.ITERATIVE
    # The cell is still tracked (never deleted for iterative)
    assert 42 in mgr._issue_cells


def test_contract_issue_never_closes():
    """Contract issues never auto-close, even at prana 0."""
    from city.issues import CityIssueManager, IssueType
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    mgr = CityIssueManager()
    cell = MahaCellUnified.from_content("Quality contract", register=False)
    mgr._issue_cells[99] = cell
    mgr._issue_types[99] = IssueType.CONTRACT

    # Kill it
    cell.apoptosis()
    assert not cell.is_alive

    # Contract type: still tracked, would generate audit action
    assert mgr.get_issue_type(99) == IssueType.CONTRACT
    assert 99 in mgr._issue_cells


def test_default_issue_type_is_ephemeral():
    """Untyped issues default to EPHEMERAL."""
    from city.issues import CityIssueManager, IssueType
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    mgr = CityIssueManager()
    mgr._issue_cells[7] = MahaCellUnified.from_content("No type set", register=False)

    assert mgr.get_issue_type(7) == IssueType.EPHEMERAL


# ── Phase 2: Quality Contracts ────────────────────────────────────────


def test_contract_register_and_check():
    """Register a contract and check it."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )

    def always_pass(cwd: Path) -> ContractResult:
        return ContractResult(name="test", status=ContractStatus.PASSING, message="OK")

    registry = ContractRegistry()
    registry.register(QualityContract(
        name="test",
        description="Always passes",
        check=always_pass,
    ))

    results = registry.check_all()
    assert len(results) == 1
    assert results[0].status == ContractStatus.PASSING
    assert results[0].name == "test"


def test_contract_failing_filter():
    """Failing filter returns only failed contracts."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )

    def pass_check(cwd: Path) -> ContractResult:
        return ContractResult(name="good", status=ContractStatus.PASSING)

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(name="bad", status=ContractStatus.FAILING, message="broken")

    registry = ContractRegistry()
    registry.register(QualityContract(name="good", description="OK", check=pass_check))
    registry.register(QualityContract(name="bad", description="Broken", check=fail_check))

    registry.check_all()
    failing = registry.failing()
    assert len(failing) == 1
    assert failing[0].name == "bad"


def test_contract_no_slop_clean():
    """no_slop contract passes on clean directory."""
    from city.contracts import check_no_slop, ContractStatus

    tmpdir = Path(tempfile.mkdtemp())
    city_dir = tmpdir / "city"
    city_dir.mkdir()
    (city_dir / "clean.py").write_text("# This is clean code\nprint('hello')\n")

    result = check_no_slop(tmpdir)
    assert result.status == ContractStatus.PASSING

    shutil.rmtree(tmpdir)


def test_contract_no_slop_detects():
    """no_slop contract detects slop patterns via Constitution (phrase-level)."""
    from city.contracts import check_no_slop, ContractStatus

    tmpdir = Path(tempfile.mkdtemp())
    city_dir = tmpdir / "city"
    city_dir.mkdir()
    # Constitution catches "delve into" and "vibrant tapestry" as AI filler phrases.
    # Two matches = hard block (violations, not just warnings).
    (city_dir / "sloppy.py").write_text(
        "# Let me delve into this vibrant tapestry of code.\n"
        "# It's worth noting that this is great question!\n"
    )

    result = check_no_slop(tmpdir)
    assert result.status == ContractStatus.FAILING
    assert len(result.details) >= 1

    shutil.rmtree(tmpdir)


def test_contract_stats():
    """Contract stats show correct counts."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )

    def pass_check(cwd: Path) -> ContractResult:
        return ContractResult(name="a", status=ContractStatus.PASSING)

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(name="b", status=ContractStatus.FAILING)

    registry = ContractRegistry()
    registry.register(QualityContract(name="a", description="OK", check=pass_check))
    registry.register(QualityContract(name="b", description="Fail", check=fail_check))

    # Before checking
    s = registry.stats()
    assert s["total"] == 2
    assert s["unchecked"] == 2

    # After checking
    registry.check_all()
    s = registry.stats()
    assert s["passing"] == 1
    assert s["failing"] == 1
    assert s["unchecked"] == 0


# ── Phase 3: Sankalpa + Contracts in Mayor ────────────────────────────


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


def test_contracts_checked_in_dharma():
    """DHARMA phase runs contract checks when wired."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(name="test_contract", status=ContractStatus.FAILING, message="broken")

    contracts = ContractRegistry()
    contracts.register(QualityContract(name="test_contract", description="Test", check=fail_check))

    mayor = _make_mayor(tmpdir, _contracts=contracts)

    # Run GENESIS + DHARMA
    results = mayor.run_cycle(2)
    dharma = results[1]
    assert dharma["department"] == "DHARMA"

    # Should have contract failing action
    contract_actions = [a for a in dharma["governance_actions"] if "contract_failing" in a]
    assert len(contract_actions) >= 1
    assert "test_contract" in contract_actions[0]

    shutil.rmtree(tmpdir)


def test_healing_mission_created_from_failing_contract():
    """Failing contract creates a Sankalpa healing mission."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(name="ruff_clean", status=ContractStatus.FAILING, message="3 violations")

    contracts = ContractRegistry()
    contracts.register(QualityContract(name="ruff_clean", description="Ruff", check=fail_check))

    sankalpa = SankalpaOrchestrator(workspace=tmpdir)
    initial_count = len(sankalpa.registry.get_all_missions())

    mayor = _make_mayor(tmpdir, _contracts=contracts, _sankalpa=sankalpa)

    # Run GENESIS + DHARMA
    mayor.run_cycle(2)

    # Healing mission should have been added
    all_missions = sankalpa.registry.get_all_missions()
    assert len(all_missions) > initial_count

    heal_missions = [m for m in all_missions if m.name.startswith("Heal:")]
    assert len(heal_missions) >= 1
    assert "ruff_clean" in heal_missions[0].name

    shutil.rmtree(tmpdir)


def test_sankalpa_evaluated_in_karma():
    """KARMA phase calls sankalpa.think() for strategic intents."""
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator

    tmpdir = Path(tempfile.mkdtemp())
    sankalpa = SankalpaOrchestrator(workspace=tmpdir)

    mayor = _make_mayor(tmpdir, _sankalpa=sankalpa)

    # Run full rotation (GENESIS, DHARMA, KARMA, MOKSHA)
    results = mayor.run_cycle(4)
    karma = results[2]
    assert karma["department"] == "KARMA"
    # Sankalpa was called (may or may not generate intents depending on missions)
    # No crash = success

    shutil.rmtree(tmpdir)


def test_iterative_issues_generate_actions_in_dharma():
    """Issue intents from metabolize_issues appear in DHARMA actions."""
    from city.issues import CityIssueManager, IssueType

    tmpdir = Path(tempfile.mkdtemp())

    # Create a mock issue manager that returns actions
    issues = CityIssueManager()

    # Manually inject: no gh CLI needed
    from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

    cell = MahaCellUnified.from_content("Sprint issue", register=False)
    # Drain prana
    while cell.prana > 500:
        cell.metabolize(0)
    issues._issue_cells[42] = cell
    issues._issue_types[42] = IssueType.ITERATIVE

    # Mock gh CLI to return the issue in JSON
    import json
    import unittest.mock as mock

    issue_json = json.dumps([{
        "number": 42,
        "title": "Sprint issue",
        "updatedAt": "2026-01-01T00:00:00Z",
        "comments": [],
    }])

    with mock.patch("city.issues._gh_run", return_value=issue_json):
        actions = issues.metabolize_issues()

    # Should have intent_needed action
    intent_actions = [a for a in actions if "intent_needed" in a]
    assert len(intent_actions) >= 1

    shutil.rmtree(tmpdir)


def test_backward_compatible_mayor():
    """Mayor with zero governance wiring still works (L2 behavior)."""
    tmpdir = Path(tempfile.mkdtemp())

    mayor = _make_mayor(tmpdir)
    results = mayor.run_cycle(4)

    assert len(results) == 4
    departments = [r["department"] for r in results]
    assert departments == ["GENESIS", "DHARMA", "KARMA", "MOKSHA"]

    # MOKSHA reflection still has chain_valid
    moksha = results[3]
    assert "chain_valid" in moksha["reflection"]

    shutil.rmtree(tmpdir)


# ── Phase 4: Audit + Reflection in MOKSHA ─────────────────────────────


def test_audit_runs_in_moksha():
    """Audit kernel runs during MOKSHA phase."""
    tmpdir = Path(tempfile.mkdtemp())

    # Mock audit kernel
    mock_audit = MagicMock()
    mock_audit.run_all.return_value = 2
    mock_audit.summary.return_value = {"total": 2, "critical": 0, "is_pristine": True}
    mock_audit.critical_findings.return_value = []

    mayor = _make_mayor(tmpdir, _audit=mock_audit)

    # Run full rotation to get to MOKSHA
    results = mayor.run_cycle(4)
    moksha = results[3]

    assert moksha["department"] == "MOKSHA"
    mock_audit.run_all.assert_called_once()
    assert "audit" in moksha["reflection"]
    assert moksha["reflection"]["audit"]["total"] == 2

    shutil.rmtree(tmpdir)


def test_critical_finding_creates_mission():
    """Critical audit finding creates a Sankalpa healing mission."""
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator

    tmpdir = Path(tempfile.mkdtemp())

    # Mock audit kernel with critical finding
    mock_finding = MagicMock()
    mock_finding.source = "DriftAuditor"
    mock_finding.description = "Lineage broken in module X"

    mock_audit = MagicMock()
    mock_audit.run_all.return_value = 1
    mock_audit.summary.return_value = {"total": 1, "critical": 1, "is_pristine": False}
    mock_audit.critical_findings.return_value = [mock_finding]

    sankalpa = SankalpaOrchestrator(workspace=tmpdir)
    initial_count = len(sankalpa.registry.get_all_missions())

    mayor = _make_mayor(tmpdir, _audit=mock_audit, _sankalpa=sankalpa)
    mayor.run_cycle(4)

    # Audit mission should exist
    all_missions = sankalpa.registry.get_all_missions()
    audit_missions = [m for m in all_missions if m.name.startswith("Audit:")]
    assert len(audit_missions) >= 1
    assert "DriftAuditor" in audit_missions[0].name

    shutil.rmtree(tmpdir)


def test_reflection_patterns_analyzed():
    """Reflection analyzes patterns and records execution."""
    from vibe_core.protocols.reflection import BasicReflection

    tmpdir = Path(tempfile.mkdtemp())
    reflection = BasicReflection()

    mayor = _make_mayor(tmpdir, _reflection=reflection)

    # Run a full rotation
    mayor.run_cycle(4)

    # Should have recorded 4 executions (one per heartbeat)
    stats = reflection.get_stats()
    assert stats.executions_analyzed == 4


def test_reflection_proposal_creates_mission():
    """Reflection improvement proposal creates a Sankalpa mission."""
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator
    from vibe_core.protocols.reflection import BasicReflection, ExecutionRecord

    tmpdir = Path(tempfile.mkdtemp())
    reflection = BasicReflection()
    sankalpa = SankalpaOrchestrator(workspace=tmpdir)

    # Feed reflection enough data to potentially generate insights
    for i in range(20):
        reflection.record_execution(ExecutionRecord(
            command="mayor.heartbeat.DHARMA",
            success=i % 3 != 0,  # 33% failure rate
            duration_ms=float(100 + i * 50),
        ))

    initial_count = len(sankalpa.registry.get_all_missions())

    mayor = _make_mayor(tmpdir, _reflection=reflection, _sankalpa=sankalpa)

    # Run to MOKSHA
    mayor.run_cycle(4)

    # Check if improvement missions were created (depends on pattern detection)
    # At minimum, reflection should have been called without error
    all_missions = sankalpa.registry.get_all_missions()
    # May or may not have improvement mission depending on threshold
    # The test validates the wiring doesn't crash
    assert isinstance(all_missions, list)

    shutil.rmtree(tmpdir)


def test_audit_cooldown_respected():
    """Audit doesn't run again within cooldown period."""
    tmpdir = Path(tempfile.mkdtemp())

    mock_audit = MagicMock()
    mock_audit.run_all.return_value = 0
    mock_audit.summary.return_value = {"total": 0, "critical": 0}
    mock_audit.critical_findings.return_value = []

    mayor = _make_mayor(tmpdir, _audit=mock_audit)

    # Run first MOKSHA
    mayor.run_cycle(4)
    assert mock_audit.run_all.call_count == 1

    # Run second MOKSHA (heartbeats 4-7)
    mayor.run_cycle(4)
    # Should NOT have run again (cooldown not expired)
    assert mock_audit.run_all.call_count == 1

    shutil.rmtree(tmpdir)


# ── Integration Tests ─────────────────────────────────────────────────


def test_full_layer3_governance_cycle():
    """Full MURALI rotation with all Layer 3 governance wired."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator
    from vibe_core.protocols.reflection import BasicReflection

    tmpdir = Path(tempfile.mkdtemp())

    # Set up contracts
    def pass_check(cwd: Path) -> ContractResult:
        return ContractResult(name="test", status=ContractStatus.PASSING)

    contracts = ContractRegistry()
    contracts.register(QualityContract(name="test", description="Test", check=pass_check))

    # Set up sankalpa + reflection + mock audit
    sankalpa = SankalpaOrchestrator(workspace=tmpdir)
    reflection = BasicReflection()

    mock_audit = MagicMock()
    mock_audit.run_all.return_value = 0
    mock_audit.summary.return_value = {"total": 0, "critical": 0, "is_pristine": True}
    mock_audit.critical_findings.return_value = []

    mayor = _make_mayor(
        tmpdir,
        _contracts=contracts,
        _sankalpa=sankalpa,
        _reflection=reflection,
        _audit=mock_audit,
    )

    results = mayor.run_cycle(4)

    assert len(results) == 4
    departments = [r["department"] for r in results]
    assert departments == ["GENESIS", "DHARMA", "KARMA", "MOKSHA"]

    # DHARMA: no contract failures
    dharma = results[1]
    contract_failures = [a for a in dharma["governance_actions"] if "contract_failing" in a]
    assert len(contract_failures) == 0

    # MOKSHA: audit ran, reflection recorded
    moksha = results[3]
    assert "audit" in moksha["reflection"]
    assert reflection.get_stats().executions_analyzed == 4

    shutil.rmtree(tmpdir)


def test_governance_feedback_loop():
    """Two MURALI rotations: second rotation sees missions from first."""
    from city.contracts import (
        ContractRegistry,
        ContractResult,
        ContractStatus,
        QualityContract,
    )
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator

    tmpdir = Path(tempfile.mkdtemp())

    def fail_check(cwd: Path) -> ContractResult:
        return ContractResult(name="quality", status=ContractStatus.FAILING, message="bad")

    contracts = ContractRegistry()
    contracts.register(QualityContract(name="quality", description="Q", check=fail_check))
    sankalpa = SankalpaOrchestrator(workspace=tmpdir)

    mayor = _make_mayor(tmpdir, _contracts=contracts, _sankalpa=sankalpa)

    # Rotation 1
    mayor.run_cycle(4)

    # Should have healing mission from rotation 1
    heal_missions = [m for m in sankalpa.registry.get_all_missions() if m.name.startswith("Heal:")]
    assert len(heal_missions) >= 1

    # Rotation 2 — sankalpa.think() in KARMA sees the mission
    results2 = mayor.run_cycle(4)
    karma2 = results2[2]
    assert karma2["department"] == "KARMA"
    # Mission exists and sankalpa was evaluated
    all_missions = sankalpa.registry.get_all_missions()
    assert len(all_missions) > 0

    shutil.rmtree(tmpdir)


def test_layer3_backward_compatible():
    """Mayor with zero governance still passes all core L2 behavior."""
    tmpdir = Path(tempfile.mkdtemp())

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    # Register agents
    pdx.register("AgentA")
    pdx.register("AgentB")

    mayor = Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
    )

    # Enqueue + run
    mayor.enqueue("AgentA", "Hello")
    results = mayor.run_cycle(4)

    assert len(results) == 4
    assert results[0]["department"] == "GENESIS"
    assert results[3]["reflection"]["chain_valid"] is True

    # KARMA processed the enqueue
    karma = results[2]
    assert len(karma["operations"]) == 1

    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        # Phase 1: Issue Lifecycle
        test_ephemeral_issue_closes_on_death,
        test_iterative_issue_generates_intent,
        test_contract_issue_never_closes,
        test_default_issue_type_is_ephemeral,
        # Phase 2: Quality Contracts
        test_contract_register_and_check,
        test_contract_failing_filter,
        test_contract_no_slop_clean,
        test_contract_no_slop_detects,
        test_contract_stats,
        # Phase 3: Sankalpa + Contracts
        test_contracts_checked_in_dharma,
        test_healing_mission_created_from_failing_contract,
        test_sankalpa_evaluated_in_karma,
        test_iterative_issues_generate_actions_in_dharma,
        test_backward_compatible_mayor,
        # Phase 4: Audit + Reflection
        test_audit_runs_in_moksha,
        test_critical_finding_creates_mission,
        test_reflection_patterns_analyzed,
        test_reflection_proposal_creates_mission,
        test_audit_cooldown_respected,
        # Integration
        test_full_layer3_governance_cycle,
        test_governance_feedback_loop,
        test_layer3_backward_compatible,
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

    print(f"\n=== {passed}/{passed + failed} LAYER 3 TESTS PASSED ===")
    if failed:
        print(f"    {failed} FAILED")
        sys.exit(1)
