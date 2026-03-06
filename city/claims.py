"""
CLAIM LEVELS — Graduated Identity Verification
================================================

Binary discovered/citizen is not enough. ClaimLevel provides
mechanical, graduated trust verification:

  DISCOVERED (0)       — Spotted on Moltbook. No claim.
  SELF_CLAIMED (1)     — Agent posted [city-claim:<name>]. Proof: post exists.
  PLATFORM_VERIFIED (2) — Challenge-response DM verified. Proof: nonce match.
  CRYPTO_VERIFIED (3)  — ECDSA signature matches pokedex public_key.

Each level = mechanical proof, no human ceremony.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("AGENT_CITY.CLAIMS")


def _claims_membrane() -> dict[str, object]:
    from city.membrane import internal_membrane_snapshot

    return internal_membrane_snapshot(source_class="claims")


class ClaimLevel(IntEnum):
    """Graduated identity verification levels."""

    DISCOVERED = 0
    SELF_CLAIMED = 1
    PLATFORM_VERIFIED = 2
    CRYPTO_VERIFIED = 3


# Pattern agents must include in a post to self-claim
CLAIM_TAG_PREFIX = "[city-claim:"
CLAIM_TAG_SUFFIX = "]"


@dataclass
class ClaimManager:
    """Manages graduated identity claims for pokedex agents.

    Stateless verifier — all persistent state lives in Pokedex (SQLite).
    Pending challenges are held in-memory (lost on restart = safe).
    """

    _pending_challenges: dict[str, str] = field(default_factory=dict)
    # agent_name → nonce

    def attempt_self_claim(
        self,
        agent_name: str,
        post_title: str,
        pokedex: object,
    ) -> bool:
        """Level 0 → 1: Agent posted with [city-claim:<agent_name>].

        Args:
            agent_name: The agent to verify.
            post_title: Full post title text to scan for claim tag.
            pokedex: Pokedex instance for level update.

        Returns:
            True if claim tag found and level upgraded.
        """
        expected_tag = f"{CLAIM_TAG_PREFIX}{agent_name}{CLAIM_TAG_SUFFIX}"
        if expected_tag not in post_title:
            return False

        current_level = pokedex.get_claim_level(agent_name)
        if current_level >= ClaimLevel.SELF_CLAIMED:
            return False  # Already at or above this level

        pokedex.update_claim_level(
            agent_name,
            ClaimLevel.SELF_CLAIMED,
            membrane=_claims_membrane(),
        )
        logger.info("SELF_CLAIMED: %s (proof: post title match)", agent_name)
        return True

    def initiate_platform_challenge(self, agent_name: str) -> str:
        """Generate a nonce for platform verification (Level 1 → 2).

        Returns the challenge nonce to send via DM.
        The agent must reply with this exact nonce.
        """
        nonce = secrets.token_hex(16)
        self._pending_challenges[agent_name] = nonce
        logger.info("Platform challenge issued to %s", agent_name)
        return nonce

    def verify_platform_response(
        self,
        agent_name: str,
        response: str,
        pokedex: object,
    ) -> bool:
        """Level 1 → 2: Agent replied with correct nonce via DM.

        Args:
            agent_name: The agent responding.
            response: The agent's DM reply text.
            pokedex: Pokedex instance for level update.

        Returns:
            True if nonce matches and level upgraded.
        """
        expected = self._pending_challenges.get(agent_name)
        if expected is None:
            logger.warning("No pending challenge for %s", agent_name)
            return False

        if expected not in response:
            logger.warning("Platform verification failed for %s: nonce mismatch", agent_name)
            return False

        del self._pending_challenges[agent_name]

        current_level = pokedex.get_claim_level(agent_name)
        if current_level >= ClaimLevel.PLATFORM_VERIFIED:
            return False

        pokedex.update_claim_level(
            agent_name,
            ClaimLevel.PLATFORM_VERIFIED,
            membrane=_claims_membrane(),
        )
        logger.info("PLATFORM_VERIFIED: %s (proof: DM nonce match)", agent_name)
        return True

    def verify_crypto_claim(
        self,
        agent_name: str,
        nonce: str,
        signature_b64: str,
        pokedex: object,
    ) -> bool:
        """Level 2 → 3: Agent signed nonce with ECDSA key matching pokedex.

        Args:
            agent_name: The agent claiming.
            nonce: The challenge nonce that was signed.
            signature_b64: Base64-encoded ECDSA signature.
            pokedex: Pokedex instance (has verify_identity + update_claim_level).

        Returns:
            True if signature valid and level upgraded.
        """
        if not pokedex.verify_identity(agent_name, nonce.encode(), signature_b64):
            logger.warning("CRYPTO_VERIFIED failed for %s: bad signature", agent_name)
            return False

        current_level = pokedex.get_claim_level(agent_name)
        if current_level >= ClaimLevel.CRYPTO_VERIFIED:
            return False

        pokedex.update_claim_level(
            agent_name,
            ClaimLevel.CRYPTO_VERIFIED,
            membrane=_claims_membrane(),
        )
        logger.info("CRYPTO_VERIFIED: %s (proof: ECDSA signature)", agent_name)
        return True

    def has_pending_challenge(self, agent_name: str) -> bool:
        """Check if an agent has a pending platform challenge."""
        return agent_name in self._pending_challenges

    def stats(self) -> dict:
        """Claim manager stats."""
        return {
            "pending_challenges": len(self._pending_challenges),
        }
