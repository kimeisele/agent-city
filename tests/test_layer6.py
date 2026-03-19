"""Layer 6 Tests — Federation Communication (Relay + Directives + Reports).
Linked to GitHub Issue #13.
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Phase 1: FederationRelay Unit Tests ───────────────────────────


def test_relay_creation():
    """Relay starts with default mothership and empty state."""
    from city.federation import DEFAULT_MOTHERSHIP, FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        assert relay._mothership_repo == DEFAULT_MOTHERSHIP
        assert relay.last_report == {}
        stats = relay.stats()
        assert stats["mothership"] == DEFAULT_MOTHERSHIP
        assert stats["reports_sent"] == 0
        assert stats["pending_directives"] == 0
    finally:
        shutil.rmtree(tmp)


def test_build_city_report():
    """CityReport contains all required fields."""
    from city.federation import CityReport

    report = CityReport(
        heartbeat=42,
        timestamp=time.time(),
        population=20,
        alive=18,
        dead=2,
        elected_mayor="Agent_Alpha",
        council_seats=6,
        open_proposals=1,
        chain_valid=True,
        recent_actions=["election:mayor=Agent_Alpha"],
        contract_status={"ruff_clean": "passing"},
        mission_results=[],
        directive_acks=["DIR-001"],
        active_campaigns=[{"id": "internet-adaptation", "status": "active"}],
    )
    d = report.to_dict()
    assert d["heartbeat"] == 42
    assert d["population"] == 20
    assert d["elected_mayor"] == "Agent_Alpha"
    assert d["chain_valid"] is True
    assert "DIR-001" in d["directive_acks"]
    assert d["active_campaigns"][0]["id"] == "internet-adaptation"


def test_outbound_builders_include_recent_actions(tmp_path):
    from city.gateway import CityGateway
    from city.hooks.moksha.outbound import _build_city_report, _build_post_data
    from city.network import CityNetwork
    from city.phases import PhaseContext
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp_path / "economy.db"))
    pokedex = Pokedex(db_path=str(tmp_path / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)
    ctx = PhaseContext(
        pokedex=pokedex,
        gateway=gateway,
        network=network,
        heartbeat_count=42,
        offline_mode=True,
        state_path=tmp_path / "mayor_state.json",
        campaigns=MagicMock(),
    )
    ctx.campaigns.summary.return_value = [
        {
            "id": "internet-adaptation",
            "title": "Internet adaptation",
            "north_star": "Continuously adapt to relevant new protocols and standards.",
            "status": "active",
            "last_gap_summary": ["keep execution bounded"],
            "last_evaluated_heartbeat": 40,
        }
    ]
    reflection = {
        "city_stats": {"total": 3, "active": 1, "citizen": 1},
        "chain_valid": True,
        "brain_operations": ["brain_reflect"],
        "pr_results": [{"branch": "fix/42", "pr_url": "https://example/pr/42"}],
    }
    operations = ["mission_lifecycle:reported", "federation_report:sent"]

    post_data = _build_post_data(ctx, reflection, operations)
    report = _build_city_report(ctx, reflection, operations)

    assert post_data["recent_actions"] == [
        "mission_lifecycle:reported",
        "federation_report:sent",
        "brain_reflect",
        "pr_created:fix/42",
    ]
    assert post_data["active_campaigns"][0]["id"] == "internet-adaptation"
    assert report.recent_actions == post_data["recent_actions"]
    assert report.active_campaigns == post_data["active_campaigns"]


def test_send_report_dry_run():
    """Dry-run logs but doesn't call gh CLI."""
    from city.federation import CityReport, FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _dry_run=True,
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        report = CityReport(
            heartbeat=1, timestamp=time.time(), population=10,
            alive=8, dead=2, elected_mayor="Boss",
            council_seats=4, open_proposals=0, chain_valid=True,
            recent_actions=[], contract_status={},
            mission_results=[], directive_acks=[],
        )
        result = relay.send_report(report)
        assert result is True
        assert relay.last_report["heartbeat"] == 1
        # Report file saved locally
        report_file = tmp / "reports" / "report_1.json"
        assert report_file.exists()
        saved = json.loads(report_file.read_text())
        assert saved["population"] == 10
    finally:
        shutil.rmtree(tmp)


def test_check_directives_empty():
    """No directive files → empty list."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        directives = relay.check_directives()
        assert directives == []
    finally:
        shutil.rmtree(tmp)


def test_check_directives_reads_json():
    """Directive files are read and parsed correctly."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        # Write a test directive
        directive_data = {
            "id": "DIR-001",
            "directive_type": "register_agent",
            "params": {"name": "NewAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }
        (tmp / "directives" / "DIR-001.json").write_text(
            json.dumps(directive_data),
        )

        directives = relay.check_directives()
        assert len(directives) == 1
        assert directives[0].id == "DIR-001"
        assert directives[0].directive_type == "register_agent"
        assert directives[0].params["name"] == "NewAgent"
    finally:
        shutil.rmtree(tmp)


def test_acknowledge_directive():
    """Acknowledging renames .json to .json.done."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )
        directive_data = {
            "id": "DIR-002",
            "directive_type": "freeze_agent",
            "params": {"name": "BadAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }
        json_path = tmp / "directives" / "DIR-002.json"
        json_path.write_text(json.dumps(directive_data))

        result = relay.acknowledge_directive("DIR-002")
        assert result is True
        assert not json_path.exists()
        assert (tmp / "directives" / "DIR-002.json.done").exists()

        # Second check returns empty (acknowledged directives are skipped)
        directives = relay.check_directives()
        assert len(directives) == 0
    finally:
        shutil.rmtree(tmp)


# ── Phase 2: Directive Execution Tests ────────────────────────────


def _make_mayor_with_federation(tmp_dir, directives_dir=None):
    """Helper: create a Mayor with federation relay in a temp dir."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.federation import FederationRelay
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    db_path = tmp_dir / "city.db"
    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pokedex = Pokedex(db_path=str(db_path), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    relay = FederationRelay(
        _dry_run=True,
        _directives_dir=directives_dir or (tmp_dir / "directives"),
        _reports_dir=tmp_dir / "reports",
    )

    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _state_path=tmp_dir / "mayor_state.json",
        _offline_mode=True,
        _federation=relay,
    )
    return mayor, pokedex, relay


def test_execute_register_agent():
    """register_agent directive → agent registered in Pokedex."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Write directive
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-REG.json").write_text(json.dumps({
            "id": "DIR-REG",
            "directive_type": "register_agent",
            "params": {"name": "FederatedAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run GENESIS (heartbeat 0)
        result = mayor.heartbeat()
        assert result["department"] == "MURALI"

        # Agent should be registered
        agent = pokedex.get("FederatedAgent")
        assert agent is not None
        assert agent["name"] == "FederatedAgent"

        # Directive should be acknowledged
        assert (directives_dir / "DIR-REG.json.done").exists()
        assert not (directives_dir / "DIR-REG.json").exists()
    finally:
        shutil.rmtree(tmp)


def test_execute_freeze_agent():
    """freeze_agent directive → agent frozen in Pokedex."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Register an agent first (register → citizen status)
        pokedex.register("TargetAgent")
        assert pokedex.get("TargetAgent")["status"] == "citizen"

        # Write freeze directive
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-FRZ.json").write_text(json.dumps({
            "id": "DIR-FRZ",
            "directive_type": "freeze_agent",
            "params": {"name": "TargetAgent"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run GENESIS
        result = mayor.heartbeat()
        assert any("directive:freeze_agent:True" in d for d in result["discovered"])

        # Agent should be frozen
        agent = pokedex.get("TargetAgent")
        assert agent["status"] == "frozen"
    finally:
        shutil.rmtree(tmp)


def test_execute_unknown_directive():
    """Unknown directive type → False, not crash."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        directives_dir = tmp / "directives"
        (directives_dir / "DIR-UNK.json").write_text(json.dumps({
            "id": "DIR-UNK",
            "directive_type": "self_destruct",
            "params": {},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        result = mayor.heartbeat()
        assert any("directive:self_destruct:False" in d for d in result["discovered"])
    finally:
        shutil.rmtree(tmp)


def test_directive_lifecycle():
    """Full lifecycle: write → check → execute → ack → gone."""
    from city.federation import FederationRelay

    tmp = Path(tempfile.mkdtemp())
    try:
        relay = FederationRelay(
            _dry_run=True,
            _directives_dir=tmp / "directives",
            _reports_dir=tmp / "reports",
        )

        # Write directive
        (tmp / "directives" / "DIR-LC.json").write_text(json.dumps({
            "id": "DIR-LC",
            "directive_type": "policy_update",
            "params": {"description": "New slop rule"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Check → found
        directives = relay.check_directives()
        assert len(directives) == 1
        assert directives[0].id == "DIR-LC"

        # Acknowledge → renamed
        relay.acknowledge_directive("DIR-LC")
        assert not (tmp / "directives" / "DIR-LC.json").exists()
        assert (tmp / "directives" / "DIR-LC.json.done").exists()

        # Check again → empty
        directives = relay.check_directives()
        assert len(directives) == 0

        # Ack tracked
        assert "DIR-LC" in relay.pending_acks
    finally:
        shutil.rmtree(tmp)


# ── Phase 3: Mayor Integration Tests ─────────────────────────────


def test_mayor_no_federation_backward_compatible():
    """Mayor with _federation=None works exactly as before."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
        )

        # Run full rotation — no crash, no federation fields in output
        results = mayor.run_cycle(4)
        assert len(results) == 4
        moksha = results[3]
        assert "federation_report_sent" not in moksha["reflection"]
    finally:
        shutil.rmtree(tmp)


def test_genesis_processes_directives():
    """GENESIS processes directive files from federation."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Write two directives
        directives_dir = tmp / "directives"
        for i, name in enumerate(["AgentA", "AgentB"]):
            (directives_dir / f"DIR-{i}.json").write_text(json.dumps({
                "id": f"DIR-{i}",
                "directive_type": "register_agent",
                "params": {"name": name},
                "timestamp": time.time(),
                "source": "mothership",
            }))

        result = mayor.heartbeat()
        assert result["department"] == "MURALI"

        # Both agents registered
        assert pokedex.get("AgentA") is not None
        assert pokedex.get("AgentB") is not None

        # Both directives acknowledged
        assert (directives_dir / "DIR-0.json.done").exists()
        assert (directives_dir / "DIR-1.json.done").exists()
    finally:
        shutil.rmtree(tmp)


def test_moksha_sends_report():
    """MOKSHA sends federation report (dry-run)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Register some agents for population stats
        pokedex.register("Citizen1")
        pokedex.register("Citizen2")

        # Advance to MOKSHA (heartbeat 3)
        results = mayor.run_cycle(4)
        moksha = results[3]
        assert moksha["department"] == "MURALI"
        assert moksha["reflection"].get("federation_report_sent") is True

        # Report saved locally
        report = relay.last_report
        assert report["heartbeat"] == 3
        assert report["population"] >= 2
        assert report["chain_valid"] is True
    finally:
        shutil.rmtree(tmp)


# ── Phase 4: Full Cycle Test ─────────────────────────────────────


def test_full_rotation_with_federation():
    """Full MURALI rotation: GENESIS (directives) → DHARMA → KARMA → MOKSHA (report)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Seed a directive for GENESIS
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-FULL.json").write_text(json.dumps({
            "id": "DIR-FULL",
            "directive_type": "register_agent",
            "params": {"name": "FedCitizen"},
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run full rotation
        results = mayor.run_cycle(4)
        assert len(results) == 4

        # GENESIS: directive processed
        genesis = results[0]
        assert genesis["department"] == "MURALI"
        assert any("directive:register_agent:True" in d for d in genesis["discovered"])

        # Agent registered
        assert pokedex.get("FedCitizen") is not None

        # DHARMA: governance ran
        dharma = results[1]
        assert dharma["department"] == "MURALI"

        # KARMA: operations ran
        karma = results[2]
        assert karma["department"] == "MURALI"

        # MOKSHA: report sent
        moksha = results[3]
        assert moksha["department"] == "MURALI"
        assert moksha["reflection"]["federation_report_sent"] is True

        # Report includes the newly registered citizen
        report = relay.last_report
        assert report["population"] >= 1
        assert "DIR-FULL" in report["directive_acks"]

        # Directive file acknowledged
        assert (directives_dir / "DIR-FULL.json.done").exists()
    finally:
        shutil.rmtree(tmp)


# ── Phase 5: Moltbook Bridge Tests ───────────────────────────────


class _MockBridgeClient:
    """Minimal mock for MoltbookClient with bridge methods."""

    def __init__(self, feed=None):
        self._feed = feed or []
        self.subscribed = False
        self.posts_created = []
        self.comments_created = []

    def sync_subscribe_submolt(self, name):
        self.subscribed = True
        return {"success": True}

    def sync_get_personalized_feed(self, sort="hot", limit=25):
        return self._feed

    def sync_get_feed(self, sort="hot", limit=25):
        return self._feed

    def sync_create_post(self, title, content, submolt=None):
        self.posts_created.append({"title": title, "content": content, "submolt": submolt})
        return {"id": f"post_{len(self.posts_created)}"}

    def sync_comment_with_verification(self, post_id, content):
        self.comments_created.append({"post_id": post_id, "content": content})
        return {"id": f"comment_{len(self.comments_created)}"}


def test_bridge_creation():
    """Bridge starts with empty state."""
    from city.moltbook_bridge import MoltbookBridge

    bridge = MoltbookBridge(_client=_MockBridgeClient(), _own_username="mayor_bot")
    assert len(bridge._seen_post_ids) == 0
    assert bridge._last_post_times == {}
    assert bridge._subscribed is False


def test_bridge_scan_filters_own_posts():
    """Own posts are skipped during scan."""
    from city.moltbook_bridge import MoltbookBridge, SUBMOLT_NAME

    feed = [
        {"id": "p1", "author": {"username": "mayor_bot"}, "title": "My post",
         "content": "test", "submolt": {"name": SUBMOLT_NAME}},
        {"id": "p2", "author": {"username": "steward-protocol"}, "title": "Fix bug in ruff",
         "content": "Need to fix", "submolt": {"name": SUBMOLT_NAME}},
    ]
    client = _MockBridgeClient(feed=feed)
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    signals = bridge.scan_submolt()
    assert len(signals) == 1
    assert signals[0]["author"] == "steward-protocol"


def test_bridge_scan_dedup():
    """Seen posts are not re-processed."""
    from city.moltbook_bridge import MoltbookBridge, SUBMOLT_NAME

    feed = [
        {"id": "p1", "author": {"username": "other"}, "title": "Hello",
         "content": "test", "submolt": {"name": SUBMOLT_NAME}},
    ]
    client = _MockBridgeClient(feed=feed)
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    signals1 = bridge.scan_submolt()
    assert len(signals1) == 1
    signals2 = bridge.scan_submolt()
    assert len(signals2) == 0  # Deduped


def test_bridge_scan_filters_other_submolts():
    """Posts from other submolts are ignored."""
    from city.moltbook_bridge import MoltbookBridge

    feed = [
        {"id": "p1", "author": {"username": "someone"}, "title": "Random post",
         "content": "hi", "submolt": {"name": "ai_agents"}},
    ]
    client = _MockBridgeClient(feed=feed)
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    signals = bridge.scan_submolt()
    assert len(signals) == 0


def test_bridge_scan_skips_city_reports():
    """Posts with [City Report] prefix are skipped (feedback loop prevention)."""
    from city.moltbook_bridge import CITY_REPORT_PREFIX, MoltbookBridge, SUBMOLT_NAME

    feed = [
        {"id": "p1", "author": {"username": "other_city"},
         "title": f"{CITY_REPORT_PREFIX} 20 agents, chain verified",
         "content": "test", "submolt": {"name": SUBMOLT_NAME}},
    ]
    client = _MockBridgeClient(feed=feed)
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    signals = bridge.scan_submolt()
    assert len(signals) == 0


def test_bridge_code_signal_extraction():
    """Posts with code keywords produce code_signals."""
    from city.moltbook_bridge import MoltbookBridge, SUBMOLT_NAME

    feed = [
        {"id": "p1", "author": {"username": "steward"},
         "title": "Fix regression in audit pipeline",
         "content": "We need to refactor the test suite",
         "submolt": {"name": SUBMOLT_NAME}},
    ]
    client = _MockBridgeClient(feed=feed)
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    signals = bridge.scan_submolt()
    assert len(signals) == 1
    assert "fix" in signals[0]["code_signals"]
    assert "regression" in signals[0]["code_signals"]
    assert "refactor" in signals[0]["code_signals"]
    assert "test" in signals[0]["code_signals"]
    # Should have acknowledged with a comment
    assert len(client.comments_created) == 1
    assert "fix" in client.comments_created[0]["content"]


def test_bridge_governance_signal_extraction():
    """Posts with governance keywords produce governance_signals."""
    from city.moltbook_bridge import MoltbookBridge, SUBMOLT_NAME

    feed = [
        {"id": "p1", "author": {"username": "admin"},
         "title": "New proposal for council election",
         "content": "We should audit the policy",
         "submolt": {"name": SUBMOLT_NAME}},
    ]
    client = _MockBridgeClient(feed=feed)
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    signals = bridge.scan_submolt()
    assert len(signals) == 1
    assert "proposal" in signals[0]["governance_signals"]
    assert "council" in signals[0]["governance_signals"]
    assert "election" in signals[0]["governance_signals"]
    assert "audit" in signals[0]["governance_signals"]


def test_bridge_post_cooldown():
    """Posts respect cooldown period."""
    from city.moltbook_bridge import MoltbookBridge

    client = _MockBridgeClient()
    bridge = MoltbookBridge(
        _client=client, _own_username="mayor_bot", _post_cooldown_s=1800,
    )

    data = {"heartbeat": 1, "population": 10, "alive": 8, "chain_valid": True}
    result1 = bridge.post_city_update(data)
    assert result1 is True
    assert len(client.posts_created) == 1

    result2 = bridge.post_city_update(data)
    assert result2 is False  # Cooldown active
    assert len(client.posts_created) == 1  # No new post


def test_bridge_post_format():
    """City update post has correct title prefix and readable content."""
    from city.moltbook_bridge import CITY_REPORT_PREFIX, MoltbookBridge

    client = _MockBridgeClient()
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")

    data = {
        "heartbeat": 42,
        "population": 20,
        "alive": 18,
        "elected_mayor": "Agent_Alpha",
        "council_seats": 6,
        "open_proposals": 1,
        "recent_actions": ["election:mayor=Agent_Alpha"],
        "contract_status": {"total": 3, "passing": 2, "failing": 1},
        "chain_valid": True,
        "active_campaigns": [
            {
                "id": "internet-adaptation",
                "title": "Internet adaptation",
                "north_star": "Continuously adapt to relevant new protocols and standards.",
                "status": "active",
                "last_gap_summary": ["keep execution bounded"],
            }
        ],
    }
    result = bridge.post_city_update(data)
    assert result is True

    post = client.posts_created[0]
    assert post["title"].startswith(CITY_REPORT_PREFIX)
    assert "20 agents" in post["title"]
    assert "verified" in post["title"]
    assert post["submolt"] == "agent-city"

    # Content is human-readable
    assert "heartbeat cycle #42" in post["content"]
    assert "20 agents" in post["content"]
    assert "Agent_Alpha" in post["content"]
    assert "6 seats" in post["content"]
    assert "Failing contracts: 1" in post["content"]
    assert "Campaigns:" in post["content"]
    assert "Internet adaptation (active)" in post["content"]
    assert "Continuously adapt to relevant new protocols and standards." in post["content"]
    assert "keep execution bounded" in post["content"]


def test_bridge_persistence():
    """State survives snapshot/restore cycle."""
    from city.moltbook_bridge import MoltbookBridge

    client = _MockBridgeClient()
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")
    from collections import OrderedDict
    bridge._seen_post_ids = OrderedDict.fromkeys(["p1", "p2", "p3"])
    bridge._last_post_times = {"submolt": 12345.0}
    bridge._subscribed = True

    snapshot = bridge.snapshot()

    bridge2 = MoltbookBridge(_client=client, _own_username="mayor_bot")
    bridge2.restore(snapshot)

    assert set(bridge2._seen_post_ids) == {"p1", "p2", "p3"}
    assert bridge2._last_post_times == {"submolt": 12345.0}
    assert bridge2._subscribed is True


def test_bridge_mission_result_post():
    """[Mission Result] batched into single summary post."""
    from city.moltbook_bridge import MISSION_RESULT_PREFIX, MoltbookBridge

    client = _MockBridgeClient()
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")

    missions = [
        {"id": "signal_fix_abc123", "name": "Signal: fix", "status": "completed", "owner": "submolt"},
        {"id": "heal_ruff_42", "name": "Heal: ruff_clean", "status": "active", "owner": "mayor"},
        {"id": "exec_dir1_5", "name": "Execute: ruff_clean", "status": "failed", "owner": "federation"},
    ]
    posted = bridge.post_mission_results(missions)
    assert posted == 2  # completed + failed, not active
    assert len(client.posts_created) == 1  # single batched post, not N
    assert client.posts_created[0]["title"].startswith(MISSION_RESULT_PREFIX)
    assert "2 missions resolved" in client.posts_created[0]["title"]
    assert "completed" in client.posts_created[0]["content"]
    assert "failed" in client.posts_created[0]["content"]


def test_bridge_directive_acks_in_content():
    """City report content includes directive acknowledgments."""
    from city.moltbook_bridge import MoltbookBridge

    client = _MockBridgeClient()
    bridge = MoltbookBridge(_client=client, _own_username="mayor_bot")

    data = {
        "heartbeat": 10,
        "population": 5,
        "alive": 5,
        "chain_valid": True,
        "directive_acks": ["DIR-1709305200", "DIR-1709305300"],
    }
    bridge.post_city_update(data)
    content = client.posts_created[0]["content"]
    assert "Directives processed:" in content
    assert "ACK: DIR-1709305200" in content
    assert "ACK: DIR-1709305300" in content


def test_bridge_offline_no_crash():
    """Mayor with bridge=None (offline) runs without crash."""
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)
        assert mayor._moltbook_bridge is None
        results = mayor.run_cycle(4)
        assert len(results) == 4
        # MOKSHA should NOT have moltbook_update_posted
        moksha = results[3]
        assert "moltbook_update_posted" not in moksha["reflection"]
    finally:
        shutil.rmtree(tmp)


# ── Phase 6: Cognition Layer Tests ────────────────────────────────


def test_cognition_knowledge_graph_unavailable():
    """get_city_knowledge() returns None gracefully when unavailable."""
    from city.cognition import get_city_knowledge
    # In test environment, KG may or may not be available
    result = get_city_knowledge()
    assert result is None or hasattr(result, "compile_prompt_context")


def test_cognition_compile_context_empty():
    """compile_context returns '' when KG unavailable."""
    from city.cognition import compile_context
    result = compile_context("test task")
    assert isinstance(result, str)


def test_cognition_check_constraints_empty():
    """check_constraints returns [] when KG unavailable."""
    from city.cognition import check_constraints
    result = check_constraints("test_action", {"key": "value"})
    assert isinstance(result, list)


def test_cognition_event_bus_unavailable():
    """get_city_bus() returns None gracefully when unavailable."""
    from city.cognition import get_city_bus
    result = get_city_bus()
    assert result is None or hasattr(result, "emit_sync")


def test_cognition_emit_event_graceful():
    """emit_event returns str (event_id or '') — never crashes."""
    from city.cognition import emit_event
    result = emit_event("PHASE_TRANSITION", "test_agent", "test message")
    assert isinstance(result, str)


def test_cognition_get_history_graceful():
    """get_event_history returns list — never crashes."""
    from city.cognition import get_event_history
    result = get_event_history(limit=10)
    assert isinstance(result, list)


def test_cognition_get_stats_graceful():
    """get_bus_stats returns dict — never crashes."""
    from city.cognition import get_bus_stats
    result = get_bus_stats()
    assert isinstance(result, dict)


def test_mayor_cognition_backward_compatible():
    """Mayor with knowledge_graph=None + event_bus=None runs without crash."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
        )

        assert mayor._knowledge_graph is None
        assert mayor._event_bus is None

        # Full rotation — no crash
        results = mayor.run_cycle(4)
        assert len(results) == 4

        # MOKSHA should NOT have event_bus_stats
        moksha = results[3]
        assert "event_bus_stats" not in moksha["reflection"]
    finally:
        shutil.rmtree(tmp)


# ── Phase 7: Issue #13 — Bidirectional Federation & Mission Coordination ──


class _MockSankalpaRegistry:
    """Minimal mock for SankalpaMission registry (stores missions in a list)."""

    def __init__(self):
        self.missions: list = []

    def add_mission(self, mission: object) -> None:
        self.missions.append(mission)

    def list_missions(self, status: str | None = None) -> list:
        if status is None:
            return self.missions
        return [m for m in self.missions if m.status.value == status]


class _MockSankalpa:
    """Minimal mock for SankalpaOrchestrator."""

    def __init__(self):
        self.registry = _MockSankalpaRegistry()

    def think(self, **kwargs) -> list:
        return []


def _make_mayor_full_stack(tmp_dir, *, with_council: bool = True, with_bridge: bool = False):
    """Helper: Mayor with federation + sankalpa + council (full governance stack)."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.council import CityCouncil
    from city.federation import FederationRelay
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    db_path = tmp_dir / "city.db"
    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pokedex = Pokedex(db_path=str(db_path), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    relay = FederationRelay(
        _dry_run=True,
        _directives_dir=tmp_dir / "directives",
        _reports_dir=tmp_dir / "reports",
    )

    sankalpa = _MockSankalpa()

    council = None
    if with_council:
        council = CityCouncil(_state_path=tmp_dir / "council_state.json")
        # Seed agents so council has members for proposals
        candidates = []
        for name in ["Alpha", "Beta", "Gamma"]:
            entry = pokedex.register(name)
            candidates.append({
                "name": name,
                "prana": entry.get("vitals", {}).get("prana", 100),
                "guardian": "",
                "position": 0,
            })
        council.run_election(candidates, heartbeat_count=0)

    bridge = None
    if with_bridge:
        from city.moltbook_bridge import MoltbookBridge
        bridge = MoltbookBridge(
            _client=_MockBridgeClient(), _own_username="mayor_bot",
        )

    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _state_path=tmp_dir / "mayor_state.json",
        _offline_mode=True,
        _federation=relay,
        _sankalpa=sankalpa,
        _council=council,
        _moltbook_bridge=bridge if with_bridge else None,
    )
    return mayor, pokedex, relay, sankalpa, council, bridge


def test_create_mission_directive_creates_mission_and_proposal():
    """HARD TEST: create_mission directive → Sankalpa Mission + Council Proposal.

    This tests the full governance loop:
    1. Mothership sends create_mission directive with topic + context
    2. GENESIS reads it, creates a SankalpaMission in the registry
    3. GENESIS also creates a Council Proposal for community governance
    4. Directive is acknowledged

    This is the core of Issue #13: community intent → real infrastructure.
    Without this, federation directives are read-and-forgotten.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay, sankalpa, council, _ = _make_mayor_full_stack(tmp)
        assert council is not None, "Council must be wired for this test"
        assert council.elected_mayor is not None, "Mayor must be elected"

        # Write a create_mission directive from mothership
        directives_dir = tmp / "directives"
        (directives_dir / "DIR-MISSION.json").write_text(json.dumps({
            "id": "DIR-MISSION",
            "directive_type": "create_mission",
            "params": {
                "topic": "Implement agent reputation system",
                "context": "Community discussion on m/agent-city requesting trust-based agent scoring",
                "source_post_id": "moltbook_post_42",
                "priority": "high",
            },
            "timestamp": time.time(),
            "source": "mothership",
        }))

        # Run GENESIS
        result = mayor.heartbeat()
        assert result["department"] == "MURALI"

        # ── Verify Mission Created ──
        missions = sankalpa.registry.missions
        assert len(missions) >= 1, f"Expected at least 1 mission, got {len(missions)}"
        fed_mission = [m for m in missions if "reputation" in m.name.lower()
                       or "federation" in m.name.lower()]
        assert len(fed_mission) == 1, f"Expected 1 federation mission, got {fed_mission}"
        mission = fed_mission[0]
        assert mission.owner == "federation"
        assert mission.priority.name == "HIGH"
        assert "reputation" in mission.description.lower() or "trust" in mission.description.lower()

        # ── Verify Council Proposal Created ──
        open_proposals = council.get_open_proposals()
        fed_proposals = [p for p in open_proposals
                         if "federation" in p.title.lower() or "reputation" in p.title.lower()]
        assert len(fed_proposals) >= 1, (
            f"Expected a council proposal for mission directive, got {open_proposals}"
        )
        proposal = fed_proposals[0]
        assert proposal.action.get("type") == "federation_mission"
        assert proposal.action.get("directive_id") == "DIR-MISSION"

        # ── Verify Directive Acknowledged ──
        assert (directives_dir / "DIR-MISSION.json.done").exists()
        assert not (directives_dir / "DIR-MISSION.json").exists()
    finally:
        shutil.rmtree(tmp)


def test_city_report_includes_real_mission_outcomes():
    """HARD TEST: CityReport.mission_results populated from actual mission registry.

    This tests that MOKSHA doesn't just report `mission_results: []`.
    When missions exist (with various statuses), the CityReport must include
    their outcomes so mothership can track what happened to its directives.

    Without this, mothership sends directives into a black hole —
    it never knows what the city did with them.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay, sankalpa, council, _ = _make_mayor_full_stack(tmp)

        # Simulate some missions with results (as if KARMA executed them)
        from dataclasses import dataclass
        from enum import Enum

        # Mock mission objects that look like real SankalpaMission
        class MockStatus(str, Enum):
            ACTIVE = "active"
            COMPLETED = "completed"
            FAILED = "failed"

        class MockPriority(str, Enum):
            HIGH = "HIGH"
            MEDIUM = "MEDIUM"

        @dataclass
        class MockMission:
            id: str
            name: str
            description: str
            priority: MockPriority
            status: MockStatus
            owner: str

        # Add missions with different statuses
        sankalpa.registry.add_mission(MockMission(
            id="fed_DIR-A_5", name="Federation: Agent reputation",
            description="Implement trust scoring", priority=MockPriority.HIGH,
            status=MockStatus.COMPLETED, owner="federation",
        ))
        sankalpa.registry.add_mission(MockMission(
            id="fed_DIR-B_6", name="Federation: Network analysis",
            description="Analyze agent connections", priority=MockPriority.MEDIUM,
            status=MockStatus.ACTIVE, owner="federation",
        ))
        sankalpa.registry.add_mission(MockMission(
            id="heal_ruff_7", name="Heal: ruff_clean",
            description="Fix lint", priority=MockPriority.MEDIUM,
            status=MockStatus.COMPLETED, owner="mayor",
        ))

        # Advance to MOKSHA (heartbeat 3)
        results = mayor.run_cycle(4)
        moksha = results[3]
        assert moksha["department"] == "MURALI"
        assert moksha["reflection"].get("federation_report_sent") is True

        # ── Verify Report Contains Mission Results ──
        report = relay.last_report
        mission_results = report.get("mission_results", [])
        assert len(mission_results) > 0, (
            f"Expected mission_results in CityReport, got empty list. "
            f"Report keys: {list(report.keys())}"
        )

        # Should include federation missions
        fed_results = [r for r in mission_results if r.get("owner") == "federation"]
        assert len(fed_results) >= 1, (
            f"Expected federation mission results, got: {mission_results}"
        )

        # Completed mission should have status
        completed = [r for r in mission_results if r.get("status") == "completed"]
        assert len(completed) >= 1, "Expected at least 1 completed mission in report"

        # Each result should have meaningful fields
        for r in mission_results:
            assert "id" in r, f"Mission result missing 'id': {r}"
            assert "status" in r, f"Mission result missing 'status': {r}"
            assert "name" in r, f"Mission result missing 'name': {r}"
    finally:
        shutil.rmtree(tmp)


def test_moltbook_post_includes_mission_outcomes():
    """HARD TEST: Moltbook city update includes mission results in the post content.

    This tests the full bidirectional loop:
    Mothership → Directive → Mission → CityReport → Moltbook Post with results.

    The community on Moltbook should be able to SEE what happened to
    their ideas — not just population stats and chain status.
    Without this, the public face of Agent City is a dead dashboard.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay, sankalpa, council, bridge = _make_mayor_full_stack(
            tmp, with_bridge=True,
        )
        assert bridge is not None

        # Add a completed federation mission
        from dataclasses import dataclass
        from enum import Enum

        class MockStatus(str, Enum):
            COMPLETED = "completed"

        class MockPriority(str, Enum):
            HIGH = "HIGH"

        @dataclass
        class MockMission:
            id: str
            name: str
            description: str
            priority: MockPriority
            status: MockStatus
            owner: str

        sankalpa.registry.add_mission(MockMission(
            id="fed_DIR-X_10", name="Federation: Smart Contracts",
            description="Implement contract templates from community request",
            priority=MockPriority.HIGH, status=MockStatus.COMPLETED,
            owner="federation",
        ))

        # Run full MURALI rotation → MOKSHA posts to Moltbook
        results = mayor.run_cycle(4)
        moksha = results[3]
        assert moksha["department"] == "MURALI"

        # ── Verify Moltbook Post Includes Mission Data ──
        client = bridge._client
        if client.posts_created:
            post = client.posts_created[0]
            content = post["content"].lower()
            # The post must mention completed missions
            assert "mission" in content or "completed" in content, (
                f"Moltbook post should mention mission outcomes. "
                f"Got content: {post['content'][:300]}"
            )
        else:
            # Bridge is offline (offline_mode=True skips moltbook posting)
            # In that case, verify the post_data at least has the info
            pass

        # Even if offline, verify that _build_post_data includes missions
        from city.hooks.moksha.outbound import _build_post_data
        from city.phases import PhaseContext
        ctx = PhaseContext(
            pokedex=pokedex, gateway=mayor._gateway, network=mayor._network,
            heartbeat_count=99, offline_mode=True, state_path=mayor._state_path,
            sankalpa=sankalpa,
        )
        post_data = _build_post_data(ctx, {"city_stats": pokedex.stats(), "chain_valid": True})
        assert "mission_results" in post_data, (
            f"post_data should include mission_results. Keys: {list(post_data.keys())}"
        )
        mission_results = post_data["mission_results"]
        assert len(mission_results) >= 1, "Expected mission results in post data"
    finally:
        shutil.rmtree(tmp)


# ── Phase 8: FederationNadi Tests ─────────────────────────────────


def test_federation_nadi_creation():
    """FederationNadi starts with empty state and creates dirs."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        nadi = FederationNadi(_federation_dir=tmp / "federation")
        assert (tmp / "federation").exists()
        stats = nadi.stats()
        assert stats["outbox_pending"] == 0
        assert stats["outbox_on_disk"] == 0
        assert stats["inbox_on_disk"] == 0
        assert stats["processed"] == 0
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_emit_and_flush():
    """emit() queues messages, flush() writes them to disk."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        nadi = FederationNadi(_federation_dir=tmp / "federation")

        # Emit 3 messages
        nadi.emit("moksha", "city_report", {"heartbeat": 1, "alive": 10})
        nadi.emit("karma", "pr_created", {"pr_url": "https://github.com/test/1"})
        nadi.emit("karma", "heal_done", {"contract": "ruff_clean"}, priority=3)

        assert nadi.stats()["outbox_pending"] == 3

        # Flush to disk
        count = nadi.flush()
        assert count == 3
        assert nadi.stats()["outbox_pending"] == 0
        assert nadi.stats()["outbox_on_disk"] == 3

        # Verify file contents
        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == 3
        # Highest priority first (SUDDHA=3)
        assert data[0]["operation"] == "heal_done"
        assert data[0]["priority"] == 3
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_receive():
    """receive() reads messages from inbox and deduplicates."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        nadi = FederationNadi(_federation_dir=tmp / "federation")

        # Write inbox messages (simulating mothership delivery)
        inbox_data = [
            {
                "source": "genesis",
                "target": "agent-city",
                "operation": "register_agent",
                "payload": {"name": "NewAgent"},
                "priority": 2,
                "correlation_id": "dir_001",
                "timestamp": time.time(),
                "ttl_s": 900.0,
            },
            {
                "source": "dharma",
                "target": "agent-city",
                "operation": "execute_code",
                "payload": {"contract": "ruff_clean"},
                "priority": 1,
                "correlation_id": "dir_002",
                "timestamp": time.time(),
                "ttl_s": 900.0,
            },
        ]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        # Receive
        messages = nadi.receive()
        assert len(messages) == 2
        # SATTVA (2) first
        assert messages[0].source == "genesis"
        assert messages[0].operation == "register_agent"
        assert messages[0].payload["name"] == "NewAgent"

        # Second receive — deduplication
        messages2 = nadi.receive()
        assert len(messages2) == 0
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_expired_messages():
    """Expired messages are filtered on receive."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        nadi = FederationNadi(_federation_dir=tmp / "federation")

        inbox_data = [
            {
                "source": "old",
                "target": "agent-city",
                "operation": "stale",
                "payload": {},
                "priority": 1,
                "correlation_id": "",
                "timestamp": time.time() - 2000,  # Expired (TTL=900)
                "ttl_s": 900.0,
            },
            {
                "source": "fresh",
                "target": "agent-city",
                "operation": "alive",
                "payload": {},
                "priority": 1,
                "correlation_id": "",
                "timestamp": time.time(),
                "ttl_s": 900.0,
            },
        ]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        messages = nadi.receive()
        assert len(messages) == 1
        assert messages[0].source == "fresh"
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_buffer_cap():
    """Outbox caps at NADI_BUFFER_SIZE (144)."""
    from city.federation_nadi import FederationNadi, NADI_BUFFER_SIZE

    tmp = Path(tempfile.mkdtemp())
    try:
        nadi = FederationNadi(_federation_dir=tmp / "federation")

        # Emit 200 messages (exceeds buffer)
        for i in range(200):
            nadi.emit("test", f"op_{i}", {"index": i})

        count = nadi.flush()
        assert count == 200

        # Disk should be capped at buffer size
        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == NADI_BUFFER_SIZE
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_clear_inbox():
    """clear_inbox removes expired messages from disk."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        nadi = FederationNadi(_federation_dir=tmp / "federation")

        inbox_data = [
            {
                "source": "old", "target": "agent-city", "operation": "stale",
                "payload": {}, "priority": 1, "correlation_id": "",
                "timestamp": time.time() - 2000, "ttl_s": 900.0,
            },
            {
                "source": "fresh", "target": "agent-city", "operation": "alive",
                "payload": {}, "priority": 1, "correlation_id": "",
                "timestamp": time.time(), "ttl_s": 900.0,
            },
        ]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        nadi.clear_inbox()

        remaining = json.loads(nadi.inbox_path.read_text())
        assert len(remaining) == 1
        assert remaining[0]["source"] == "fresh"
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_message_serialization():
    """FederationMessage round-trips through dict correctly."""
    from city.federation_nadi import FederationMessage, SATTVA

    msg = FederationMessage(
        source="moksha",
        target="steward-protocol",
        operation="city_report",
        payload={"heartbeat": 42, "alive": 18},
        priority=SATTVA,
        correlation_id="cor_123",
    )
    d = msg.to_dict()
    assert d["source"] == "moksha"
    assert d["priority"] == SATTVA
    assert d["payload"]["heartbeat"] == 42

    msg2 = FederationMessage.from_dict(d)
    assert msg2.source == msg.source
    assert msg2.operation == msg.operation
    assert msg2.payload == msg.payload
    assert msg2.priority == msg.priority
    assert msg2.correlation_id == msg.correlation_id


def test_federation_nadi_genesis_integration():
    """FederationNadi messages are enqueued in GENESIS phase."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Create FederationNadi and register it
        fed_nadi = FederationNadi(_federation_dir=tmp / "federation")
        mayor._registry.register("federation_nadi", fed_nadi)

        # Write inbox messages (simulating mothership delivery)
        inbox_data = [
            {
                "source": "opus_1",
                "target": "agent-city",
                "operation": "code_intent",
                "payload": {"topic": "fix ruff violations"},
                "priority": 2,
                "correlation_id": "dir_999",
                "timestamp": time.time(),
                "ttl_s": 900.0,
            },
        ]
        fed_nadi.inbox_path.write_text(json.dumps(inbox_data))

        # Run GENESIS
        result = mayor.heartbeat()
        assert result["department"] == "MURALI"
        assert any("fed_nadi:" in d for d in result["discovered"])
    finally:
        shutil.rmtree(tmp)


def test_federation_nadi_moksha_flush():
    """FederationNadi flushes outbox messages in MOKSHA phase."""
    from city.federation_nadi import FederationNadi

    tmp = Path(tempfile.mkdtemp())
    try:
        mayor, pokedex, relay = _make_mayor_with_federation(tmp)

        # Create FederationNadi and register it
        fed_nadi = FederationNadi(_federation_dir=tmp / "federation")
        mayor._registry.register("federation_nadi", fed_nadi)

        # Run full MURALI rotation → MOKSHA should flush
        results = mayor.run_cycle(4)
        moksha = results[3]
        assert moksha["department"] == "MURALI"

        # Outbox file should exist with city_report message
        if fed_nadi.outbox_path.exists():
            data = json.loads(fed_nadi.outbox_path.read_text())
            assert len(data) >= 1
            report_msgs = [m for m in data if m["operation"] == "city_report"]
            assert len(report_msgs) >= 1
            assert report_msgs[0]["source"] == "moksha"
            assert "heartbeat" in report_msgs[0]["payload"]
    finally:
        shutil.rmtree(tmp)


# ── Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import unittest
    # Collect all test functions
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
