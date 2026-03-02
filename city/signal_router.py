"""
SIGNAL ROUTER — 5-Dimensional Coordinate-Space Routing
========================================================

Routes a SemanticSignal to the best-fitting receiver agents based on
5 coordinate-space affinities:

    0.30 — element histogram similarity (walk_distance)
    0.25 — basin Jaccard overlap (basin_jaccard)
    0.20 — HKR color similarity (hkr_similarity)
    0.15 — guardian compatibility (same quarter → bonus)
    0.10 — chapter proximity (1 - |ch_a - ch_b| / 18)

Pure math. No LLM. No heuristics beyond the 5 weights.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.jiva import Jiva
from city.signal import RouteScore, SemanticSignal

# ── Quarter lookup (guardian → quarter) ──────────────────────────────
_GUARDIAN_QUARTER: dict[str, str] = {
    "vyasa": "genesis", "brahma": "genesis", "narada": "genesis", "shambhu": "genesis",
    "prithu": "dharma", "kumaras": "dharma", "kapila": "dharma", "manu": "dharma",
    "parashurama": "karma", "prahlada": "karma", "janaka": "karma", "bhishma": "karma",
    "nrisimha": "moksha", "bali": "moksha", "shuka": "moksha", "yamaraja": "moksha",
}

# ── Routing weights ──────────────────────────────────────────────────
W_ELEMENT = 0.30
W_BASIN = 0.25
W_HKR = 0.20
W_GUARDIAN = 0.15
W_CHAPTER = 0.10


def score_route(signal: SemanticSignal, receiver: Jiva) -> RouteScore:
    """5-dimensional coordinate-space affinity scoring."""
    from vibe_core.mahamantra.substrate.encoding.pancha_walk import walk_distance
    from vibe_core.mahamantra.substrate.core.basin_map import (
        basin_jaccard,
        hkr_similarity,
    )

    # Receiver's RAMA coords from Jiva seed
    recv_coords = receiver.seed.rama_coordinates

    # ── Element histogram distance → similarity ──
    elem_sim = 1.0 - walk_distance(signal.coords.rama_coordinates, recv_coords)

    # ── Basin Jaccard overlap ──
    basin_sim = basin_jaccard(signal.coords.rama_coordinates, recv_coords)

    # ── HKR color similarity ──
    hkr_sim = hkr_similarity(signal.coords.rama_coordinates, recv_coords)

    # ── Guardian compatibility (same quarter = 1.0, else 0.0) ──
    sender_quarter = _GUARDIAN_QUARTER.get(signal.sender_guardian, "")
    receiver_quarter = _GUARDIAN_QUARTER.get(receiver.classification.guardian, "")
    guardian_sim = 1.0 if sender_quarter == receiver_quarter and sender_quarter else 0.0

    # ── Chapter proximity ──
    chapter_dist = abs(signal.sender_chapter - receiver.classification.chapter)
    chapter_sim = 1.0 - (chapter_dist / 18.0)

    # ── Weighted score ──
    total = (
        W_ELEMENT * elem_sim
        + W_BASIN * basin_sim
        + W_HKR * hkr_sim
        + W_GUARDIAN * guardian_sim
        + W_CHAPTER * chapter_sim
    )

    return RouteScore(
        receiver_name=receiver.name,
        score=total,
        element_affinity=elem_sim,
        basin_affinity=basin_sim,
        hkr_affinity=hkr_sim,
        guardian_affinity=guardian_sim,
        chapter_affinity=chapter_sim,
    )


def route_signal(
    signal: SemanticSignal,
    candidates: dict[str, Jiva],
    top_n: int = 3,
) -> list[RouteScore]:
    """Route signal to best-fitting agents.

    Returns top_n RouteScores sorted by score descending.
    Excludes the sender from candidates.
    """
    scores = []
    for name, jiva in candidates.items():
        if name == signal.sender_name:
            continue
        scores.append(score_route(signal, jiva))

    scores.sort(key=lambda r: r.score, reverse=True)
    return scores[:top_n]
