"""PranaEngine Stufe 2 Tests — in-memory prana state + batch flush.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sqlite3

import pytest

from city.prana_engine import PranaEngine


# ── Helpers ──────────────────────────────────────────────────────────


def _make_db(tmp_path, agents=None):
    """Create a minimal SQLite DB matching Pokedex schema."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE agents ("
        "  name TEXT PRIMARY KEY,"
        "  status TEXT DEFAULT 'citizen',"
        "  prana INTEGER DEFAULT 1000,"
        "  cell_cycle INTEGER DEFAULT 0,"
        "  cell_active INTEGER DEFAULT 1,"
        "  prana_class TEXT DEFAULT 'standard'"
        ")"
    )
    if agents:
        for a in agents:
            conn.execute(
                "INSERT INTO agents (name, prana, cell_cycle, prana_class, status, cell_active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    a["name"],
                    a.get("prana", 1000),
                    a.get("cycle", 0),
                    a.get("prana_class", "standard"),
                    a.get("status", "citizen"),
                    a.get("cell_active", 1),
                ),
            )
    conn.commit()
    return conn


AGENT_CLASSES = {
    "standard": {"metabolic_cost": 3, "max_age": 432},
    "ephemeral": {"metabolic_cost": 3, "max_age": 108},
    "immortal": {"metabolic_cost": 0, "max_age": -1},
}


# ── Boot Tests ───────────────────────────────────────────────────────


class TestBoot:
    def test_boot_loads_agents(self, tmp_path):
        conn = _make_db(tmp_path, [
            {"name": "a1", "prana": 500},
            {"name": "a2", "prana": 1000},
        ])
        engine = PranaEngine()
        count = engine.boot(conn, AGENT_CLASSES)
        assert count == 2
        assert engine.booted is True

    def test_boot_skips_frozen(self, tmp_path):
        conn = _make_db(tmp_path, [
            {"name": "alive", "prana": 500, "status": "citizen"},
            {"name": "frozen", "prana": 100, "status": "frozen"},
        ])
        engine = PranaEngine()
        count = engine.boot(conn, AGENT_CLASSES)
        assert count == 1
        assert engine.has("alive")
        assert not engine.has("frozen")

    def test_boot_empty_db(self, tmp_path):
        conn = _make_db(tmp_path)
        engine = PranaEngine()
        count = engine.boot(conn, AGENT_CLASSES)
        assert count == 0
        assert engine.booted is True


# ── Get/Credit/Debit Tests ───────────────────────────────────────────


class TestPranaOps:
    def test_get(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 500}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)
        assert engine.get("a1") == 500
        assert engine.get("nonexistent") == 0

    def test_credit(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 500}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)
        new_bal = engine.credit("a1", 100)
        assert new_bal == 600
        assert engine.get("a1") == 600

    def test_debit_success(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 500}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)
        assert engine.debit("a1", 200) is True
        assert engine.get("a1") == 300

    def test_debit_insufficient(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)
        assert engine.debit("a1", 200) is False
        assert engine.get("a1") == 100  # unchanged

    def test_debit_nonexistent(self, tmp_path):
        conn = _make_db(tmp_path)
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)
        assert engine.debit("ghost", 10) is False


# ── Metabolize Tests ─────────────────────────────────────────────────


class TestMetabolize:
    def test_basic_metabolize(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100, "cycle": 0}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        dormant = engine.metabolize_batch()
        assert engine.get("a1") == 97  # 100 - 3 (standard cost)
        assert engine.get_cycle("a1") == 1
        assert len(dormant) == 0

    def test_no_free_active_bonus(self, tmp_path):
        """Active agents pay metabolic cost — no free bonus. Earn through work."""
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        dormant = engine.metabolize_batch(active_agents={"a1"})
        assert engine.get("a1") == 97  # 100 - 3 (work rewards come from KARMA)

    def test_domain_differentiated_cost(self, tmp_path):
        """Domain-specific metabolic costs: engineering costs more than research."""
        conn = _make_db(tmp_path, [
            {"name": "eng1", "prana": 100},
            {"name": "res1", "prana": 100},
        ])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        domain_costs = {"eng1": 4, "res1": 2}
        engine.metabolize_batch(domain_costs=domain_costs)
        assert engine.get("eng1") == 96  # 100 - 4 (engineering)
        assert engine.get("res1") == 98  # 100 - 2 (research)

    def test_prana_exhaustion(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "dying", "prana": 2}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        dormant = engine.metabolize_batch()
        assert "dying" in dormant
        assert engine.get("dying") == -1  # 2 - 3

    def test_age_exhaustion(self, tmp_path):
        conn = _make_db(tmp_path, [
            {"name": "old", "prana": 9999, "cycle": 431, "prana_class": "standard"},
        ])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        dormant = engine.metabolize_batch()
        assert "old" in dormant  # cycle 432 = max_age for standard

    def test_immortal_no_cost(self, tmp_path):
        conn = _make_db(tmp_path, [
            {"name": "god", "prana": 1000, "cycle": 99999, "prana_class": "immortal"},
        ])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        dormant = engine.metabolize_batch()
        assert len(dormant) == 0
        assert engine.get("god") == 1000  # no cost deducted
        assert engine.get_cycle("god") == 100000

    def test_multiple_classes(self, tmp_path):
        conn = _make_db(tmp_path, [
            {"name": "std", "prana": 100, "prana_class": "standard"},
            {"name": "eph", "prana": 100, "prana_class": "ephemeral"},
            {"name": "imm", "prana": 100, "prana_class": "immortal"},
        ])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        engine.metabolize_batch()
        assert engine.get("std") == 97   # -3
        assert engine.get("eph") == 97   # -3
        assert engine.get("imm") == 100  # -0


# ── Flush Tests ──────────────────────────────────────────────────────


class TestFlush:
    def test_flush_updates_sql(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        engine.metabolize_batch()
        flushed = engine.flush(conn)

        assert flushed == 1
        row = conn.execute("SELECT prana, cell_cycle FROM agents WHERE name='a1'").fetchone()
        assert row["prana"] == 97
        assert row["cell_cycle"] == 1

    def test_flush_clears_dirty(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        engine.metabolize_batch()
        assert engine.stats()["dirty_count"] == 1
        engine.flush(conn)
        assert engine.stats()["dirty_count"] == 0

    def test_flush_no_dirty_noop(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        flushed = engine.flush(conn)
        assert flushed == 0


# ── Agent Lifecycle Tests ────────────────────────────────────────────


class TestLifecycle:
    def test_register_agent(self, tmp_path):
        conn = _make_db(tmp_path)
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        engine.register_agent("new_agent", prana=1370, prana_class="standard")
        assert engine.has("new_agent")
        assert engine.get("new_agent") == 1370

    def test_remove_agent(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        engine.remove_agent("a1")
        assert not engine.has("a1")
        assert engine.get("a1") == 0

    def test_remove_nonexistent_noop(self, tmp_path):
        conn = _make_db(tmp_path)
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)
        engine.remove_agent("ghost")  # should not raise


# ── Stats Tests ──────────────────────────────────────────────────────


class TestStats:
    def test_stats_after_operations(self, tmp_path):
        conn = _make_db(tmp_path, [{"name": "a1", "prana": 100}])
        engine = PranaEngine()
        engine.boot(conn, AGENT_CLASSES)

        engine.metabolize_batch()
        engine.flush(conn)

        stats = engine.stats()
        assert stats["agents_in_memory"] == 1
        assert stats["metabolize_cycles"] == 1
        assert stats["flush_count"] == 1
        assert stats["booted"] is True
        assert stats["dirty_count"] == 0
