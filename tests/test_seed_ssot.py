"""
TEST SEED SSOT — Verify Agent City constants trace back to the Mahamantra.
===========================================================================

Every number in config/city.yaml and the codebase must be derivable from
steward-protocol's seed.py.  This test catches drift before it ships.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.seed_constants import (
    GENESIS_GRANT,
    GENESIS_PRANA_EPHEMERAL,
    GENESIS_PRANA_RESILIENT,
    GENESIS_PRANA_STANDARD,
    HIBERNATION_THRESHOLD,
    MAX_AGE_EPHEMERAL,
    MAX_AGE_RESILIENT,
    MAX_AGE_STANDARD,
    METABOLIC_COST,
    PRANA_NORM_MAX,
    classify_prana_class,
)
from config import get_config


# ── city.yaml vs seed_constants ──────────────────────────────────────


class TestAgentClassesSSOT:
    """Verify agent_classes in city.yaml match Mahamantra derivations."""

    @pytest.fixture(autouse=True)
    def _load_config(self):
        self.cfg = get_config().get("agent_classes", {})

    def test_ephemeral_genesis_prana(self):
        assert self.cfg["ephemeral"]["genesis_prana"] == GENESIS_PRANA_EPHEMERAL

    def test_standard_genesis_prana(self):
        assert self.cfg["standard"]["genesis_prana"] == GENESIS_PRANA_STANDARD

    def test_resilient_genesis_prana(self):
        assert self.cfg["resilient"]["genesis_prana"] == GENESIS_PRANA_RESILIENT

    def test_ephemeral_max_age(self):
        assert self.cfg["ephemeral"]["max_age"] == MAX_AGE_EPHEMERAL

    def test_standard_max_age(self):
        assert self.cfg["standard"]["max_age"] == MAX_AGE_STANDARD

    def test_resilient_max_age(self):
        assert self.cfg["resilient"]["max_age"] == MAX_AGE_RESILIENT

    def test_metabolic_cost_all_classes(self):
        """All non-immortal classes must use TRINITY as metabolic cost."""
        for cls_name in ("ephemeral", "standard", "resilient"):
            assert self.cfg[cls_name]["metabolic_cost"] == METABOLIC_COST, (
                f"{cls_name} metabolic_cost != TRINITY ({METABOLIC_COST})"
            )

    def test_immortal_no_cost(self):
        assert self.cfg["immortal"]["metabolic_cost"] == 0
        assert self.cfg["immortal"]["max_age"] == -1
        assert self.cfg["immortal"]["genesis_prana"] == -1


class TestEconomySSOT:
    """Verify economy constants derive from Mahamantra."""

    def test_genesis_grant_is_mala(self):
        """genesis_grant must equal MALA (108), not arbitrary 100."""
        cfg = get_config().get("economy", {})
        assert cfg["genesis_grant"] == GENESIS_GRANT, (
            f"genesis_grant {cfg['genesis_grant']} != MALA-derived {GENESIS_GRANT}"
        )


class TestThresholdsSSOT:
    """Verify operational thresholds derive from Mahamantra."""

    def test_hibernation_threshold(self):
        """MALA × NAVA = 972 (not arbitrary 1000)."""
        assert HIBERNATION_THRESHOLD == 972

    def test_prana_norm_max_is_cosmic_frame(self):
        """Election prana normalization must use COSMIC_FRAME (21600)."""
        assert PRANA_NORM_MAX == 21600


class TestDerivationChain:
    """Verify the derivation chain from Mahamantra axioms."""

    def test_genesis_prana_scaling(self):
        """genesis_prana scales by powers of TEN from MAHA_QUANTUM."""
        from vibe_core.mahamantra.protocols import MAHA_QUANTUM, TEN

        assert GENESIS_PRANA_EPHEMERAL == MAHA_QUANTUM * TEN
        assert GENESIS_PRANA_STANDARD == MAHA_QUANTUM * TEN ** 2
        assert GENESIS_PRANA_RESILIENT == MAHA_QUANTUM * TEN ** 3

    def test_max_age_derivation(self):
        """max_age derives from MALA and JIVA_CYCLE."""
        from vibe_core.mahamantra.protocols import MALA, TEN
        from vibe_core.mahamantra.protocols._seed import JIVA_CYCLE

        assert MAX_AGE_EPHEMERAL == MALA
        assert MAX_AGE_STANDARD == JIVA_CYCLE
        assert MAX_AGE_RESILIENT == JIVA_CYCLE * TEN

    def test_metabolic_cost_is_trinity(self):
        from vibe_core.mahamantra.protocols import TRINITY

        assert METABOLIC_COST == TRINITY

    def test_genesis_grant_is_mala(self):
        from vibe_core.mahamantra.protocols import MALA

        assert GENESIS_GRANT == MALA


class TestClassifyPranaClass:
    """Verify prana_class derivation from VM prana values."""

    def test_exact_ephemeral(self):
        assert classify_prana_class(1370) == "ephemeral"

    def test_exact_standard(self):
        assert classify_prana_class(13700) == "standard"

    def test_exact_resilient(self):
        assert classify_prana_class(137000) == "resilient"

    def test_immortal_sentinel(self):
        assert classify_prana_class(-1) == "immortal"

    def test_below_ephemeral(self):
        assert classify_prana_class(500) == "ephemeral"

    def test_between_ephemeral_and_standard(self):
        assert classify_prana_class(5000) == "ephemeral"

    def test_between_standard_and_resilient(self):
        assert classify_prana_class(50000) == "standard"

    def test_above_resilient(self):
        assert classify_prana_class(200000) == "resilient"

    def test_zero_prana(self):
        assert classify_prana_class(0) == "ephemeral"
