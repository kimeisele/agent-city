"""
SEMANTIC SIGNAL — Atomic Unit of A2A Communication
====================================================

Pure data structures. Zero logic. Zero substrate deps.

A SemanticSignal carries coordinate-space encodings of text through
the RAMA phonetic substrate. Like radio — each agent tunes to its
frequency, encodes/decodes through its own coordinate space.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalCoords:
    """Coordinate-space encoding of a message."""

    rama_coordinates: tuple[int, ...]
    element_walk: tuple[int, ...]
    element_histogram: tuple[int, ...]  # 5-bin (akasha..prithvi)
    basin_set: frozenset[int]
    hkr_color: tuple[float, float, float]
    walk_direction: int  # +ascending, -descending, 0=steady
    dominant_element: int  # 0-4


@dataclass(frozen=True)
class SemanticSignal:
    """Atomic unit of A2A communication.

    The coordinate payload (coords) IS the signal.
    Everything else is sender metadata for routing + edge composition.
    """

    sender_name: str
    sender_address: int
    correlation_id: str
    coords: SignalCoords
    sender_element: int
    sender_guardian: str
    sender_chapter: int
    sender_guna: str
    sender_trinity: str
    concepts: tuple[str, ...]
    resonant_elements: tuple[str, ...]  # Element names of resonant words
    raw_text: str  # For edge composition ONLY
    priority: int  # Nadi priority (0-3)


@dataclass(frozen=True)
class RouteScore:
    """Affinity score between a signal and a candidate receiver."""

    receiver_name: str
    score: float  # [0, 1]
    element_affinity: float
    basin_affinity: float
    hkr_affinity: float
    guardian_affinity: float
    chapter_affinity: float


@dataclass(frozen=True)
class DecodedSignal:
    """Signal decoded through a receiver's Jiva lens."""

    signal: SemanticSignal
    receiver_name: str
    affinity: float  # Route score [0, 1]
    element_transitions: tuple[str, ...]  # Verb phrases (sender→receiver)
    receiver_domain: str  # Receiver's element domain name
    relative_direction: str  # "manifesting"/"resolving"/"steady"
    resonant_concepts: tuple[str, ...]  # Concepts aligned w/ receiver domain
    quality: str  # "contemplative"/"active"/"flowing"
