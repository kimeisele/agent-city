"""
SIGNAL COMPOSER — Compose Response Signals
=============================================

Closes the A2A loop: Agent receives a DecodedSignal, composes a reply
SemanticSignal through its own Jiva's RAMA coordinate space.

Hop counter prevents infinite ping-pong between high-affinity agents.
correlation_id is preserved to maintain reply chains.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from dataclasses import replace

from city.jiva import Jiva
from city.signal import MAX_SIGNAL_HOPS, DecodedSignal, SemanticSignal
from city.signal_encoder import encode_signal


def compose_response_signal(
    decoded: DecodedSignal,
    responder: Jiva,
) -> SemanticSignal | None:
    """Compose a reply signal from a DecodedSignal through the responder's Jiva.

    Returns None if hop limit reached (hard stop against ping-pong storms).
    The response is encoded through the responder's RAMA coordinate space.
    correlation_id is preserved from the inbound signal (reply chain).
    """
    if decoded.signal.hop_count >= MAX_SIGNAL_HOPS:
        return None

    # Build response text from decoded concepts + responder domain
    concepts = ", ".join(decoded.resonant_concepts[:3]) or "acknowledged"
    transitions = (
        " → ".join(decoded.element_transitions[:2])
        if decoded.element_transitions
        else ""
    )
    response_text = f"{decoded.receiver_domain}: {concepts}"
    if transitions:
        response_text += f" | {transitions}"

    # Encode through responder's RAMA space (preserves correlation chain)
    signal = encode_signal(
        response_text,
        responder,
        correlation_id=decoded.signal.correlation_id,
    )

    # Increment hop count (frozen dataclass → rebuild)
    return replace(signal, hop_count=decoded.signal.hop_count + 1)
