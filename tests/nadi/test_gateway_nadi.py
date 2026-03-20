"""Nadi Hub Tests — Structured Gateway Messaging."""

import shutil
import sys
import tempfile
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── CityNadi Unit Tests ──────────────────────────────────────────


def test_city_nadi_creation():
    """CityNadi creates with LocalNadi backend."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi()
    assert nadi._endpoint_id == "city_gateway"
    assert nadi.pending_count() == 0


def test_city_nadi_enqueue_dequeue():
    """Basic enqueue → drain cycle."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_enqueue")
    result = nadi.enqueue("dm", "hello world", from_agent="alice")
    assert result is True
    assert nadi.pending_count() == 1

    items = nadi.drain()
    assert len(items) == 1
    assert items[0]["source"] == "dm"
    assert items[0]["text"] == "hello world"
    assert items[0]["from_agent"] == "alice"

    # Drained — should be empty now
    assert nadi.pending_count() == 0
    assert nadi.drain() == []


def test_city_nadi_priority_sorting():
    """Higher priority messages come first in drain."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_priority")

    # Enqueue in wrong order: low, high, medium
    nadi.enqueue("feed", "low priority", priority=0)      # TAMAS
    nadi.enqueue("dm", "high priority", priority=3)        # SUDDHA
    nadi.enqueue("submolt", "medium priority", priority=1) # RAJAS

    items = nadi.drain()
    assert len(items) == 3
    # Highest priority first
    assert items[0]["text"] == "high priority"
    assert items[1]["text"] == "medium priority"
    assert items[2]["text"] == "low priority"


def test_city_nadi_dm_gets_suddha_priority():
    """DMs automatically get SUDDHA (critical) priority."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_dm_priority")

    nadi.enqueue("feed", "low importance")
    nadi.enqueue("dm", "urgent DM", from_agent="bob", conversation_id="conv123")

    items = nadi.drain()
    assert len(items) == 2
    # DM should come first (SUDDHA > RAJAS)
    assert items[0]["text"] == "urgent DM"
    assert items[0]["conversation_id"] == "conv123"


def test_city_nadi_code_signals_get_sattva():
    """Submolt code signals get SATTVA (important) priority."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_code_priority")

    nadi.enqueue("feed", "regular post")
    nadi.enqueue(
        "submolt", "Fix regression bug",
        code_signals=["fix", "regression"],
        post_id="p1",
    )

    items = nadi.drain()
    assert len(items) == 2
    # Code signal should come first (SATTVA > RAJAS)
    assert items[0]["text"] == "Fix regression bug"
    assert items[0]["code_signals"] == ["fix", "regression"]
    assert items[0]["post_id"] == "p1"


def test_city_nadi_preserves_conversation_id():
    """Correlation IDs preserved for DM request/response."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_correlation")

    nadi.enqueue(
        "dm", "What's my status?",
        conversation_id="conv_abc",
        from_agent="alice",
    )

    items = nadi.drain()
    assert len(items) == 1
    assert items[0]["conversation_id"] == "conv_abc"
    assert items[0]["from_agent"] == "alice"


def test_city_nadi_preserves_extra_payload():
    """Arbitrary membrane metadata survives enqueue → drain."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_extra_payload")
    nadi.enqueue(
        "discussion",
        "hello",
        extra_payload={
            "comment_id": "comment_1",
            "membrane": {"surface": "github_discussion"},
        },
    )

    items = nadi.drain()
    assert items[0]["comment_id"] == "comment_1"
    assert items[0]["membrane"]["surface"] == "github_discussion"


def test_city_nadi_stats():
    """Stats reflect message counts."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_stats")
    nadi.enqueue("dm", "msg1")
    nadi.enqueue("dm", "msg2")

    stats = nadi.stats()
    assert stats["pending"] == 2
    assert stats["endpoint"] == "test_stats"


def test_city_nadi_empty_drain():
    """Drain on empty nadi returns []."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi(_endpoint_id="test_empty")
    assert nadi.drain() == []
    assert nadi.pending_count() == 0


def test_city_nadi_none_fallback():
    """CityNadi with _nadi=None returns safe defaults."""
    from city.nadi_hub import CityNadi

    nadi = CityNadi.__new__(CityNadi)
    nadi._nadi = None
    nadi._endpoint_id = "null_test"

    assert nadi.enqueue("dm", "hello") is False
    assert nadi.drain() == []
    assert nadi.pending_count() == 0
    assert nadi.stats() == {}


# ── Integration with Mayor ───────────────────────────────────────


def test_mayor_nadi_backward_compatible():
    """Mayor with city_nadi=None runs without crash (old gateway_queue)."""
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

        assert mayor._city_nadi is None

        # Full rotation — no crash
        results = mayor.run_cycle(4)
        assert len(results) == 4
    finally:
        shutil.rmtree(tmp)


def test_mayor_with_nadi():
    """Mayor with CityNadi routes messages through Nadi."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.nadi_hub import CityNadi
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

        city_nadi = CityNadi(_endpoint_id="test_mayor_nadi")

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _city_nadi=city_nadi,
        )

        # Enqueue a message before KARMA phase
        mayor.enqueue("test", "process this", from_agent="tester")

        # Run one MURALI heartbeat (all phases in one)
        results = mayor.run_cycle(1)
        assert len(results) == 1

        # MURALI heartbeat processes the queued item
        murali = results[0]
        assert murali["department"] == "MURALI"
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
