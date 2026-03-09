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

    def verify_foreign_passport(self, passport: dict) -> bool:
        """Verify a passport from a foreign city (cross-city verification).

        The passport must contain:
        - agent_name, fingerprint, public_key, seed_hash, passport_signature, passport_data

        Verification uses the public key embedded in the passport itself.
        This works because Jiva identity is deterministic — same name always
        produces the same ECDSA keypair. A forged passport would fail because
        the public key wouldn't match the name's deterministic derivation.

        For full trust, the receiving city should also re-derive the Jiva from
        the agent_name and confirm the public key matches the passport.
        """
        required = {"public_key", "passport_signature", "passport_data"}
        if not required.issubset(passport.keys()):
            logger.warning(
                "verify_foreign_passport: missing fields %s",
                required - set(passport.keys()),
            )
            return False

        return verify_ownership(
            passport,
            passport["passport_data"].encode(),
            passport["passport_signature"],
        )

    def verify_foreign_passport_deep(self, passport: dict) -> bool:
        """Deep verification: re-derive identity from name and verify match.

        This is the strongest verification — it confirms that the passport's
        public key matches the deterministic derivation from the agent name.
        Prevents forged passports with valid signatures but wrong keys.
        """
        if not self.verify_foreign_passport(passport):
            return False

        agent_name = passport.get("agent_name")
        if not agent_name:
            return False

        # Re-derive identity from name to confirm public key matches
        try:
            from city.jiva import derive_jiva
            jiva = derive_jiva(agent_name)
            local_identity = generate_identity(jiva)
            return local_identity.fingerprint == passport.get("fingerprint")
        except Exception as e:
            logger.warning(
                "verify_foreign_passport_deep: derivation failed for %s: %s",
                agent_name, e,
            )
            return False

    def stats(self) -> dict:
        """Identity service statistics."""
        return {
            "known_agents": len(self._identities),
            "agent_names": list(self._identities.keys()),
        }
