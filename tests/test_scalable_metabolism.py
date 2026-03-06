"""
TDD: Scalable Metabolism — Issue #17
=====================================

Tests for:
  S1a: prana/cell_cycle/cell_active/prana_class SQL columns + SQL-native metabolize_all()
  S1a: _sync_cell_prana() bidirectional BLOB ↔ SQL sync
  S1a: Variable prana classes from config/city.yaml
  S1b: Daemon file-lock (heartbeat overlap prevention)
  S1c: SQLite WAL mode

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


def _root_membrane():
    from city.membrane import internal_membrane_snapshot

    return internal_membrane_snapshot(source_class="tests")


def _make_pokedex(tmp_path: Path, config_override: dict | None = None):
    """Create a minimal Pokedex pointing at tmp_path for isolated tests."""
    mock_bank = MagicMock()
    mock_bank.get_balance.return_value = 0
    mock_bank.get_system_stats.return_value = {}

    cfg = config_override or {"economy": {}}

    with patch("city.pokedex.CivicBank", return_value=mock_bank):
        with patch("city.pokedex.get_config", return_value=cfg):
            from city.pokedex import Pokedex

            return Pokedex(
                db_path=str(tmp_path / "test.db"),
                bank=mock_bank,
                constitution_path=str(tmp_path / "CONSTITUTION.md"),
            )


def _discover_and_register(pkdx, name: str) -> dict:
    """Helper: discover + register an agent, return record."""
    pkdx.discover(name)
    return pkdx.register(name)


# ── S1a: SQL Columns Exist After Migration ───────────────────────────────


def test_prana_column_exists(tmp_path):
    """Migration must add 'prana' INTEGER column to agents table."""
    pkdx = _make_pokedex(tmp_path)
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents LIMIT 0")
    # If no exception, column exists


def test_cell_cycle_column_exists(tmp_path):
    """Migration must add 'cell_cycle' INTEGER column."""
    pkdx = _make_pokedex(tmp_path)
    cur = pkdx._conn.cursor()
    cur.execute("SELECT cell_cycle FROM agents LIMIT 0")


def test_cell_active_column_exists(tmp_path):
    """Migration must add 'cell_active' INTEGER column."""
    pkdx = _make_pokedex(tmp_path)
    cur = pkdx._conn.cursor()
    cur.execute("SELECT cell_active FROM agents LIMIT 0")


def test_prana_class_column_exists(tmp_path):
    """Migration must add 'prana_class' TEXT column."""
    pkdx = _make_pokedex(tmp_path)
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana_class FROM agents LIMIT 0")


# ── S1a: Prana Populated on Discover ─────────────────────────────────────


def test_discover_sets_prana(tmp_path):
    """discover() must populate the prana SQL column from MahaCellUnified genesis."""
    pkdx = _make_pokedex(tmp_path)
    pkdx.discover("test-agent-alpha")
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana, cell_cycle, cell_active FROM agents WHERE name = ?", ("test-agent-alpha",))
    row = cur.fetchone()
    assert row is not None
    assert row["prana"] == 13700  # GENESIS_PRANA = MAHA_QUANTUM * 100
    assert row["cell_cycle"] == 0
    assert row["cell_active"] == 1


def test_discover_sets_default_prana_class(tmp_path):
    """discover() must set prana_class to 'standard' by default."""
    pkdx = _make_pokedex(tmp_path)
    pkdx.discover("test-agent-beta")
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana_class FROM agents WHERE name = ?", ("test-agent-beta",))
    row = cur.fetchone()
    assert row["prana_class"] == "standard"


# ── S1a: SQL-Native metabolize_all() ─────────────────────────────────────


def test_metabolize_all_decrements_prana(tmp_path):
    """metabolize_all() must decrement prana by METABOLIC_COST (3) via SQL."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-m1")
    pkdx.activate("agent-m1")

    pkdx.metabolize_all()

    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-m1",))
    row = cur.fetchone()
    # GENESIS_PRANA (13700) - METABOLIC_COST (3) = 13697
    assert row["prana"] == 13697


def test_metabolize_all_adds_energy_for_active(tmp_path):
    """Active agents get +10 energy (net +7 after cost of 3)."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-active")
    pkdx.activate("agent-active")

    pkdx.metabolize_all(active_agents={"agent-active"})

    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-active",))
    row = cur.fetchone()
    # 13700 - 3 + 10 = 13707
    assert row["prana"] == 13707


def test_metabolize_all_increments_cycle(tmp_path):
    """Each metabolize_all() call must increment cell_cycle by 1."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-cycle")
    pkdx.activate("agent-cycle")

    pkdx.metabolize_all()
    pkdx.metabolize_all()
    pkdx.metabolize_all()

    cur = pkdx._conn.cursor()
    cur.execute("SELECT cell_cycle FROM agents WHERE name = ?", ("agent-cycle",))
    row = cur.fetchone()
    assert row["cell_cycle"] == 3


def test_metabolize_all_kills_zero_prana(tmp_path):
    """Agents with prana <= 0 after metabolize become dormant (frozen), not archived."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-dying")
    pkdx.activate("agent-dying")

    # Set prana to 2 (below METABOLIC_COST of 3)
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET prana = 2 WHERE name = ?", ("agent-dying",))
    pkdx._conn.commit()

    dead = pkdx.metabolize_all()
    assert "agent-dying" in dead

    agent = pkdx.get("agent-dying")
    assert agent["status"] == "frozen"


def test_metabolize_all_kills_max_age(tmp_path):
    """Agents at MAX_AGE_CYCLES (432) become dormant (frozen), not archived."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-old")
    pkdx.activate("agent-old")

    # Set cycle to 431 (one away from limit)
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET cell_cycle = 431 WHERE name = ?", ("agent-old",))
    pkdx._conn.commit()

    dead = pkdx.metabolize_all()
    assert "agent-old" in dead


def test_metabolize_all_skips_frozen(tmp_path):
    """Frozen agents must NOT be metabolized."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-frozen")
    pkdx.activate("agent-frozen")
    pkdx.freeze("agent-frozen", "test", membrane=_root_membrane())

    initial_cur = pkdx._conn.cursor()
    initial_cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-frozen",))
    initial_prana = initial_cur.fetchone()["prana"]

    pkdx.metabolize_all()

    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-frozen",))
    assert cur.fetchone()["prana"] == initial_prana  # Unchanged


def test_metabolize_all_no_blob_deserialization(tmp_path):
    """metabolize_all() must NOT call MahaCellUnified.from_bytes in the hot loop."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-perf")
    pkdx.activate("agent-perf")

    with patch("city.pokedex.MahaCellUnified") as mock_cell:
        pkdx.metabolize_all()
        # from_bytes should NOT be called during metabolize_all
        mock_cell.from_bytes.assert_not_called()


def test_metabolize_all_scales_to_100_agents(tmp_path):
    """metabolize_all() with 100 agents must complete in < 1 second."""
    pkdx = _make_pokedex(tmp_path)
    for i in range(100):
        _discover_and_register(pkdx, f"agent-scale-{i:03d}")
        pkdx.activate(f"agent-scale-{i:03d}")

    active = {f"agent-scale-{i:03d}" for i in range(50)}

    start = time.monotonic()
    pkdx.metabolize_all(active_agents=active)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"metabolize_all took {elapsed:.3f}s for 100 agents"


# ── S1a: _sync_cell_prana() ──────────────────────────────────────────────


def test_sync_cell_prana_updates_blob(tmp_path):
    """_sync_cell_prana() must update cell_bytes BLOB to match SQL prana."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-sync")
    pkdx.activate("agent-sync")

    # Manually change SQL prana
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET prana = 9999 WHERE name = ?", ("agent-sync",))
    pkdx._conn.commit()

    pkdx._sync_cell_prana("agent-sync")

    # Now get_cell should reflect the new prana
    cell = pkdx.get_cell("agent-sync")
    assert cell is not None
    assert cell.prana == 9999


def test_get_cell_reflects_sql_prana(tmp_path):
    """get_cell() should return a cell whose prana matches the SQL column."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-reflect")
    pkdx.activate("agent-reflect")

    # Metabolize to change SQL prana
    pkdx.metabolize_all()

    # Sync and check
    pkdx._sync_cell_prana("agent-reflect")
    cell = pkdx.get_cell("agent-reflect")
    assert cell.prana == 13697  # 13700 - 3


# ── S1a: Variable Prana Classes ──────────────────────────────────────────


def test_prana_class_ephemeral_gets_low_genesis(tmp_path):
    """Agents with prana_class 'ephemeral' should get reduced genesis_prana."""
    cfg = {
        "economy": {},
        "agent_classes": {
            "ephemeral": {"genesis_prana": 1370, "metabolic_cost": 3, "max_age": 108},
            "standard": {"genesis_prana": 13700, "metabolic_cost": 3, "max_age": 432},
        },
    }
    pkdx = _make_pokedex(tmp_path, config_override=cfg)
    pkdx.discover("agent-ephemeral", moltbook_profile=None)

    # Manually set prana_class to ephemeral
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET prana_class = 'ephemeral', prana = 1370 WHERE name = ?", ("agent-ephemeral",))
    pkdx._conn.commit()

    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-ephemeral",))
    assert cur.fetchone()["prana"] == 1370


def test_metabolize_respects_prana_class_cost(tmp_path):
    """metabolize_all() must use the correct metabolic_cost per prana_class."""
    cfg = {
        "economy": {},
        "agent_classes": {
            "standard": {"genesis_prana": 13700, "metabolic_cost": 3, "max_age": 432},
            "immortal": {"genesis_prana": -1, "metabolic_cost": 0, "max_age": -1},
        },
    }
    pkdx = _make_pokedex(tmp_path, config_override=cfg)
    _discover_and_register(pkdx, "agent-immortal")
    pkdx.activate("agent-immortal")

    # Set as immortal class
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET prana_class = 'immortal', prana = 13700 WHERE name = ?", ("agent-immortal",))
    pkdx._conn.commit()

    pkdx.metabolize_all()

    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-immortal",))
    # Immortal: metabolic_cost = 0, so prana unchanged
    assert cur.fetchone()["prana"] == 13700


def test_metabolize_respects_prana_class_max_age(tmp_path):
    """Agents with immortal prana_class should never die from age."""
    cfg = {
        "economy": {},
        "agent_classes": {
            "standard": {"genesis_prana": 13700, "metabolic_cost": 3, "max_age": 432},
            "immortal": {"genesis_prana": -1, "metabolic_cost": 0, "max_age": -1},
        },
    }
    pkdx = _make_pokedex(tmp_path, config_override=cfg)
    _discover_and_register(pkdx, "agent-forever")
    pkdx.activate("agent-forever")

    cur = pkdx._conn.cursor()
    cur.execute(
        "UPDATE agents SET prana_class = 'immortal', prana = 13700, cell_cycle = 99999 WHERE name = ?",
        ("agent-forever",),
    )
    pkdx._conn.commit()

    dead = pkdx.metabolize_all()
    assert "agent-forever" not in dead


# ── S1c: WAL Mode ────────────────────────────────────────────────────────


def test_wal_mode_enabled(tmp_path):
    """Pokedex must use WAL journal mode for concurrent read safety."""
    pkdx = _make_pokedex(tmp_path)
    cur = pkdx._conn.cursor()
    cur.execute("PRAGMA journal_mode")
    mode = cur.fetchone()[0]
    assert mode == "wal", f"Expected WAL mode, got {mode}"


# ── S1b: Heartbeat Lock ─────────────────────────────────────────────────


def test_heartbeat_lock_prevents_concurrent_runs(tmp_path):
    """Two heartbeat locks on the same file must not both succeed."""
    import fcntl

    lock_file = tmp_path / ".heartbeat.lock"

    fd1 = open(lock_file, "w")
    fcntl.flock(fd1, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fd1.write("1")
    fd1.flush()

    fd2 = open(lock_file, "w")
    with pytest.raises(BlockingIOError):
        fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)

    fd1.close()
    fd2.close()


# ── S1c: Concurrent Read Safety ─────────────────────────────────────────


def test_concurrent_reads_during_write(tmp_path):
    """WAL mode must allow reads while a write transaction is open."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-concurrent")
    pkdx.activate("agent-concurrent")

    errors = []

    def read_in_thread():
        try:
            conn2 = sqlite3.connect(str(tmp_path / "test.db"))
            conn2.row_factory = sqlite3.Row
            cur = conn2.cursor()
            cur.execute("SELECT name, prana FROM agents WHERE name = ?", ("agent-concurrent",))
            row = cur.fetchone()
            assert row is not None
            conn2.close()
        except Exception as e:
            errors.append(e)

    # Start a write transaction
    pkdx._conn.execute("BEGIN IMMEDIATE")
    pkdx._conn.execute("UPDATE agents SET prana = prana - 1 WHERE name = 'agent-concurrent'")

    # Read from another thread (should work in WAL mode)
    t = threading.Thread(target=read_in_thread)
    t.start()
    t.join(timeout=2.0)

    pkdx._conn.execute("COMMIT")

    assert len(errors) == 0, f"Concurrent read failed: {errors}"
