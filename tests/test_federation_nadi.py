"""
Tests for FederationNadi — Inter-Repo Message Bridge.

File-based Nadi channel for steward-protocol ↔ agent-city communication.
Tests cover: emit/flush/receive cycle, TTL expiry, priority sorting,
dedup, buffer cap, outbox merge, inbox clear, snapshot roundtrip,
and cross-repo compatibility (steward-protocol can consume our outbox format).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from city.federation_nadi import (
    NADI_BUFFER_SIZE,
    NADI_FEDERATION_TTL_S,
    RAJAS,
    SATTVA,
    SUDDHA,
    TAMAS,
    FederationMessage,
    FederationNadi,
)


# ── Helpers ────────────────────────────────────────────────────────────


@pytest.fixture
def fed_dir(tmp_path):
    """Temp federation directory."""
    d = tmp_path / "federation"
    d.mkdir()
    return d


@pytest.fixture
def nadi(fed_dir):
    """Fresh FederationNadi with temp dir."""
    return FederationNadi(_federation_dir=fed_dir)


# ── FederationMessage ─────────────────────────────────────────────────


class TestFederationMessage:
    def test_to_dict_roundtrip(self):
        msg = FederationMessage(
            source="moksha",
            target="steward-protocol",
            operation="city_report",
            payload={"heartbeat": 42, "population": 10},
            priority=SATTVA,
            correlation_id="corr_123",
        )
        d = msg.to_dict()
        restored = FederationMessage.from_dict(d)

        assert restored.source == "moksha"
        assert restored.target == "steward-protocol"
        assert restored.operation == "city_report"
        assert restored.payload == {"heartbeat": 42, "population": 10}
        assert restored.priority == SATTVA
        assert restored.correlation_id == "corr_123"

    def test_is_expired_fresh(self):
        msg = FederationMessage(
            source="test", target="test", operation="test", payload={},
        )
        assert msg.is_expired is False

    def test_is_expired_old(self):
        msg = FederationMessage(
            source="test", target="test", operation="test", payload={},
            timestamp=time.time() - 2000,
            ttl_s=100,
        )
        assert msg.is_expired is True

    def test_from_dict_defaults(self):
        msg = FederationMessage.from_dict({})
        assert msg.source == "unknown"
        assert msg.target == ""
        assert msg.operation == "process"
        assert msg.priority == RAJAS

    def test_default_ttl_is_federation(self):
        msg = FederationMessage(
            source="test", target="test", operation="test", payload={},
        )
        assert msg.ttl_s == NADI_FEDERATION_TTL_S


# ── Emit + Flush ──────────────────────────────────────────────────────


class TestEmitFlush:
    def test_emit_queues_message(self, nadi):
        assert nadi.emit("karma", "heal_result", {"contract": "lint"}) is True
        assert len(nadi._outbox) == 1

    def test_flush_writes_to_disk(self, nadi, fed_dir):
        nadi.emit("moksha", "city_report", {"heartbeat": 1})
        count = nadi.flush()

        assert count == 1
        assert nadi.outbox_path.exists()
        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == 1
        assert data[0]["source"] == "moksha"
        assert data[0]["operation"] == "city_report"
        assert data[0]["payload"]["heartbeat"] == 1

    def test_flush_clears_outbox(self, nadi):
        nadi.emit("karma", "test", {})
        nadi.flush()
        assert len(nadi._outbox) == 0

    def test_flush_empty_returns_zero(self, nadi):
        assert nadi.flush() == 0

    def test_flush_merges_with_existing(self, nadi, fed_dir):
        # Write existing message
        existing = [{
            "source": "old", "target": "steward-protocol",
            "operation": "old_op", "payload": {},
            "priority": 1, "correlation_id": "",
            "timestamp": time.time(), "ttl_s": 900.0,
        }]
        nadi.outbox_path.write_text(json.dumps(existing))

        nadi.emit("moksha", "new_op", {"new": True})
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == 2

    def test_flush_filters_expired(self, nadi, fed_dir):
        # Write expired message
        expired = [{
            "source": "old", "target": "steward-protocol",
            "operation": "expired_op", "payload": {},
            "priority": 1, "correlation_id": "",
            "timestamp": time.time() - 2000, "ttl_s": 100.0,
        }]
        nadi.outbox_path.write_text(json.dumps(expired))

        nadi.emit("moksha", "fresh", {})
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == 1
        assert data[0]["operation"] == "fresh"

    def test_flush_caps_at_buffer_size(self, nadi):
        for i in range(NADI_BUFFER_SIZE + 20):
            nadi.emit("karma", f"op_{i}", {"idx": i})
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == NADI_BUFFER_SIZE

    def test_flush_priority_sorted(self, nadi):
        nadi.emit("karma", "low", {}, priority=TAMAS)
        nadi.emit("moksha", "high", {}, priority=SUDDHA)
        nadi.emit("genesis", "medium", {}, priority=RAJAS)
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        # Highest priority first
        assert data[0]["operation"] == "high"
        assert data[1]["operation"] == "medium"
        assert data[2]["operation"] == "low"

    def test_flush_uses_atomic_write(self, nadi, fed_dir):
        """Flush writes to .tmp then renames (atomic)."""
        nadi.emit("moksha", "test", {})
        nadi.flush()

        # .tmp should not exist after flush
        tmp_path = nadi.outbox_path.with_suffix(".tmp")
        assert not tmp_path.exists()
        assert nadi.outbox_path.exists()


# ── Receive ───────────────────────────────────────────────────────────


class TestReceive:
    def test_receive_reads_inbox(self, nadi, fed_dir):
        inbox_data = [{
            "source": "steward-protocol",
            "target": "agent-city",
            "operation": "sync_request",
            "payload": {"agents": ["HERALD", "AUDITOR"]},
            "priority": 2,
            "correlation_id": "sync_001",
            "timestamp": time.time(),
            "ttl_s": 900.0,
        }]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        messages = nadi.receive()
        assert len(messages) == 1
        assert messages[0].source == "steward-protocol"
        assert messages[0].operation == "sync_request"
        assert messages[0].payload["agents"] == ["HERALD", "AUDITOR"]

    def test_receive_filters_expired(self, nadi, fed_dir):
        inbox_data = [{
            "source": "old", "target": "agent-city",
            "operation": "expired", "payload": {},
            "priority": 1, "correlation_id": "",
            "timestamp": time.time() - 2000, "ttl_s": 100.0,
        }]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        messages = nadi.receive()
        assert len(messages) == 0

    def test_receive_dedup_by_source_timestamp(self, nadi, fed_dir):
        ts = time.time()
        inbox_data = [
            {"source": "sp", "target": "ac", "operation": "op1",
             "payload": {}, "priority": 1, "correlation_id": "",
             "timestamp": ts, "ttl_s": 900.0},
            {"source": "sp", "target": "ac", "operation": "op1_dup",
             "payload": {}, "priority": 1, "correlation_id": "",
             "timestamp": ts, "ttl_s": 900.0},  # same source+timestamp = dup
        ]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        messages = nadi.receive()
        assert len(messages) == 1

    def test_receive_priority_sorted(self, nadi, fed_dir):
        now = time.time()
        inbox_data = [
            {"source": "a", "target": "ac", "operation": "low",
             "payload": {}, "priority": TAMAS, "timestamp": now, "ttl_s": 900.0},
            {"source": "b", "target": "ac", "operation": "high",
             "payload": {}, "priority": SUDDHA, "timestamp": now + 1, "ttl_s": 900.0},
            {"source": "c", "target": "ac", "operation": "mid",
             "payload": {}, "priority": RAJAS, "timestamp": now + 2, "ttl_s": 900.0},
        ]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        messages = nadi.receive()
        assert len(messages) == 3
        assert messages[0].operation == "high"
        assert messages[1].operation == "mid"
        assert messages[2].operation == "low"

    def test_receive_idempotent(self, nadi, fed_dir):
        inbox_data = [{
            "source": "sp", "target": "ac", "operation": "test",
            "payload": {}, "priority": 1,
            "timestamp": time.time(), "ttl_s": 900.0,
        }]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        # First receive → 1 message
        assert len(nadi.receive()) == 1
        # Second receive → 0 (already processed)
        assert len(nadi.receive()) == 0

    def test_receive_empty_inbox(self, nadi):
        assert nadi.receive() == []

    def test_receive_missing_inbox_file(self, nadi):
        assert not nadi.inbox_path.exists()
        assert nadi.receive() == []

    def test_receive_corrupted_inbox(self, nadi, fed_dir):
        nadi.inbox_path.write_text("not json{{{")
        assert nadi.receive() == []


# ── Clear Inbox ───────────────────────────────────────────────────────


class TestClearInbox:
    def test_clear_removes_expired(self, nadi, fed_dir):
        now = time.time()
        inbox_data = [
            {"source": "live", "target": "ac", "operation": "keep",
             "payload": {}, "priority": 1, "timestamp": now, "ttl_s": 900.0},
            {"source": "dead", "target": "ac", "operation": "remove",
             "payload": {}, "priority": 1, "timestamp": now - 2000, "ttl_s": 100.0},
        ]
        nadi.inbox_path.write_text(json.dumps(inbox_data))

        nadi.clear_inbox()

        data = json.loads(nadi.inbox_path.read_text())
        assert len(data) == 1
        assert data[0]["operation"] == "keep"

    def test_clear_no_inbox_file(self, nadi):
        nadi.clear_inbox()  # should not crash


# ── Stats ─────────────────────────────────────────────────────────────


class TestStats:
    def test_stats_initial(self, nadi):
        stats = nadi.stats()
        assert stats["outbox_pending"] == 0
        assert stats["outbox_on_disk"] == 0
        assert stats["inbox_on_disk"] == 0
        assert stats["processed"] == 0

    def test_stats_after_emit(self, nadi):
        nadi.emit("moksha", "test", {})
        stats = nadi.stats()
        assert stats["outbox_pending"] == 1
        assert stats["outbox_on_disk"] == 0  # not flushed yet

    def test_stats_after_flush(self, nadi):
        nadi.emit("moksha", "test", {})
        nadi.flush()
        stats = nadi.stats()
        assert stats["outbox_pending"] == 0
        assert stats["outbox_on_disk"] == 1

    def test_stats_after_receive(self, nadi, fed_dir):
        inbox_data = [{
            "source": "sp", "target": "ac", "operation": "test",
            "payload": {}, "priority": 1,
            "timestamp": time.time(), "ttl_s": 900.0,
        }]
        nadi.inbox_path.write_text(json.dumps(inbox_data))
        nadi.receive()

        stats = nadi.stats()
        assert stats["processed"] == 1


# ══════════════════════════════════════════════════════════════════════
# Cross-Repo Compatibility Tests
#
# These tests verify that agent-city's outbox format is consumable by
# steward-protocol. This is the FEDERATION BRIDGE CONTRACT.
# ══════════════════════════════════════════════════════════════════════


class TestCrossRepoCompatibility:
    """Verify agent-city outbox is consumable by steward-protocol."""

    def _write_outbox_as_agent_city(self, nadi: FederationNadi):
        """Simulate what MOKSHA phase does."""
        nadi.emit(
            source="moksha",
            operation="city_report",
            payload={
                "heartbeat": 42,
                "population": 15,
                "alive": 12,
                "chain_valid": True,
                "pr_results": [{"pr": 7, "status": "merged"}],
                "mission_results": [{"name": "heal_lint", "status": "completed"}],
            },
            priority=SATTVA,
        )
        nadi.flush()

    def test_outbox_is_valid_json_array(self, nadi):
        self._write_outbox_as_agent_city(nadi)
        raw = nadi.outbox_path.read_text()
        data = json.loads(raw)
        assert isinstance(data, list)

    def test_outbox_message_has_required_fields(self, nadi):
        """Every outbox message must have these fields for steward-protocol."""
        self._write_outbox_as_agent_city(nadi)
        data = json.loads(nadi.outbox_path.read_text())
        msg = data[0]

        required = {"source", "target", "operation", "payload",
                    "priority", "correlation_id", "timestamp", "ttl_s"}
        assert required.issubset(set(msg.keys())), f"Missing: {required - set(msg.keys())}"

    def test_outbox_target_is_steward_protocol(self, nadi):
        self._write_outbox_as_agent_city(nadi)
        data = json.loads(nadi.outbox_path.read_text())
        assert data[0]["target"] == "steward-protocol"

    def test_outbox_payload_has_heartbeat(self, nadi):
        self._write_outbox_as_agent_city(nadi)
        data = json.loads(nadi.outbox_path.read_text())
        payload = data[0]["payload"]
        assert "heartbeat" in payload
        assert isinstance(payload["heartbeat"], int)

    def test_outbox_payload_has_population_and_alive(self, nadi):
        self._write_outbox_as_agent_city(nadi)
        data = json.loads(nadi.outbox_path.read_text())
        payload = data[0]["payload"]
        assert "population" in payload
        assert "alive" in payload

    def test_outbox_consumable_as_federation_message(self, nadi):
        """steward-protocol can deserialize our outbox entries."""
        self._write_outbox_as_agent_city(nadi)
        data = json.loads(nadi.outbox_path.read_text())

        for entry in data:
            msg = FederationMessage.from_dict(entry)
            assert msg.source == "moksha"
            assert msg.target == "steward-protocol"
            assert msg.is_expired is False
            assert isinstance(msg.payload, dict)

    def test_bidirectional_format(self, nadi, fed_dir):
        """steward-protocol inbox format → agent-city can receive."""
        # Simulate steward-protocol writing to agent-city's inbox
        sp_message = {
            "source": "steward-protocol",
            "target": "agent-city",
            "operation": "federation_sync",
            "payload": {
                "agents": [
                    {"agent_id": "HERALD", "status": "active", "reputation": 100},
                    {"agent_id": "AUDITOR", "status": "active", "reputation": 100},
                ],
                "protocol_version": "1.0",
            },
            "priority": SATTVA,
            "correlation_id": "sync_001",
            "timestamp": time.time(),
            "ttl_s": NADI_FEDERATION_TTL_S,
        }
        nadi.inbox_path.write_text(json.dumps([sp_message]))

        messages = nadi.receive()
        assert len(messages) == 1
        msg = messages[0]
        assert msg.source == "steward-protocol"
        assert msg.operation == "federation_sync"
        assert len(msg.payload["agents"]) == 2
        assert msg.payload["agents"][0]["agent_id"] == "HERALD"

    def test_steward_protocol_pokedex_format_compatible(self, nadi, fed_dir):
        """steward-protocol's federation/pokedex.json format is parseable."""
        # This is the ACTUAL format from steward-protocol/data/federation/pokedex.json
        sp_agents = [
            {"agent_id": "HERALD", "public_key": "04d8f8...",
             "status": "active", "role": "Broadcaster & Headhunter",
             "joined_at": "2025-11-20T00:00:00Z", "reputation": 100},
            {"agent_id": "AUDITOR", "public_key": "04c3d4...",
             "status": "active", "role": "Compliance Officer",
             "joined_at": "2025-11-20T00:00:00Z", "reputation": 100},
        ]

        # Wrap in federation message
        sp_message = {
            "source": "steward-protocol",
            "target": "agent-city",
            "operation": "pokedex_sync",
            "payload": {"agents": sp_agents},
            "priority": RAJAS,
            "correlation_id": "",
            "timestamp": time.time(),
            "ttl_s": NADI_FEDERATION_TTL_S,
        }
        nadi.inbox_path.write_text(json.dumps([sp_message]))

        messages = nadi.receive()
        assert len(messages) == 1
        agents = messages[0].payload["agents"]
        assert agents[0]["agent_id"] == "HERALD"
        assert agents[0]["status"] == "active"
        assert agents[1]["agent_id"] == "AUDITOR"

    def test_full_federation_roundtrip(self, fed_dir):
        """agent-city emits → flush → another FederationNadi reads as inbox."""
        # Simulate two repos sharing a directory (or transport copies outbox→inbox)
        city_nadi = FederationNadi(_federation_dir=fed_dir)
        city_nadi.emit("moksha", "city_report", {"heartbeat": 99, "population": 20})
        city_nadi.flush()

        # "Transport" copies outbox to inbox (simulating git sync / CI bridge)
        import shutil
        shutil.copy(city_nadi.outbox_path, city_nadi.inbox_path)

        # Consumer reads inbox
        consumer_nadi = FederationNadi(_federation_dir=fed_dir)
        messages = consumer_nadi.receive()
        assert len(messages) == 1
        assert messages[0].payload["heartbeat"] == 99
        assert messages[0].payload["population"] == 20

    def test_multiple_heartbeats_accumulate(self, nadi):
        """Multiple heartbeat reports accumulate in outbox."""
        for hb in range(1, 6):
            nadi.emit("moksha", "city_report", {"heartbeat": hb, "population": hb * 3})
        nadi.flush()

        data = json.loads(nadi.outbox_path.read_text())
        assert len(data) == 5
        heartbeats = [d["payload"]["heartbeat"] for d in data]
        assert set(heartbeats) == {1, 2, 3, 4, 5}


# ── File I/O Edge Cases ───────────────────────────────────────────────


class TestFileIO:
    def test_read_missing_file(self, nadi):
        result = nadi._read_file(Path("/nonexistent/path.json"))
        assert result == []

    def test_read_corrupted_file(self, nadi, fed_dir):
        bad = fed_dir / "bad.json"
        bad.write_text("{not a list}")
        result = nadi._read_file(bad)
        assert result == []

    def test_read_non_list_json(self, nadi, fed_dir):
        bad = fed_dir / "dict.json"
        bad.write_text('{"key": "value"}')
        result = nadi._read_file(bad)
        assert result == []

    def test_write_creates_file(self, nadi, fed_dir):
        path = fed_dir / "new.json"
        nadi._write_file(path, [{"test": True}])
        assert path.exists()
        data = json.loads(path.read_text())
        assert data == [{"test": True}]

    def test_federation_dir_autocreated(self, tmp_path):
        new_dir = tmp_path / "new_federation"
        nadi = FederationNadi(_federation_dir=new_dir)
        assert new_dir.exists()


# ── Constants ─────────────────────────────────────────────────────────


class TestConstants:
    def test_buffer_size(self):
        assert NADI_BUFFER_SIZE == 144

    def test_federation_ttl(self):
        assert NADI_FEDERATION_TTL_S == 900.0

    def test_priority_ordering(self):
        assert TAMAS < RAJAS < SATTVA < SUDDHA
