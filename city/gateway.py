"""
GOVARDHAN GATEWAY — The City Wall
===================================

ALL external input passes through MahaCompression before touching internal state.
This IS the security boundary.

Wired from steward-protocol:
- MahaCompression — sanitize input (any string → seed)
- Buddhi.think() — cognitive frame before routing
- MahaHeader — 72-byte routing header

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TypedDict

from vibe_core.mahamantra.adapters.compression import MahaCompression
from vibe_core.mahamantra.substrate.buddhi import get_buddhi

from city.addressing import CityAddressBook

logger = logging.getLogger("AGENT_CITY.GATEWAY")


class GatewayResult(TypedDict):
    """Result of processing input through the gateway."""
    seed: int
    source: str
    source_address: int
    buddhi_function: str
    buddhi_chapter: int
    buddhi_mode: str
    buddhi_prana: int
    buddhi_is_alive: bool
    compressed_size: int
    input_size: int


@dataclass
class CityGateway:
    """Single entry point for ALL external input.

    Compress → Buddhi.think → Address Resolution.
    Nothing touches internal state without passing through here.
    """

    _address_book: CityAddressBook = field(default_factory=CityAddressBook)
    _compression: MahaCompression = field(default_factory=MahaCompression)
    _processed_count: int = 0

    @property
    def address_book(self) -> CityAddressBook:
        return self._address_book

    def process(self, input_text: str, source: str) -> GatewayResult:
        """Process external input through the gateway.

        Pipeline: Compress → Buddhi.think → Address Resolution.
        """
        # Step 1: MahaCompression — sanitize input to deterministic seed
        compressed = self._compression.compress(input_text)

        # Step 2: Buddhi — cognitive frame (what is this input about?)
        buddhi = get_buddhi()
        cognition = buddhi.think(input_text)

        # Step 3: Address resolution
        source_address = self._address_book.resolve(source)

        self._processed_count += 1

        result: GatewayResult = {
            "seed": compressed.seed,
            "source": source,
            "source_address": source_address,
            "buddhi_function": cognition.function,
            "buddhi_chapter": cognition.chapter,
            "buddhi_mode": cognition.mode,
            "buddhi_prana": cognition.prana,
            "buddhi_is_alive": cognition.is_alive,
            "compressed_size": compressed.output_size,
            "input_size": compressed.input_size,
        }

        logger.debug(
            "Gateway processed input from %s: seed=%d, function=%s, chapter=%d",
            source, compressed.seed, cognition.function, cognition.chapter,
        )
        return result

    def validate_agent_message(
        self, from_agent: str, payload: bytes, signature_b64: str, public_key_pem: str,
    ) -> bool:
        """Verify ECDSA signature for agent-to-agent messages.

        Uses the agent's public key from the Pokedex to verify.
        """
        from ecdsa import BadSignatureError, VerifyingKey
        from ecdsa.util import sigdecode_string
        import base64
        import hashlib

        try:
            vk = VerifyingKey.from_pem(public_key_pem)
            sig = base64.b64decode(signature_b64)
            vk.verify(sig, payload, hashfunc=hashlib.sha256, sigdecode=sigdecode_string)
            return True
        except (BadSignatureError, Exception):
            logger.warning("Invalid signature from %s", from_agent)
            return False

    def stats(self) -> dict:
        """Gateway statistics."""
        return {
            "processed": self._processed_count,
            "address_book": self._address_book.stats(),
        }
