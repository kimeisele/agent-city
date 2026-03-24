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

import json
import time

from dataclasses import replace
from typing import Any

from city.jiva import Jiva
from city.node_identity import NodeIdentity
from city.signal import MAX_SIGNAL_HOPS, DecodedSignal, SemanticSignal
from city.signal_encoder import encode_signal


class SignalComposer:
    """Orchestrates the construction and signing of NADI messages.

    Binds a Jiva identity (e.g. Mayor) to a NodeIdentity (City Node)
    to produce verifiable inter-repo signals.
    """

    def __init__(self, node_identity: NodeIdentity, mayor_jiva: Jiva):
        self._node_identity = node_identity
        self._mayor_jiva = mayor_jiva
        self._protocol_version = "1.0.0"

    def compose_mission_proposal(
        self, target: str, detail: str, author: str, correlation_id: str = ""
    ) -> dict:
        """Compose a signed mission proposal payload for NADI federation.

        Follows Senior Architect Mandates for protocol versioning,
        Jiva-Node binding, and cryptographic signing.
        """
        # 1. Semantic Hardening: encode text as first-class Signal
        text = f"PROPOSE MISSION: {target} | {detail}"
        signal = encode_signal(text, self._mayor_jiva, correlation_id=correlation_id)

        # 2. Construct versioned payload (Senior Architect Mandate #2)
        payload = {
            "protocol_version": self._protocol_version,
            "origin_jiva": self._mayor_jiva.name,
            "timestamp": time.time(),
            "signal": signal.to_dict(),
            "mission": {
                "target": target,
                "detail": detail,
                "author": author,
            },
        }

        # 3. Cryptographic Binding: sign the entire payload (Senior Mandate #1)
        # Sort keys to ensure deterministic serialization for signature
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        signature = self._node_identity.sign(payload_bytes)

        return {
            "payload": payload,
            "signature": signature,
            "signer_node": self._node_identity.node_id,
            "signer_key": self._node_identity.public_key_hex,
        }


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
