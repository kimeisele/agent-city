"""
SIGNAL ENCODER — text + Jiva → SemanticSignal
===============================================

Wires existing substrate infrastructure into a deterministic signal:
  phonetic_encoder → RAMA coords
  pancha_walk → element analysis
  basin_map → basin/HKR data
  resonate() → resonant meanings
  semantic._extract_concepts() → concept phrases

Deterministic: same (text, Jiva) → same SemanticSignal, always.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import uuid

from city.jiva import Jiva
from city.signal import SemanticSignal, SignalCoords


_ELEM_NAMES: tuple[str, ...] = ("akasha", "vayu", "agni", "jala", "prithvi")


def encode_signal(
    text: str,
    sender: Jiva,
    correlation_id: str = "",
    in_reply_to: str = "",
    intent: str | None = None,
) -> SemanticSignal:
    """Encode text + sender Jiva into a SemanticSignal. Deterministic."""
    from vibe_core.mahamantra.substrate.encoding.phonetic_encoder import encode_text
    from vibe_core.mahamantra.substrate.encoding.pancha_walk import (
        element_walk,
        element_histogram,
        walk_direction,
    )
    from vibe_core.mahamantra.substrate.core.basin_map import basin_set, hkr_color
    from vibe_core.mahamantra.substrate.encoding.maha_llm_kernel import resonate

    from city.semantic import _extract_concepts
    from city.signal import SemanticIntent

    # ── RAMA coordinates ──
    rama_coords = encode_text(text)

    # ── Element analysis ──
    ewalk = element_walk(rama_coords)  # tuple[Element, ...]
    ehist = element_histogram(rama_coords)  # tuple[int, ...] (5 bins)
    wdir = walk_direction(rama_coords)  # int
    dominant = max(range(5), key=lambda i: ehist[i]) if any(ehist) else 4

    # ── Basin / HKR ──
    bset = basin_set(rama_coords)
    hkr = hkr_color(rama_coords)

    # ── Resonance → concepts + element names ──
    res = resonate(text, top_n=5)
    meanings = [w.meanings[0] for w in res.words if w.meanings and w.meanings[0]]
    concepts = tuple(_extract_concepts(meanings))
    resonant_elements = tuple(
        w.element for w in res.words if w.element
    )

    # ── Sender lens from Jiva ──
    sender_elem_idx = _elem_to_int(sender.elements.dominant)

    coords = SignalCoords(
        rama_coordinates=tuple(rama_coords),
        element_walk=tuple(int(e) for e in ewalk),
        element_histogram=tuple(ehist),
        basin_set=frozenset(bset),
        hkr_color=tuple(hkr),  # type: ignore[arg-type]
        walk_direction=wdir,
        dominant_element=dominant,
    )

    # Resolve intent
    sem_intent = SemanticIntent.MISSION_PROPOSAL
    if intent:
        try:
            sem_intent = SemanticIntent(intent)
        except ValueError:
            pass

    return SemanticSignal(
        sender_name=sender.name,
        sender_address=sender.address,
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        coords=coords,
        sender_element=sender_elem_idx,
        sender_guardian=sender.classification.guardian,
        sender_chapter=sender.classification.chapter,
        sender_guna=sender.classification.guna,
        sender_trinity=sender.classification.trinity_function,
        concepts=concepts,
        resonant_elements=resonant_elements,
        raw_text=text,
        priority=1,  # Default RAJAS
        intent=sem_intent,
        in_reply_to=in_reply_to,
    )


def _elem_to_int(name: str) -> int:
    """Element name → int index (0-4). Defaults to 4 (prithvi)."""
    try:
        return _ELEM_NAMES.index(name)
    except ValueError:
        return 4
