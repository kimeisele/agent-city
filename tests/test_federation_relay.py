"""
Tests for FederationRelay — Cross-Repo Communication.

Covers: CityReport dataclass, FederationDirective, send_report (audit trail),
check_directives (file-based intake), acknowledge_directive (rename → .done),
stats, report log capping, edge cases (corrupt files, missing dirs).

Also tests nadi_bridge.py CLI: read-outbox, write-inbox, clear-outbox, stats.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from city.federation import (
    CityReport,
    FederationDirective,
    FederationRelay,
)


# ── Helpers ────────────────────────────────────────────────────────────


@pytest.fixture
def fed_dirs(tmp_path):
    directives = tmp_path / "directives"
    reports = tmp_path / "reports"
    directives.mkdir()
    reports.mkdir()
    return directives, reports


@pytest.fixture
def relay(fed_dirs):
    directives_dir, reports_dir = fed_dirs
    return FederationRelay(
        _directives_dir=directives_dir,
        _reports_dir=reports_dir,
        _dry_run=True,
    )


def _make_report(heartbeat: int = 1, population: int = 10) -> CityReport:
    return CityReport(
        heartbeat=heartbeat,
        timestamp=time.time(),
        population=population,
        alive=population - 2,
        dead=2,
        elected_mayor="TestMayor",
        council_seats=3,
        open_proposals=1,
        chain_valid=True,
        recent_actions=["genesis:discover", "karma:heal"],
        contract_status={"lint": "passing", "test": "failing"},
        mission_results=[{"name": "heal_lint", "status": "completed"}],
        directive_acks=["dir_001"],
        pr_results=[{"pr": 7, "status": "merged"}],
        active_campaigns=[{"id": "internet-adaptation", "status": "active"}],
    )


def _write_directive(directives_dir: Path, directive_id: str,
                     directive_type: str = "create_mission",
                     params: dict | None = None) -> Path:
    data = {
        "id": directive_id,
        "directive_type": directive_type,
        "params": params or {"topic": "test"},
        "timestamp": time.time(),
        "source": "mothership",
    }
    path = directives_dir / f"{directive_id}.json"
    path.write_text(json.dumps(data))
    return path


# ── CityReport ─────────────────────────────────────────────────────────


class TestCityReport:
    def test_to_dict_roundtrip(self):
        report = _make_report(heartbeat=42, population=20)
        d = report.to_dict()

        assert d["heartbeat"] == 42
        assert d["population"] == 20
        assert d["alive"] == 18
        assert d["dead"] == 2
        assert d["elected_mayor"] == "TestMayor"
        assert d["council_seats"] == 3
        assert d["chain_valid"] is True
        assert len(d["recent_actions"]) == 2
        assert d["pr_results"][0]["pr"] == 7

    def test_frozen(self):
        report = _make_report()
        with pytest.raises(AttributeError):
            report.heartbeat = 999  # type: ignore[misc]

    def test_all_fields_present(self):
        report = _make_report()
        d = report.to_dict()
        expected_keys = {
            "heartbeat", "timestamp", "population", "alive", "dead",
            "elected_mayor", "council_seats", "open_proposals",
            "chain_valid", "recent_actions", "contract_status",
            "mission_results", "directive_acks", "pr_results", "active_campaigns",
        }
        assert expected_keys == set(d.keys())


# ── FederationDirective ────────────────────────────────────────────────


class TestFederationDirective:
    def test_frozen(self):
        d = FederationDirective(
            id="dir_001", directive_type="create_mission",
            params={"topic": "fix"}, timestamp=time.time(), source="mothership",
        )
        with pytest.raises(AttributeError):
            d.id = "modified"  # type: ignore[misc]


# ── send_report ────────────────────────────────────────────────────────


class TestSendReport:
    def test_saves_report_to_disk(self, relay, fed_dirs):
        _, reports_dir = fed_dirs
        report = _make_report(heartbeat=5)
        result = relay.send_report(report)

        assert result is True
        report_file = reports_dir / "report_5.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text())
        assert data["heartbeat"] == 5

    def test_stores_last_report(self, relay):
        report = _make_report(heartbeat=10)
        relay.send_report(report)

        assert relay.last_report["heartbeat"] == 10
        assert relay.last_report["population"] == 10

    def test_appends_to_report_log(self, relay):
        relay.send_report(_make_report(heartbeat=1))
        relay.send_report(_make_report(heartbeat=2))
        relay.send_report(_make_report(heartbeat=3))

        assert relay.stats()["reports_sent"] == 3

    def test_clears_acknowledged_on_send(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "d1")
        relay.check_directives()
        relay.acknowledge_directive("d1")
        assert len(relay.pending_acks) == 1

        relay.send_report(_make_report())
        assert len(relay.pending_acks) == 0

    def test_report_log_capped(self, relay):
        # Default max is 50, trim to 25
        for i in range(60):
            relay.send_report(_make_report(heartbeat=i))

        assert len(relay._report_log) <= 50


# ── federation claim ───────────────────────────────────────────────────


def _make_relay_with_peer(tmp_path: Path) -> tuple["FederationRelay", Path]:
    """Create a relay with a real peer.json in its federation dir."""
    fed_dir = tmp_path / "federation"
    directives_dir = fed_dir / "directives"
    reports_dir = fed_dir / "reports"
    directives_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    peer = {
        "identity": {
            "city_id": "agent-city",
            "node_id": "ag_testnode123",
            "public_key": "deadbeef",
        },
        "capabilities": ["multi_agent_runtime", "city_governance"],
    }
    (fed_dir / "peer.json").write_text(json.dumps(peer))

    relay = FederationRelay(
        _directives_dir=directives_dir,
        _reports_dir=reports_dir,
    )
    return relay, fed_dir


class TestFederationClaim:
    def test_claim_written_to_outbox_on_first_send_report(self, tmp_path):
        relay, fed_dir = _make_relay_with_peer(tmp_path)
        relay.send_report(_make_report(heartbeat=1))

        outbox = json.loads((fed_dir / "nadi_outbox.json").read_text())
        claim = next((m for m in outbox if m.get("operation") == "federation.agent_claim"), None)
        assert claim is not None
        # source must equal node_id: gateway verifies derive_node_id(public_key)==source
        assert claim["source"] == "ag_testnode123"
        assert claim["target"] == "steward"
        assert claim["payload"]["node_id"] == "ag_testnode123"
        assert claim["payload"]["agent_name"] == "agent-city"
        assert claim["payload"]["public_key"] == "deadbeef"
        assert claim["payload"]["repo"] == "kimeisele/agent-city"
        assert "multi_agent_runtime" in claim["payload"]["capabilities"]

    def test_sentinel_created_after_claim(self, tmp_path):
        import hashlib as _h

        relay, fed_dir = _make_relay_with_peer(tmp_path)
        relay.send_report(_make_report(heartbeat=1))
        # Sentinel name is bound to the public key digest so a key rotation
        # automatically retriggers the claim.
        token = _h.sha256("deadbeef".encode("utf-8")).hexdigest()[:16]
        assert (fed_dir / f".claim_sent_{token}").exists()

    def test_claim_sent_only_once(self, tmp_path):
        relay, fed_dir = _make_relay_with_peer(tmp_path)
        relay.send_report(_make_report(heartbeat=1))
        relay.send_report(_make_report(heartbeat=2))
        relay.send_report(_make_report(heartbeat=3))

        outbox = json.loads((fed_dir / "nadi_outbox.json").read_text())
        claims = [m for m in outbox if m.get("operation") == "federation.agent_claim"]
        assert len(claims) == 1

    def test_claim_skipped_if_sentinel_exists(self, tmp_path):
        import hashlib as _h

        relay, fed_dir = _make_relay_with_peer(tmp_path)
        token = _h.sha256("deadbeef".encode("utf-8")).hexdigest()[:16]
        (fed_dir / f".claim_sent_{token}").write_text("")  # pubkey-bound sentinel

        relay.send_report(_make_report(heartbeat=1))

        outbox = json.loads((fed_dir / "nadi_outbox.json").read_text())
        claims = [m for m in outbox if m.get("operation") == "federation.agent_claim"]
        assert len(claims) == 0

    def test_claim_resent_after_key_rotation(self, tmp_path):
        """Stale sentinel for an OLD pubkey must NOT block a new claim."""
        relay, fed_dir = _make_relay_with_peer(tmp_path)
        # Pretend we previously claimed under a different pubkey
        (fed_dir / ".claim_sent_oldkeytoken00").write_text("")

        relay.send_report(_make_report(heartbeat=1))

        outbox = json.loads((fed_dir / "nadi_outbox.json").read_text())
        claims = [m for m in outbox if m.get("operation") == "federation.agent_claim"]
        assert len(claims) == 1

    def test_claim_skipped_gracefully_without_peer_json(self, fed_dirs):
        """Relay without peer.json should not crash."""
        directives_dir, reports_dir = fed_dirs
        relay = FederationRelay(
            _directives_dir=directives_dir,
            _reports_dir=reports_dir,
        )
        relay.send_report(_make_report(heartbeat=1))  # must not raise

    def test_heartbeat_uses_operation_key(self, tmp_path):
        relay, fed_dir = _make_relay_with_peer(tmp_path)
        relay.send_report(_make_report(heartbeat=1))

        outbox = json.loads((fed_dir / "nadi_outbox.json").read_text())
        heartbeat = next((m for m in outbox if m.get("operation") == "heartbeat"), None)
        assert heartbeat is not None
        assert "type" not in heartbeat
        # source must be node_id so gateway's is_verified_agent(source) passes
        assert heartbeat["source"] == "ag_testnode123"


# ── check_directives ──────────────────────────────────────────────────


class TestCheckDirectives:
    def test_reads_json_files(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "dir_001", "create_mission")
        _write_directive(directives_dir, "dir_002", "freeze_agent")

        directives = relay.check_directives()
        assert len(directives) == 2
        types = {d.directive_type for d in directives}
        assert types == {"create_mission", "freeze_agent"}

    def test_skips_done_files(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "dir_001")
        # Create a .done.json file — should be skipped
        done_path = directives_dir / "dir_002.done.json"
        done_path.write_text(json.dumps({"id": "dir_002"}))

        directives = relay.check_directives()
        assert len(directives) == 1
        assert directives[0].id == "dir_001"

    def test_handles_corrupt_file(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "good")
        bad = directives_dir / "bad.json"
        bad.write_text("not valid json{{{")

        directives = relay.check_directives()
        assert len(directives) == 1
        assert directives[0].id == "good"

    def test_empty_directory(self, relay):
        directives = relay.check_directives()
        assert directives == []

    def test_missing_directory(self, tmp_path):
        relay = FederationRelay(
            _directives_dir=tmp_path / "nonexistent",
            _reports_dir=tmp_path / "reports",
        )
        # __post_init__ creates the dir, so it exists
        directives = relay.check_directives()
        assert directives == []

    def test_sorted_by_filename(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "b_directive")
        _write_directive(directives_dir, "a_directive")

        directives = relay.check_directives()
        assert directives[0].id == "a_directive"
        assert directives[1].id == "b_directive"

    def test_directive_fields(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "d1", "register_agent",
                         {"name": "NewAgent", "element": "fire"})

        directives = relay.check_directives()
        assert len(directives) == 1
        d = directives[0]
        assert d.id == "d1"
        assert d.directive_type == "register_agent"
        assert d.params == {"name": "NewAgent", "element": "fire"}
        assert d.source == "mothership"


# ── acknowledge_directive ──────────────────────────────────────────────


class TestAcknowledgeDirective:
    def test_renames_to_done(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "ack_me")

        result = relay.acknowledge_directive("ack_me")
        assert result is True
        assert not (directives_dir / "ack_me.json").exists()
        assert (directives_dir / "ack_me.json.done").exists()

    def test_ack_tracked(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "d1")
        relay.acknowledge_directive("d1")

        assert "d1" in relay.pending_acks

    def test_ack_unknown_returns_false(self, relay):
        assert relay.acknowledge_directive("nonexistent") is False

    def test_ack_by_id_inside_json(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        # File named differently but ID inside matches
        data = {
            "id": "custom_id_123",
            "directive_type": "freeze_agent",
            "params": {},
            "timestamp": time.time(),
            "source": "mothership",
        }
        path = directives_dir / "some_file.json"
        path.write_text(json.dumps(data))

        result = relay.acknowledge_directive("custom_id_123")
        assert result is True
        assert not path.exists()


# ── stats ──────────────────────────────────────────────────────────────


class TestStats:
    def test_initial_stats(self, relay):
        stats = relay.stats()
        assert stats["dry_run"] is True
        assert stats["reports_sent"] == 0
        assert stats["pending_directives"] == 0
        assert stats["processed_directives"] == 0
        assert stats["last_report_heartbeat"] is None

    def test_stats_after_report(self, relay):
        relay.send_report(_make_report(heartbeat=42))
        stats = relay.stats()
        assert stats["reports_sent"] == 1
        assert stats["last_report_heartbeat"] == 42

    def test_stats_counts_directives(self, relay, fed_dirs):
        directives_dir, _ = fed_dirs
        _write_directive(directives_dir, "d1")
        _write_directive(directives_dir, "d2")

        stats = relay.stats()
        assert stats["pending_directives"] == 2

        relay.acknowledge_directive("d1")
        stats = relay.stats()
        assert stats["pending_directives"] == 1
        assert stats["processed_directives"] == 1


# ══════════════════════════════════════════════════════════════════════
# nadi_bridge.py CLI Tests
# ══════════════════════════════════════════════════════════════════════


class TestNadiBridgeCLI:
    """Test the nadi_bridge.py CLI via subprocess."""

    def test_read_outbox_empty(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "read-outbox"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == []

    def test_read_outbox_with_data(self, tmp_path):
        import subprocess
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text(json.dumps([
            {"source": "moksha", "operation": "city_report",
             "payload": {"heartbeat": 1}},
        ]))

        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "read-outbox"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["payload"]["heartbeat"] == 1

    def test_write_inbox(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "write-inbox",
             "--source", "opus_1",
             "--operation", "create_mission",
             "--payload", '{"topic": "fix ruff"}'],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        resp = json.loads(result.stdout)
        assert resp["written"] is True

        # Verify inbox file
        inbox = tmp_path / "nadi_inbox.json"
        assert inbox.exists()
        data = json.loads(inbox.read_text())
        assert len(data) == 1
        assert data[0]["source"] == "opus_1"
        assert data[0]["operation"] == "create_mission"
        assert data[0]["payload"]["topic"] == "fix ruff"

    def test_write_inbox_appends(self, tmp_path):
        import subprocess
        # Write first
        subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "write-inbox",
             "--source", "a", "--operation", "op1", "--payload", "{}"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        # Write second
        subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "write-inbox",
             "--source", "b", "--operation", "op2", "--payload", "{}"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )

        inbox = tmp_path / "nadi_inbox.json"
        data = json.loads(inbox.read_text())
        assert len(data) == 2

    def test_clear_outbox(self, tmp_path):
        import subprocess
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text(json.dumps([{"test": True}]))

        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "clear-outbox"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        resp = json.loads(result.stdout)
        assert resp["cleared"] is True
        assert json.loads(outbox.read_text()) == []

    def test_clear_outbox_missing(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "clear-outbox"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        resp = json.loads(result.stdout)
        assert resp["cleared"] is False

    def test_stats(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "stats"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        stats = json.loads(result.stdout)
        assert "outbox_on_disk" in stats
        assert "inbox_on_disk" in stats

    def test_write_inbox_invalid_json(self, tmp_path):
        import subprocess
        result = subprocess.run(
            ["python", "scripts/nadi_bridge.py",
             "--data-dir", str(tmp_path), "write-inbox",
             "--source", "a", "--operation", "op",
             "--payload", "not json{{{"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0


# ══════════════════════════════════════════════════════════════════════
# Cross-Repo Contract: CityReport format matches FederationNadi outbox
# ══════════════════════════════════════════════════════════════════════


class TestCrossRepoContract:
    """Verify CityReport format is compatible with FederationNadi outbox."""

    def test_city_report_payload_matches_nadi_outbox(self):
        """CityReport.to_dict() keys match what MOKSHA writes to FederationNadi."""
        report = _make_report(heartbeat=99)
        d = report.to_dict()

        # These keys MUST be present for steward-protocol to consume
        assert "heartbeat" in d
        assert "population" in d
        assert "alive" in d
        assert "chain_valid" in d
        assert "mission_results" in d
        assert "pr_results" in d
        assert "active_campaigns" in d

    def test_city_report_serializable(self):
        """CityReport can be JSON-serialized (for Nadi payload)."""
        report = _make_report()
        serialized = json.dumps(report.to_dict())
        restored = json.loads(serialized)
        assert restored["heartbeat"] == report.heartbeat

    def test_federation_nadi_can_emit_city_report(self, tmp_path):
        """FederationNadi.emit() accepts CityReport.to_dict() as payload."""
        from city.federation_nadi import FederationNadi

        nadi = FederationNadi(_federation_dir=tmp_path)
        report = _make_report(heartbeat=42)

        nadi.emit("moksha", "city_report", report.to_dict())
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == 1
        assert data[0]["payload"]["heartbeat"] == 42
        assert data[0]["payload"]["chain_valid"] is True
