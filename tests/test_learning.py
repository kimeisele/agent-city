"""CityLearning Tests — Hebbian Cross-Session Memory."""

import shutil
import sys
import tempfile
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── CityLearning Unit Tests ───────────────────────────────────────


def test_city_learning_creation():
    """CityLearning creates with HebbianSynaptic backend."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")
        assert learning.available is True
    finally:
        shutil.rmtree(tmp)


def test_city_learning_record_outcome():
    """Record success/failure updates weights."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")

        # Default weight is 0.5
        assert learning.get_confidence("dm", "process") == 0.5

        # Success increases weight
        w = learning.record_outcome("dm", "process", success=True)
        assert w > 0.5

        # Failure decreases weight
        w2 = learning.record_outcome("feed", "process", success=False)
        assert w2 < 0.5
    finally:
        shutil.rmtree(tmp)


def test_city_learning_hebbian_convergence():
    """Repeated success converges toward 1.0, failure toward 0.0."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")

        # 20 successes → high confidence
        for _ in range(20):
            learning.record_outcome("dm", "reply", success=True)
        assert learning.get_confidence("dm", "reply") > 0.85

        # 20 failures on different pair → low confidence
        for _ in range(20):
            learning.record_outcome("feed", "heal", success=False)
        assert learning.get_confidence("feed", "heal") < 0.15
    finally:
        shutil.rmtree(tmp)


def test_city_learning_persistence():
    """Weights survive flush + reload."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        state_dir = tmp / "synapses"

        # Session 1: learn something
        learning1 = CityLearning(_state_dir=state_dir)
        learning1.record_outcome("dm", "reply", success=True)
        learning1.record_outcome("dm", "reply", success=True)
        learning1.flush()

        # Session 2: weights survive
        learning2 = CityLearning(_state_dir=state_dir)
        w = learning2.get_confidence("dm", "reply")
        assert w > 0.5, f"Expected weight > 0.5 after 2 successes, got {w}"
    finally:
        shutil.rmtree(tmp)


def test_city_learning_stats():
    """Stats reflect synapse state."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")

        # Empty stats
        stats = learning.stats()
        assert stats.get("synapses", 0) == 0

        # Record some outcomes
        learning.record_outcome("dm", "reply", success=True)
        learning.record_outcome("feed", "process", success=False)

        stats = learning.stats()
        assert stats["synapses"] == 2
        assert "avg_weight" in stats
        assert "strongest" in stats
        assert "weakest" in stats
    finally:
        shutil.rmtree(tmp)


def test_city_learning_flush_idempotent():
    """Flush with no changes is safe."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")
        # Flush with no changes — should not crash
        learning.flush()
        learning.flush()
    finally:
        shutil.rmtree(tmp)


def test_city_learning_null_fallback():
    """CityLearning with _synaptic=None returns safe defaults."""
    from city.learning import CityLearning

    learning = CityLearning.__new__(CityLearning)
    learning._synaptic = None
    learning._state_dir = Path("/tmp/unused")

    assert learning.available is False
    assert learning.get_confidence("dm", "reply") == 0.5
    assert learning.record_outcome("dm", "reply", success=True) == 0.5
    learning.flush()  # no crash
    assert learning.stats() == {}


def test_city_learning_multiple_pairs():
    """Different trigger→action pairs track independently."""
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")

        learning.record_outcome("dm", "reply", success=True)
        learning.record_outcome("feed", "process", success=False)
        learning.record_outcome("submolt", "heal", success=True)

        assert learning.get_confidence("dm", "reply") > 0.5
        assert learning.get_confidence("feed", "process") < 0.5
        assert learning.get_confidence("submolt", "heal") > 0.5
    finally:
        shutil.rmtree(tmp)


# ── Integration with Mayor ───────────────────────────────────────


def test_mayor_with_learning():
    """Mayor with CityLearning runs without crash."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.learning import CityLearning
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

        learning = CityLearning(_state_dir=tmp / "synapses")

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _learning=learning,
        )

        assert mayor._learning is not None
        assert mayor._learning.available is True

        # Full rotation — no crash
        results = mayor.run_cycle(4)
        assert len(results) == 4
    finally:
        shutil.rmtree(tmp)


def test_mayor_learning_backward_compatible():
    """Mayor with _learning=None runs without crash."""
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

        assert mayor._learning is None

        # Full rotation — no crash
        results = mayor.run_cycle(4)
        assert len(results) == 4
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
