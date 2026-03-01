"""Issue-Driven Governance Tests — DHARMA→KARMA→MOKSHA lifecycle."""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_ctx(tmp, **kwargs):
    """Create a minimal PhaseContext for testing."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    bank = CivicBank(db_path=str(tmp / "economy.db"))
    pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
    gw = CityGateway()
    net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

    from city.phases import PhaseContext

    return PhaseContext(
        pokedex=pdx, gateway=gw, network=net,
        heartbeat_count=10, offline_mode=True,
        state_path=tmp / "state.json",
        **kwargs,
    )


# ── Mission Factory Tests ──────────────────────────────────────────


def test_create_issue_mission_intent_needed():
    """create_issue_mission with intent_needed creates MEDIUM priority mission."""
    from vibe_core.mahamantra.protocols.sankalpa.types import MissionPriority

    tmp = Path(tempfile.mkdtemp())
    try:
        # Mock sankalpa with a registry
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.missions import create_issue_mission
        mission_id = create_issue_mission(ctx, 42, "Fix bug", "intent_needed")

        assert mission_id == "issue_42_10"
        mock_sankalpa.registry.add_mission.assert_called_once()
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.name == "IssueHeal: #42"
        assert mission.priority == MissionPriority.MEDIUM
    finally:
        shutil.rmtree(tmp)


def test_create_issue_mission_audit_needed():
    """create_issue_mission with audit_needed creates HIGH priority mission."""
    from vibe_core.mahamantra.protocols.sankalpa.types import MissionPriority

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.missions import create_issue_mission
        mission_id = create_issue_mission(ctx, 7, "Audit contract", "audit_needed")

        assert mission_id == "issue_7_10"
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.name == "IssueAudit: #7"
        assert mission.priority == MissionPriority.HIGH
    finally:
        shutil.rmtree(tmp)


def test_create_issue_mission_no_sankalpa():
    """create_issue_mission returns None without sankalpa."""
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_ctx(tmp)  # no sankalpa
        from city.missions import create_issue_mission
        result = create_issue_mission(ctx, 1, "Test", "intent_needed")
        assert result is None
    finally:
        shutil.rmtree(tmp)


# ── DHARMA Parsing Tests ──────────────────────────────────────────


def test_dharma_process_issue_action_intent():
    """_process_issue_action parses intent_needed and creates mission."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.phases.dharma import _process_issue_action
        _process_issue_action(ctx, "intent_needed:#42:low_prana")

        mock_sankalpa.registry.add_mission.assert_called_once()
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.id == "issue_42_10"
    finally:
        shutil.rmtree(tmp)


def test_dharma_process_issue_action_contract_check():
    """_process_issue_action parses contract_check and creates audit mission."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.phases.dharma import _process_issue_action
        _process_issue_action(ctx, "contract_check:#7:audit_needed")

        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.name == "IssueAudit: #7"
    finally:
        shutil.rmtree(tmp)


def test_dharma_process_issue_action_ignores_informational():
    """_process_issue_action ignores ashrama/closed actions."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.phases.dharma import _process_issue_action
        _process_issue_action(ctx, "ashrama:#42:brahmachari")
        _process_issue_action(ctx, "closed:#42:prana_exhaustion")

        mock_sankalpa.registry.add_mission.assert_not_called()
    finally:
        shutil.rmtree(tmp)


def test_dharma_process_issue_action_malformed():
    """_process_issue_action handles malformed strings safely."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.phases.dharma import _process_issue_action
        # No crash on these
        _process_issue_action(ctx, "")
        _process_issue_action(ctx, "x")
        _process_issue_action(ctx, "intent_needed:noHash")
        _process_issue_action(ctx, "intent_needed:#notanumber:reason")

        mock_sankalpa.registry.add_mission.assert_not_called()
    finally:
        shutil.rmtree(tmp)


# ── KARMA Execution Tests ──────────────────────────────────────────


def test_karma_process_issue_audit_mission():
    """_process_issue_missions executes IssueAudit missions."""
    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_audit = MagicMock()
        mock_audit.run_all.return_value = 3

        mock_registry = MagicMock()
        mission = SankalpaMission(
            id="issue_42_10",
            name="IssueAudit: #42",
            description="test",
            priority=MissionPriority.HIGH,
            status=MissionStatus.ACTIVE,
            owner="mayor",
        )
        mock_registry.get_active_missions.return_value = [mission]

        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = mock_registry

        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa, audit=mock_audit)

        from city.phases.karma import _process_issue_missions
        operations: list[str] = []
        ctx.active_agents.add("test_agent")
        specs = {
            "test_agent": {
                "capability_tier": "verified",
                "capabilities": ["execute", "audit"],
            }
        }
        _process_issue_missions(ctx, operations, specs)

        assert any("issue_mission:issue_42_10:success" in op for op in operations)
        mock_audit.run_all.assert_called_once()
        assert mission.status == MissionStatus.COMPLETED
    finally:
        shutil.rmtree(tmp)


def test_karma_process_issue_heal_no_immune():
    """_process_issue_missions with no immune → pending."""
    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_registry = MagicMock()
        mission = SankalpaMission(
            id="issue_5_10",
            name="IssueHeal: #5",
            description="test",
            priority=MissionPriority.MEDIUM,
            status=MissionStatus.ACTIVE,
            owner="mayor",
        )
        mock_registry.get_active_missions.return_value = [mission]

        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = mock_registry

        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)  # no immune

        from city.phases.karma import _process_issue_missions
        operations: list[str] = []
        ctx.active_agents.add("test_agent")
        specs = {
            "test_agent": {
                "capability_tier": "verified",
                "capabilities": ["execute"],
            }
        }
        _process_issue_missions(ctx, operations, specs)

        assert any("issue_mission:issue_5_10:pending" in op for op in operations)
        # Should NOT be completed (no immune to heal)
        assert mission.status == MissionStatus.ACTIVE
    finally:
        shutil.rmtree(tmp)


def test_karma_skips_non_issue_missions():
    """_process_issue_missions ignores non-issue missions."""
    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_registry = MagicMock()
        mission = SankalpaMission(
            id="heal_ruff_clean_5",
            name="Heal: ruff_clean",
            description="not an issue mission",
            priority=MissionPriority.HIGH,
            status=MissionStatus.ACTIVE,
            owner="mayor",
        )
        mock_registry.get_active_missions.return_value = [mission]

        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = mock_registry

        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.phases.karma import _process_issue_missions
        operations: list[str] = []
        _process_issue_missions(ctx, operations, {})

        assert len(operations) == 0  # skipped
    finally:
        shutil.rmtree(tmp)


# ── Integration Test ──────────────────────────────────────────────


def test_mayor_full_rotation_with_issue_governance():
    """Mayor runs full MURALI rotation with issue governance wired."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from city.registry import SVC_ISSUES, CityServiceRegistry

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gw = CityGateway()
        net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

        # Mock issues manager (no gh CLI needed)
        mock_issues = MagicMock()
        mock_issues.metabolize_issues.return_value = []
        mock_issues.stats.return_value = {"tracked_issues": 0, "alive": 0, "dead": 0}

        reg = CityServiceRegistry()
        reg.register(SVC_ISSUES, mock_issues)

        mayor = Mayor(
            _pokedex=pdx, _gateway=gw, _network=net,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _registry=reg,
        )

        results = mayor.run_cycle(4)
        assert len(results) == 4
        # DHARMA should have called metabolize_issues
        dharma = results[1]
        assert dharma["department"] == "DHARMA"
    finally:
        shutil.rmtree(tmp)


# ── Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import unittest

    test_functions = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    suite = unittest.TestSuite()
    for fn in test_functions:
        suite.addTest(unittest.FunctionTestCase(fn))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
