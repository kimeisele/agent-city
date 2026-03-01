"""
SEED CONSTANTS — Mahamantra-Derived Constants for Agent City
=============================================================

Every number in Agent City's economy and biology MUST trace back to the
Mahamantra via steward-protocol's seed.py.  This module is the SSOT bridge:
it imports the axioms and derives the operational constants.

DERIVATION CHAIN (seed.py → city):
    MAHA_QUANTUM    = 137   (α⁻¹, the fine-structure constant)
    MALA            = 108   (12 Mahajanas × 9 Nava Bhakti)
    JIVA_CYCLE      = 432   (MALA × QUARTERS)
    COSMIC_FRAME    = 21600 (Yoga: breaths per day)
    TRINITY         = 3     (Hare, Krishna, Rama)
    TEN             = 10    (MAHAJANA_COUNT − HALVES)

    genesis_prana(ephemeral)  = MAHA_QUANTUM × TEN        = 1370
    genesis_prana(standard)   = MAHA_QUANTUM × TEN²       = 13700
    genesis_prana(resilient)  = MAHA_QUANTUM × TEN³       = 137000
    metabolic_cost            = TRINITY                    = 3
    max_age(ephemeral)        = MALA                       = 108
    max_age(standard)         = JIVA_CYCLE                 = 432
    max_age(resilient)        = JIVA_CYCLE × TEN           = 4320
    genesis_grant             = MALA                       = 108
    hibernation_threshold     = MALA × NAVA                = 972
    prana_norm_max            = COSMIC_FRAME               = 21600

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from vibe_core.mahamantra.protocols import (
    MAHA_QUANTUM,
    MALA,
    NAVA,
    QUARTERS,
    TEN,
    TRINITY,
)
from vibe_core.mahamantra.protocols._seed import (
    COSMIC_FRAME,
    JIVA_CYCLE,
)

# ── Biology: Agent Classes ────────────────────────────────────────────

GENESIS_PRANA_EPHEMERAL: int = MAHA_QUANTUM * TEN          # 137 × 10   = 1370
GENESIS_PRANA_STANDARD: int  = MAHA_QUANTUM * TEN ** 2     # 137 × 100  = 13700
GENESIS_PRANA_RESILIENT: int = MAHA_QUANTUM * TEN ** 3     # 137 × 1000 = 137000

METABOLIC_COST: int = TRINITY                               # 3

MAX_AGE_EPHEMERAL: int = MALA                               # 108
MAX_AGE_STANDARD: int  = JIVA_CYCLE                         # 432
MAX_AGE_RESILIENT: int = JIVA_CYCLE * TEN                   # 4320

# ── Economy ───────────────────────────────────────────────────────────

GENESIS_GRANT: int = MALA                                   # 108 (was 100 — now Mahamantra-derived)

# ── Thresholds ────────────────────────────────────────────────────────

HIBERNATION_THRESHOLD: int = MALA * NAVA                    # 108 × 9 = 972
PRANA_NORM_MAX: int = COSMIC_FRAME                          # 21600

# ── Revival & Stipends ───────────────────────────────────────────────

REVIVE_DOSE: int = MALA * TEN                               # 108 × 10 = 1080 (above HIBERNATION_THRESHOLD)
REVIVE_COOLDOWN_CYCLES: int = MALA                          # 108 heartbeats between auto-revives per agent
WORKER_VISA_STIPEND: int = MALA // TRINITY                  # 108 / 3 = 36 (survival prana for workers)

# ── Prana Class Resolution ────────────────────────────────────────────

# Ordered thresholds: if prana >= threshold → class
# Resilient boundary = midpoint between standard and resilient genesis
# Ephemeral boundary = midpoint between ephemeral and standard genesis
_PRANA_CLASS_THRESHOLDS: list[tuple[int, str]] = [
    (GENESIS_PRANA_RESILIENT, "resilient"),                              # >= 137000
    ((GENESIS_PRANA_STANDARD + GENESIS_PRANA_RESILIENT) // 2, "resilient"),  # >= 75350
    (GENESIS_PRANA_STANDARD, "standard"),                                # >= 13700
    ((GENESIS_PRANA_EPHEMERAL + GENESIS_PRANA_STANDARD) // 2, "standard"),   # >= 7535
    (GENESIS_PRANA_EPHEMERAL, "ephemeral"),                              # >= 1370
]


def classify_prana_class(prana: int) -> str:
    """Derive prana_class from initial prana value.

    Uses threshold boundaries between the Mahamantra-derived genesis_prana
    values to find the best-fit class. Falls back to 'standard' for
    unexpected values.
    """
    if prana < 0:
        return "immortal"  # -1 sentinel
    for threshold, cls in _PRANA_CLASS_THRESHOLDS:
        if prana >= threshold:
            return cls
    return "ephemeral"  # Below all thresholds


# ── Verification (fail-fast at import time) ───────────────────────────

assert GENESIS_PRANA_EPHEMERAL == 1370,  f"ephemeral prana {GENESIS_PRANA_EPHEMERAL} != 1370"
assert GENESIS_PRANA_STANDARD  == 13700, f"standard prana {GENESIS_PRANA_STANDARD} != 13700"
assert GENESIS_PRANA_RESILIENT == 137000, f"resilient prana {GENESIS_PRANA_RESILIENT} != 137000"
assert METABOLIC_COST          == 3,     f"metabolic cost {METABOLIC_COST} != 3"
assert MAX_AGE_EPHEMERAL       == 108,   f"ephemeral max_age {MAX_AGE_EPHEMERAL} != 108"
assert MAX_AGE_STANDARD        == 432,   f"standard max_age {MAX_AGE_STANDARD} != 432"
assert MAX_AGE_RESILIENT       == 4320,  f"resilient max_age {MAX_AGE_RESILIENT} != 4320"
assert GENESIS_GRANT           == 108,   f"genesis grant {GENESIS_GRANT} != 108"
assert HIBERNATION_THRESHOLD   == 972,   f"hibernation threshold {HIBERNATION_THRESHOLD} != 972"
assert PRANA_NORM_MAX          == 21600, f"prana norm max {PRANA_NORM_MAX} != 21600"
