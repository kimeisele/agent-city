"""CityImmune Tests — Structural Self-Healing with Hebbian Learning."""

import shutil
import sys
import tempfile
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── CityImmune Unit Tests ─────────────────────────────────────────


def test_city_immune_creation():
    """CityImmune creates with ShuddhiEngine backend."""
    from city.immune import CityImmune

    immune = CityImmune()
    assert immune.available is True
    assert len(immune.list_remedies()) > 0


def test_city_immune_diagnose_known_pattern():
    """Diagnose matches known audit patterns to remedy rule_ids."""
    from city.immune import CityImmune

    immune = CityImmune()
    diagnosis = immune.diagnose("any_type usage in foo.py")
    assert diagnosis.rule_id == "any_type_usage"
    assert diagnosis.confidence == 0.5  # default (no learning yet)


def test_city_immune_diagnose_unknown_pattern():
    """Diagnose returns None rule_id for unknown patterns."""
    from city.immune import CityImmune

    immune = CityImmune()
    diagnosis = immune.diagnose("completely unknown issue xyz")
    assert diagnosis.rule_id is None
    assert diagnosis.healable is False


def test_city_immune_diagnose_with_learning():
    """Hebbian learning adjusts diagnosis confidence."""
    from city.immune import CityImmune
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")
        immune = CityImmune(_learning=learning)

        # Record repeated success for any_type_usage
        for _ in range(10):
            learning.record_outcome("immune:any_type_usage", "heal", success=True)

        diagnosis = immune.diagnose("any_type usage in test.py")
        assert diagnosis.rule_id == "any_type_usage"
        assert diagnosis.confidence > 0.7  # should have high confidence now
    finally:
        shutil.rmtree(tmp)


def test_city_immune_diagnose_low_confidence():
    """Low Hebbian confidence marks diagnosis as not healable."""
    from city.immune import CityImmune
    from city.learning import CityLearning

    tmp = Path(tempfile.mkdtemp())
    try:
        learning = CityLearning(_state_dir=tmp / "synapses")
        immune = CityImmune(_learning=learning)

        # Record repeated failures
        for _ in range(20):
            learning.record_outcome("immune:any_type_usage", "heal", success=False)

        diagnosis = immune.diagnose("any_type usage in test.py")
        assert diagnosis.confidence < 0.3  # low confidence
        assert diagnosis.healable is False  # below threshold
    finally:
        shutil.rmtree(tmp)


def test_city_immune_heal_not_healable():
    """Heal returns failure for non-healable diagnosis."""
    from city.immune import CityImmune, DiagnosisResult

    immune = CityImmune()
    diagnosis = DiagnosisResult(
        pattern="unknown pattern",
        rule_id=None,
        file_path=None,
        confidence=0.0,
        healable=False,
    )
    result = immune.heal(diagnosis)
    assert result.success is False


def test_city_immune_stats():
    """Stats reflect immune system state."""
    from city.immune import CityImmune

    immune = CityImmune()
    stats = immune.stats()
    assert stats["available"] is True
    assert "remedies" in stats
    assert stats["heals_attempted"] == 0
    assert stats["heals_succeeded"] == 0


def test_city_immune_null_fallback():
    """CityImmune with _engine=None returns safe defaults."""
    from city.immune import CityImmune

    immune = CityImmune.__new__(CityImmune)
    immune._engine = None
    immune._learning = None
    immune._available = False
    immune._heals_attempted = 0
    immune._heals_succeeded = 0

    assert immune.available is False
    assert immune.list_remedies() == []

    diagnosis = immune.diagnose("any_type in foo.py")
    assert diagnosis.healable is False

    stats = immune.stats()
    assert stats["available"] is False


def test_city_immune_scan_and_heal_empty():
    """scan_and_heal with no healable findings returns []."""
    from city.immune import CityImmune

    immune = CityImmune()
    results = immune.scan_and_heal(["unknown issue xyz"])
    assert results == []


def test_city_immune_pattern_matching():
    """All known patterns map to correct rule_ids."""
    from city.immune import _match_rule_id

    assert _match_rule_id("any_type usage in module") == "any_type_usage"
    assert _match_rule_id("hardcoded constant 42") == "hardcoded_constants"
    assert _match_rule_id("f811 redefinition of x") == "f811_redefinition"
    assert _match_rule_id("unsafe io write in base") == "unsafe_io_write"
    assert _match_rule_id("missing mahajana declaration") == "missing_mahajana"
    assert _match_rule_id("completely unknown") is None


# ── Integration with Mayor ───────────────────────────────────────


def test_mayor_with_immune():
    """Mayor with CityImmune runs full rotation."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.immune import CityImmune
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

        immune = CityImmune()

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _immune=immune,
        )

        results = mayor.run_cycle(4)
        assert len(results) == 4
    finally:
        shutil.rmtree(tmp)


def test_mayor_immune_backward_compatible():
    """Mayor with _immune=None runs without crash."""
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

        assert mayor._immune is None
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
