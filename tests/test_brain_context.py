"""
Tests for ContextSnapshot + build_context_snapshot.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from city.brain_context import (
    ContextSnapshot,
    build_context_snapshot,
    diff_snapshots,
    load_before_snapshot,
    save_before_snapshot,
)


class TestContextSnapshot:
    def test_snapshot_frozen(self):
        snap = ContextSnapshot(agent_count=10, alive_count=8)
        with pytest.raises(AttributeError):
            snap.agent_count = 99  # type: ignore[misc]

    def test_defaults(self):
        snap = ContextSnapshot()
        assert snap.agent_count == 0
        assert snap.alive_count == 0
        assert snap.chain_valid is True
        assert snap.failing_contracts == ()
        assert snap.learning_stats == {}
        assert snap.immune_stats == {}
        assert snap.council_summary == {}

    def test_to_system_context_health_check(self):
        snap = ContextSnapshot(
            agent_count=51,
            alive_count=48,
            dead_count=3,
            chain_valid=True,
            failing_contracts=("ruff_clean",),
            immune_stats={"heals_attempted": 5, "breaker_tripped": False},
            learning_stats={"synapses": 120, "avg_weight": 0.65},
        )
        ctx = snap.to_system_context("health_check")
        assert "48/51" in ctx
        assert "3 dead" in ctx
        assert "valid" in ctx
        assert "ruff_clean" in ctx
        assert "5 heal attempts" in ctx
        assert "breaker ok" in ctx
        assert "120 synapses" in ctx
        assert "action_hint" in ctx  # JSON schema included

    def test_to_system_context_reflection(self):
        snap = ContextSnapshot(
            agent_count=10,
            alive_count=9,
            recent_brain_thoughts=(
                {"thought": {"intent": "observe", "confidence": 0.7}, "heartbeat": 5},
            ),
            audit_findings_count=3,
            critical_findings=("low_prana:sys_herald",),
        )
        ctx = snap.to_system_context("reflection")
        assert "End of MURALI rotation" in ctx
        assert "hb#5" in ctx
        assert "3" in ctx  # audit findings
        assert "low_prana" in ctx
        assert "create_mission" in ctx  # JSON schema

    def test_to_system_context_comprehension(self):
        snap = ContextSnapshot(agent_count=20, alive_count=18)
        ctx = snap.to_system_context("comprehension")
        assert "18/20" in ctx
        # Should NOT have health check or reflection prompts
        assert "Evaluate" not in ctx
        assert "Reflect" not in ctx


class TestBuildContextSnapshot:
    def _make_ctx(self, **overrides) -> MagicMock:
        ctx = MagicMock()
        ctx.pokedex.stats.return_value = {"total": 51, "active": 20, "citizen": 28}
        ctx.pokedex.verify_event_chain.return_value = True
        ctx.recent_events = [{"type": "test"}]

        # Default: all services None
        type(ctx).contracts = PropertyMock(return_value=None)
        type(ctx).learning = PropertyMock(return_value=None)
        type(ctx).immune = PropertyMock(return_value=None)
        type(ctx).council = PropertyMock(return_value=None)
        type(ctx).audit = PropertyMock(return_value=None)
        type(ctx).brain_memory = PropertyMock(return_value=None)

        for key, val in overrides.items():
            setattr(type(ctx), key, PropertyMock(return_value=val))

        return ctx

    def test_build_snapshot_all_services(self):
        learning = MagicMock()
        learning.stats.return_value = {"synapses": 50, "avg_weight": 0.6}

        immune = MagicMock()
        immune.stats.return_value = {"heals_attempted": 3}

        council = MagicMock()
        council.elected_mayor = "sys_governor"
        council.member_count = 5
        council.get_open_proposals.return_value = []

        audit = MagicMock()
        audit.summary.return_value = {"total_findings": 2}
        audit.critical_findings.return_value = []

        brain_mem = MagicMock()
        brain_mem.recent.return_value = [{"thought": {}, "heartbeat": 1}]

        ctx = self._make_ctx(
            learning=learning,
            immune=immune,
            council=council,
            audit=audit,
            brain_memory=brain_mem,
        )

        snap = build_context_snapshot(ctx)
        assert snap.agent_count == 51
        assert snap.alive_count == 48
        assert snap.dead_count == 3
        assert snap.chain_valid is True
        assert snap.learning_stats["synapses"] == 50
        assert snap.immune_stats["heals_attempted"] == 3
        assert snap.council_summary["mayor"] == "sys_governor"
        assert snap.audit_findings_count == 2
        assert len(snap.recent_brain_thoughts) == 1
        assert snap.recent_events_count == 1

    def test_build_snapshot_missing_services(self):
        ctx = self._make_ctx()
        snap = build_context_snapshot(ctx)
        assert snap.agent_count == 51
        assert snap.alive_count == 48
        assert snap.learning_stats == {}
        assert snap.immune_stats == {}
        assert snap.council_summary == {}
        assert snap.failing_contracts == ()
        assert snap.recent_brain_thoughts == ()


# ── Snapshot Diffing Tests ────────────────────────────────────────────


class TestDiffSnapshots:
    def test_agent_delta(self):
        before = ContextSnapshot(agent_count=50, alive_count=45)
        after = ContextSnapshot(agent_count=52, alive_count=48)
        diff = diff_snapshots(before, after)
        assert diff["agent_delta"] == 3

    def test_chain_changed(self):
        before = ContextSnapshot(chain_valid=True)
        after = ContextSnapshot(chain_valid=False)
        diff = diff_snapshots(before, after)
        assert diff["chain_changed"] is True

    def test_failing_contracts_diff(self):
        before = ContextSnapshot(failing_contracts=("ruff_clean", "test_pass"))
        after = ContextSnapshot(failing_contracts=("test_pass", "new_contract"))
        diff = diff_snapshots(before, after)
        assert "new_contract" in diff["new_failing"]
        assert "ruff_clean" in diff["resolved"]
        assert "test_pass" not in diff["new_failing"]
        assert "test_pass" not in diff["resolved"]

    def test_learning_delta(self):
        before = ContextSnapshot(learning_stats={"synapses": 100, "avg_weight": 0.5})
        after = ContextSnapshot(learning_stats={"synapses": 120, "avg_weight": 0.55})
        diff = diff_snapshots(before, after)
        assert diff["learning_delta"]["synapse_delta"] == 20
        assert diff["learning_delta"]["weight_delta"] == 0.05


# ── Before-Snapshot Persistence Tests (Fix #1) ───────────────────────


class TestBeforeSnapshotPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        snap = ContextSnapshot(
            agent_count=51,
            alive_count=48,
            dead_count=3,
            chain_valid=True,
            failing_contracts=("test_contract",),
            learning_stats={"synapses": 100},
            venu_tick=42,
            murali_phase="KARMA",
        )
        save_before_snapshot(snap, tmp_path)
        loaded = load_before_snapshot(tmp_path)
        assert loaded is not None
        assert loaded.agent_count == 51
        assert loaded.alive_count == 48
        assert loaded.failing_contracts == ("test_contract",)
        assert loaded.venu_tick == 42
        assert loaded.murali_phase == "KARMA"

    def test_load_missing_returns_none(self, tmp_path):
        loaded = load_before_snapshot(tmp_path)
        assert loaded is None

    def test_load_cleans_up_file(self, tmp_path):
        snap = ContextSnapshot(agent_count=10)
        save_before_snapshot(snap, tmp_path)
        assert (tmp_path / "before_snapshot.json").exists()
        load_before_snapshot(tmp_path)
        # File should be deleted after load (one-shot)
        assert not (tmp_path / "before_snapshot.json").exists()

    def test_load_corrupt_file_returns_none(self, tmp_path):
        path = tmp_path / "before_snapshot.json"
        path.write_text("NOT VALID JSON{{")
        loaded = load_before_snapshot(tmp_path)
        assert loaded is None


# ── New Field Tests ───────────────────────────────────────────────────


class TestNewFields:
    def test_venu_tick_default(self):
        snap = ContextSnapshot()
        assert snap.venu_tick == 0
        assert snap.murali_phase == ""
