"""
SIGNAL DECODER — Decode signal through receiver's Jiva lens
=============================================================

Takes a SemanticSignal + receiver Jiva → DecodedSignal.
The receiver's element/domain/guardian shapes HOW the signal is read:
  - Element transitions (sender→receiver) become verb phrases
  - Receiver domain filters resonant concepts
  - Walk direction interpreted relative to receiver

Reuses semantic constants: ELEMENT_DOMAIN, _TRANSITION_VERB, _VARGA_QUALITY.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.jiva import Jiva
from city.semantic import ELEMENT_DOMAIN, _TRANSITION_VERB, _VARGA_QUALITY
from city.signal import DecodedSignal, SemanticSignal
from city.signal_router import score_route


_ELEM_NAMES: tuple[str, ...] = ("akasha", "vayu", "agni", "jala", "prithvi")


def decode_signal(signal: SemanticSignal, receiver: Jiva) -> DecodedSignal:
    """Decode signal through receiver's Jiva lens."""
    # ── Affinity score ──
    route = score_route(signal, receiver)

    # ── Receiver's element ──
    recv_elem_idx = _elem_to_int(receiver.elements.dominant)
    recv_elem_name = _ELEM_NAMES[recv_elem_idx]
    receiver_domain = ELEMENT_DOMAIN.get(recv_elem_name, "foundation")

    # ── Element transitions (sender dominant → receiver dominant) ──
    sender_idx = signal.sender_element
    transitions: list[str] = []

    # Primary transition: sender → receiver element
    if sender_idx != recv_elem_idx:
        pair = (sender_idx, recv_elem_idx)
        verb = _TRANSITION_VERB.get(pair, "moves to")
        from_domain = ELEMENT_DOMAIN.get(_ELEM_NAMES[sender_idx], "foundation")
        to_domain = receiver_domain
        transitions.append(f"{from_domain} {verb} {to_domain}")

    # Secondary transitions: signal walk endpoints → receiver element
    ewalk = signal.coords.element_walk
    if ewalk:
        last_elem = ewalk[-1]
        if last_elem != recv_elem_idx and (last_elem, recv_elem_idx) not in {
            (sender_idx, recv_elem_idx)
        }:
            pair = (last_elem, recv_elem_idx)
            verb = _TRANSITION_VERB.get(pair, "moves to")
            from_domain = ELEMENT_DOMAIN.get(
                _ELEM_NAMES[last_elem] if last_elem < 5 else "prithvi", "foundation"
            )
            transitions.append(f"{from_domain} {verb} {receiver_domain}")

    # ── Relative direction ──
    wdir = signal.coords.walk_direction
    if wdir > 1:
        relative_direction = "manifesting"
    elif wdir < -1:
        relative_direction = "resolving"
    else:
        relative_direction = "steady"

    # ── Resonant concepts aligned with receiver domain ──
    # Filter concepts that contain words from receiver's element domain
    domain_keywords = _domain_keywords(recv_elem_name)
    resonant = []
    for concept in signal.concepts:
        words = set(concept.lower().split())
        if words & domain_keywords:
            resonant.append(concept)
    # If no domain-specific hits, take first few anyway
    if not resonant:
        resonant = list(signal.concepts[:3])

    # ── Quality from dominant varga of resonant elements ──
    quality = _signal_quality(signal)

    return DecodedSignal(
        signal=signal,
        receiver_name=receiver.name,
        affinity=route.score,
        element_transitions=tuple(transitions),
        receiver_domain=receiver_domain,
        relative_direction=relative_direction,
        resonant_concepts=tuple(resonant),
        quality=quality,
    )


def _elem_to_int(name: str) -> int:
    """Element name → int index (0-4). Defaults to 4 (prithvi)."""
    try:
        return _ELEM_NAMES.index(name)
    except ValueError:
        return 4


def _domain_keywords(element: str) -> set[str]:
    """Return keywords associated with an element's semantic domain."""
    return {
        "akasha": {"observe", "monitor", "awareness", "space", "consciousness", "report"},
        "vayu": {"communicate", "relay", "message", "signal", "announce", "carry"},
        "agni": {"transform", "audit", "validate", "fire", "change", "process"},
        "jala": {"connect", "integrate", "flow", "merge", "mediate", "bridge"},
        "prithvi": {"build", "maintain", "stable", "foundation", "ground", "structure"},
    }.get(element, set())


def _signal_quality(signal: SemanticSignal) -> str:
    """Determine quality from resonant elements' implicit varga."""
    # Map element prevalence to varga-like quality
    # akasha/vayu → contemplative (svara-like), agni → active, jala/prithvi → flowing
    elem_counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
    for elem_name in signal.resonant_elements:
        idx = _elem_to_int(elem_name)
        if idx <= 1:
            elem_counts[0] += 1  # contemplative
        elif idx == 2:
            elem_counts[1] += 1  # active
        else:
            elem_counts[2] += 1  # flowing

    if not any(elem_counts.values()):
        return "steady"
    dominant = max(elem_counts, key=lambda k: elem_counts[k])
    return _VARGA_QUALITY.get(dominant, "steady")
