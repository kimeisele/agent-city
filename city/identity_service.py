"""
IDENTITY SERVICE — ECDSA Verification for Governance
======================================================

Wraps city.identity with lookup + verification.
Wired into council votes and PR attestation.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from city.identity import AgentIdentity, generate_identity, verify_ownership

logger = logging.getLogger("AGENT_CITY.IDENTITY_SERVICE")


@dataclass
class IdentityService:
    """Manages agent identities and cryptographic verification.

    Caches identities per agent. Provides sign/verify for governance.
    """

    _identities: dict[str, AgentIdentity] = field(default_factory=dict)

    def get_or_create(self, jiva: object) -> AgentIdentity:
        """Get cached identity or generate a new one for a Jiva."""
        name = jiva.name
        if name not in self._identities:
            identity = generate_identity(jiva)
            self._identities[name] = identity
            logger.info(
                "Identity created for %s (fingerprint=%s)",
                name,
                identity.fingerprint,
            )
        return self._identities[name]

    def verify_agent(self, agent_name: str, payload: bytes, signature_b64: str) -> bool:
        """Verify a signature from a known agent.

        Returns False if agent not found or signature invalid.
        """
        identity = self._identities.get(agent_name)
        if identity is None:
            logger.warning("verify_agent: unknown agent %s", agent_name)
            return False
        return identity.verify(payload, signature_b64)

    def sign_as_agent(self, agent_name: str, payload: bytes) -> str | None:
        """Sign payload as an agent. Returns base64 signature or None."""
        identity = self._identities.get(agent_name)
        if identity is None:
            logger.warning("sign_as_agent: unknown agent %s", agent_name)
            return None
        return identity.sign(payload)

    def get_passport(self, agent_name: str, jiva: object) -> dict | None:
        """Get a signed passport for an agent.

        Creates identity if needed.
        """
        identity = self.get_or_create(jiva)
        return identity.sign_passport(jiva)

    def get_public_key(self, agent_name: str) -> str | None:
        """Get the public key PEM for a known agent."""
        identity = self._identities.get(agent_name)
        if identity is None:
            return None
        return identity.public_key_pem

    def verify_passport(self, passport: dict, payload: bytes, signature_b64: str) -> bool:
        """Verify a passport signature (stateless — uses public key from passport)."""
        return verify_ownership(passport, payload, signature_b64)

    def stats(self) -> dict:
        """Identity service statistics."""
        return {
            "known_agents": len(self._identities),
            "agent_names": list(self._identities.keys()),
        }
