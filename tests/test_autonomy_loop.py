"""Autonomy Loop Tests — Executor escalation, PR feedback, federation directives, identity, membrane protocol."""

import shutil
import sys
import tempfile
from dataclasses import dataclass
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


# ── Executor Escalation Tests ─────────────────────────────────────


def test_issue_heal_escalates_to_executor():
    """_execute_issue_heal escalates to executor when immune can't heal."""
    tmp = Path(tempfile.mkdtemp())
    try:
        # Immune fails
        mock_immune = MagicMock()
        mock_diagnosis = MagicMock()
        mock_diagnosis.healable = False
        mock_immune.diagnose.return_value = mock_diagnosis

        # Executor succeeds
        mock_executor = MagicMock()
        mock_fix = MagicMock()
        mock_fix.success = True
        mock_fix.files_changed = ["test.py"]
        mock_executor.execute_heal.return_value = mock_fix
        mock_executor.create_fix_pr.return_value = None  # no PR needed

        ctx = _make_ctx(tmp, immune=mock_immune, executor=mock_executor)

        from city.karma_handlers.sankalpa import _execute_issue_heal
        result = _execute_issue_heal(ctx, 42)

        assert result is True
        mock_executor.execute_heal.assert_called_once_with("ruff_clean", ["issue_42"])
    finally:
        shutil.rmtree(tmp)


def test_issue_heal_immune_succeeds_no_executor():
    """_execute_issue_heal returns True from immune without touching executor."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_immune = MagicMock()
        mock_diagnosis = MagicMock()
        mock_diagnosis.healable = True
        mock_immune.diagnose.return_value = mock_diagnosis
        mock_heal_result = MagicMock()
        mock_heal_result.success = True
        mock_immune.heal.return_value = mock_heal_result

        mock_executor = MagicMock()

        ctx = _make_ctx(tmp, immune=mock_immune, executor=mock_executor)

        from city.karma_handlers.sankalpa import _execute_issue_heal
        result = _execute_issue_heal(ctx, 5)

        assert result is True
        mock_executor.execute_heal.assert_not_called()
    finally:
        shutil.rmtree(tmp)


def test_issue_heal_creates_pr_and_records_event():
    """_execute_issue_heal records PR event in recent_events."""
    tmp = Path(tempfile.mkdtemp())
    try:
        # No immune
        mock_executor = MagicMock()
        mock_fix = MagicMock()
        mock_fix.success = True
        mock_fix.files_changed = ["fix.py"]
        mock_executor.execute_heal.return_value = mock_fix

        mock_pr = MagicMock()
        mock_pr.success = True
        mock_pr.pr_url = "https://github.com/test/pr/1"
        mock_pr.branch = "fix/ruff_clean_10"
        mock_pr.commit_hash = "abc123"
        mock_executor.create_fix_pr.return_value = mock_pr

        ctx = _make_ctx(tmp, executor=mock_executor)

        from city.karma_handlers.sankalpa import _execute_issue_heal
        result = _execute_issue_heal(ctx, 42)

        assert result is True
        assert len(ctx.recent_events) == 1
        event = ctx.recent_events[0]
        assert event["type"] == "pr_created"
        assert event["pr_url"] == "https://github.com/test/pr/1"
        assert event["issue_number"] == 42
    finally:
        shutil.rmtree(tmp)


def test_issue_heal_no_executor_no_immune():
    """_execute_issue_heal returns False without executor or immune."""
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_ctx(tmp)  # no immune, no executor

        from city.karma_handlers.sankalpa import _execute_issue_heal
        result = _execute_issue_heal(ctx, 99)

        assert result is False
    finally:
        shutil.rmtree(tmp)


# ── PR Feedback Tests ──────────────────────────────────────────────


def test_pr_results_collected_in_moksha():
    """_collect_pr_results extracts PR events from recent_events."""
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_ctx(tmp)
        ctx.recent_events.append({
            "type": "pr_created",
            "issue_number": 42,
            "pr_url": "https://github.com/test/pr/1",
            "branch": "fix/ruff_clean_10",
            "heartbeat": 10,
        })
        ctx.recent_events.append({
            "type": "other_event",
            "data": "ignored",
        })

        from city.phases.moksha import _collect_pr_results
        results = _collect_pr_results(ctx)

        assert len(results) == 1
        assert results[0]["pr_url"] == "https://github.com/test/pr/1"
        assert results[0]["issue_number"] == 42
    finally:
        shutil.rmtree(tmp)


def test_city_report_includes_pr_results():
    """CityReport dataclass accepts pr_results field."""
    from city.federation import CityReport

    report = CityReport(
        heartbeat=10, timestamp=1.0, population=5, alive=4, dead=1,
        elected_mayor="alice", council_seats=3, open_proposals=0,
        chain_valid=True, recent_actions=[], contract_status={},
        mission_results=[], directive_acks=[],
        pr_results=[{"pr_url": "https://github.com/test/pr/1", "branch": "fix/1"}],
    )
    d = report.to_dict()
    assert len(d["pr_results"]) == 1
    assert d["pr_results"][0]["pr_url"] == "https://github.com/test/pr/1"


def test_city_report_pr_results_default_empty():
    """CityReport pr_results defaults to empty list."""
    from city.federation import CityReport

    report = CityReport(
        heartbeat=1, timestamp=1.0, population=0, alive=0, dead=0,
        elected_mayor=None, council_seats=0, open_proposals=0,
        chain_valid=True, recent_actions=[], contract_status={},
        mission_results=[], directive_acks=[],
    )
    assert report.pr_results == []


def test_moltbook_bridge_formats_pr_results():
    """MoltbookBridge._format_content includes PR section."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_client = MagicMock()
        from city.moltbook_bridge import MoltbookBridge
        bridge = MoltbookBridge(_client=mock_client)

        data = {
            "heartbeat": 10,
            "population": 5,
            "alive": 4,
            "chain_valid": True,
            "pr_results": [
                {"pr_url": "https://github.com/test/pr/1", "branch": "fix/ruff_clean_10"},
            ],
        }
        content = bridge._format_content(data)
        assert "PRs created:" in content
        assert "fix/ruff_clean_10" in content
    finally:
        shutil.rmtree(tmp)


# ── Federation execute_code Tests ──────────────────────────────────


def test_execute_code_directive_creates_mission():
    """execute_code directive creates an execution mission."""
    from vibe_core.mahamantra.protocols.sankalpa.types import MissionPriority

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.missions import create_execution_mission

        @dataclass
        class FakeDirective:
            id: str = "dir_42"
            directive_type: str = "execute_code"
            params: dict = None
            timestamp: float = 1.0
            source: str = "mothership"

            def __post_init__(self):
                if self.params is None:
                    self.params = {"contract": "audit_clean", "source": "issue_7"}

        directive = FakeDirective()
        result = create_execution_mission(ctx, directive)

        assert result is True
        mock_sankalpa.registry.add_mission.assert_called_once()
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.id == "exec_dir_42_10"
        assert mission.name == "Execute: audit_clean"
        assert mission.priority == MissionPriority.HIGH
        assert mission.owner == "federation"
    finally:
        shutil.rmtree(tmp)


def test_execute_code_directive_in_genesis():
    """_execute_directive handles execute_code type."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        @dataclass
        class FakeDirective:
            id: str = "fed_99"
            directive_type: str = "execute_code"
            params: dict = None
            timestamp: float = 1.0
            source: str = "mothership"

            def __post_init__(self):
                if self.params is None:
                    self.params = {"contract": "ruff_clean"}

        from city.hooks.genesis.federation import _execute_directive
        result = _execute_directive(ctx, FakeDirective())

        assert result is True
        mock_sankalpa.registry.add_mission.assert_called_once()
    finally:
        shutil.rmtree(tmp)


def test_exec_mission_processed_in_karma():
    """_process_issue_missions handles exec_ prefix missions."""
    from vibe_core.mahamantra.protocols.sankalpa.types import (
        MissionPriority,
        MissionStatus,
        SankalpaMission,
    )

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_executor = MagicMock()
        mock_fix = MagicMock()
        mock_fix.success = True
        mock_fix.files_changed = ["fixed.py"]
        mock_executor.execute_heal.return_value = mock_fix
        mock_executor.create_fix_pr.return_value = None

        mock_registry = MagicMock()
        mission = SankalpaMission(
            id="exec_dir_42_10",
            name="Execute: ruff_clean",
            description="Federation directive: ruff_clean",
            priority=MissionPriority.HIGH,
            status=MissionStatus.ACTIVE,
            owner="federation",
        )
        mock_registry.get_active_missions.return_value = [mission]

        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = mock_registry

        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa, executor=mock_executor)

        from city.karma_handlers.sankalpa import _process_issue_missions
        from city.karma_handlers.gateway import _get_all_specs, _get_all_inventories
        operations: list[str] = []
        all_specs = _get_all_specs(ctx)
        all_inventories = _get_all_inventories(ctx)
        _process_issue_missions(ctx, operations, all_specs, all_inventories)

        assert any("exec_mission:exec_dir_42_10:success" in op for op in operations)
        mock_executor.execute_heal.assert_called_once()
        assert mission.status == MissionStatus.COMPLETED
    finally:
        shutil.rmtree(tmp)


# ── Identity Tests ─────────────────────────────────────────────────


def test_pokedex_stores_fingerprint_at_registration():
    """Pokedex.register() stores ECDSA fingerprint."""
    tmp = Path(tempfile.mkdtemp())
    try:
        from vibe_core.cartridges.system.civic.tools.economy import CivicBank
        from city.pokedex import Pokedex

        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)

        agent = pdx.register("test_agent_alpha")
        assert agent["identity"] is not None
        assert len(agent["identity"]["fingerprint"]) == 16  # SHA-256 hex, first 16
        assert "BEGIN PUBLIC KEY" in agent["identity"]["public_key"]
    finally:
        shutil.rmtree(tmp)


def test_pokedex_verify_identity():
    """Pokedex.verify_identity() validates signed payloads."""
    tmp = Path(tempfile.mkdtemp())
    try:
        from vibe_core.cartridges.system.civic.tools.economy import CivicBank
        from city.pokedex import Pokedex
        from city.identity import generate_identity
        from city.jiva import derive_jiva

        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)

        pdx.register("test_signer")

        # Sign with the agent's identity
        jiva = derive_jiva("test_signer")
        identity = generate_identity(jiva)
        payload = b"hello world"
        signature = identity.sign(payload)

        # Verify through Pokedex
        assert pdx.verify_identity("test_signer", payload, signature) is True
        assert pdx.verify_identity("test_signer", b"tampered", signature) is False
        assert pdx.verify_identity("nonexistent", payload, signature) is False
    finally:
        shutil.rmtree(tmp)


def test_identity_registry_constant():
    """SVC_IDENTITY constant exists in registry."""
    from city.registry import SVC_IDENTITY
    assert SVC_IDENTITY == "identity"


def test_phase_context_identity_property():
    """PhaseContext.identity property delegates to registry."""
    tmp = Path(tempfile.mkdtemp())
    try:
        from city.registry import SVC_IDENTITY, CityServiceRegistry

        mock_identity = MagicMock()
        registry = CityServiceRegistry()
        registry.register(SVC_IDENTITY, mock_identity)

        ctx = _make_ctx(tmp, registry=registry)
        assert ctx.identity is mock_identity

        # Without identity registered
        ctx2 = _make_ctx(tmp)
        assert ctx2.identity is None
    finally:
        shutil.rmtree(tmp)


# ── Membrane Protocol Tests ───────────────────────────────────────


def test_signal_prefix_structured_priority():
    """[Signal] prefix posts get structured=True and insert at front of signals list."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_client = MagicMock()
        # Two posts: normal first, then [Signal] prefix
        mock_client.sync_get_personalized_feed.return_value = [
            {
                "id": "post_normal",
                "submolt": {"name": "agent-city"},
                "author": {"username": "alice"},
                "title": "Some discussion about a bug fix",
                "content": "This needs a fix",
            },
            {
                "id": "post_signal",
                "submolt": {"name": "agent-city"},
                "author": {"username": "bob"},
                "title": "[Signal] fix — ruff regression in parser",
                "content": "Details about the regression",
            },
        ]
        mock_client.sync_comment_with_verification = MagicMock()

        from city.moltbook_bridge import MoltbookBridge
        bridge = MoltbookBridge(_client=mock_client)

        signals = bridge.scan_submolt(limit=20)

        assert len(signals) == 2
        # [Signal] post should be at front (priority)
        assert signals[0]["structured"] is True
        assert signals[0]["source"] == "submolt_signal"
        assert signals[0]["author"] == "bob"
        # Normal post at back
        assert signals[1]["structured"] is False
        assert signals[1]["source"] == "submolt"
    finally:
        shutil.rmtree(tmp)


def test_acknowledge_post_includes_mission_id():
    """_acknowledge_post returns mission_id and includes it in comment."""
    mock_client = MagicMock()
    from city.moltbook_bridge import MoltbookBridge
    bridge = MoltbookBridge(_client=mock_client)

    mission_id = bridge._acknowledge_post("post_abc12345", {"fix", "test"}, "alice")

    assert mission_id == "signal_fix_test_post_abc"
    mock_client.sync_comment_with_verification.assert_called_once()
    comment = mock_client.sync_comment_with_verification.call_args[0][1]
    assert "signal_fix_test_post_abc" in comment
    assert "Mission created:" in comment


def test_create_signal_mission_structured():
    """create_signal_mission creates HIGH priority mission for structured signals."""
    from vibe_core.mahamantra.protocols.sankalpa.types import MissionPriority

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.missions import create_signal_mission
        mission_id = create_signal_mission(
            ctx,
            signal_keywords=["fix", "test"],
            post_id="post_abc12345",
            author="alice",
            title="[Signal] fix — test regression",
            structured=True,
        )

        assert mission_id == "signal_fix_test_post_abc"
        mock_sankalpa.registry.add_mission.assert_called_once()
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.priority == MissionPriority.HIGH
        assert mission.owner == "submolt"
    finally:
        shutil.rmtree(tmp)


def test_create_signal_mission_unstructured():
    """create_signal_mission creates MEDIUM priority mission for normal word-match signals."""
    from vibe_core.mahamantra.protocols.sankalpa.types import MissionPriority

    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.missions import create_signal_mission
        mission_id = create_signal_mission(
            ctx,
            signal_keywords=["bug"],
            post_id="post_xyz98765",
            author="bob",
            title="Found a bug in the API",
            structured=False,
        )

        assert mission_id == "signal_bug_post_xyz"
        mock_sankalpa.registry.add_mission.assert_called_once()
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.priority == MissionPriority.MEDIUM
        assert mission.owner == "submolt"
    finally:
        shutil.rmtree(tmp)


def test_create_signal_mission_no_sankalpa():
    """create_signal_mission returns None when sankalpa not available."""
    tmp = Path(tempfile.mkdtemp())
    try:
        ctx = _make_ctx(tmp)  # no sankalpa

        from city.missions import create_signal_mission
        result = create_signal_mission(
            ctx, signal_keywords=["fix"], post_id="abc", author="x", title="y",
        )
        assert result is None
    finally:
        shutil.rmtree(tmp)


def test_genesis_creates_signal_missions():
    """Genesis _create_signal_mission delegates to missions.create_signal_mission."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = MagicMock()
        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa)

        from city.missions import create_signal_mission
        mission_id = create_signal_mission(
            ctx,
            signal_keywords=["deploy", "api"],
            post_id="post_fed12345",
            author="steward",
            title="[Signal] deploy — new api endpoint",
            structured=True,
        )

        assert mission_id is not None
        assert mission_id.startswith("signal_deploy_api")
        mock_sankalpa.registry.add_mission.assert_called_once()
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
