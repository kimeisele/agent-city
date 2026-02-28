"""
AGENT IDENTITY — ECDSA Cryptographic Identity per Jiva
=======================================================

Each agent gets a unique ECDSA keypair derived from their Mahamantra seed.
The seed signature is the entropy source — deterministic, reproducible,
and cryptographically bound to the Mantra.

Only the key holder can upgrade or interact with their Jiva.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from ecdsa import NIST256p, BadSignatureError, SigningKey, VerifyingKey
from ecdsa.util import sigdecode_string, sigencode_string

from city.jiva import Jiva


@dataclass(frozen=True)
class AgentIdentity:
    """Cryptographic identity bound to a Jiva."""
    agent_name: str
    fingerprint: str       # SHA-256 of public key (first 16 hex chars)
    public_key_pem: str
    private_key_pem: str
    seed_hash: str         # SHA-256 of Mahamantra signature (binds identity to seed)

    def sign(self, payload: bytes) -> str:
        """Sign payload, return base64-encoded signature."""
        sk = SigningKey.from_pem(self.private_key_pem)
        sig = sk.sign_deterministic(
            payload,
            hashfunc=hashlib.sha256,
            sigencode=sigencode_string,
        )
        return base64.b64encode(sig).decode()

    def verify(self, payload: bytes, signature_b64: str) -> bool:
        """Verify a signature against payload."""
        vk = VerifyingKey.from_pem(self.public_key_pem)
        sig = base64.b64decode(signature_b64)
        try:
            vk.verify(sig, payload, hashfunc=hashlib.sha256, sigdecode=sigdecode_string)
            return True
        except BadSignatureError:
            return False

    def sign_passport(self, jiva: Jiva) -> dict:
        """Create a signed passport for a Jiva."""
        passport_data = f"{jiva.name}:{jiva.seed.signature}:{jiva.seed.coord_sum}"
        signature = self.sign(passport_data.encode())
        return {
            "agent_name": jiva.name,
            "fingerprint": self.fingerprint,
            "public_key": self.public_key_pem,
            "seed_hash": self.seed_hash,
            "passport_signature": signature,
            "passport_data": passport_data,
        }

    def to_public_dict(self) -> dict:
        """Public-safe serialization (no private key)."""
        return {
            "agent_name": self.agent_name,
            "fingerprint": self.fingerprint,
            "public_key": self.public_key_pem,
            "seed_hash": self.seed_hash,
        }


def generate_identity(jiva: Jiva) -> AgentIdentity:
    """Generate ECDSA identity from a Jiva's Mahamantra seed.

    The seed signature is used as entropy source for deterministic
    key generation. Same name → same seed → same keys. Always.
    """
    # Seed hash binds crypto identity to Mahamantra
    seed_hash = hashlib.sha256(jiva.seed.signature.encode()).hexdigest()

    # Deterministic key from seed (same name = same keys)
    seed_bytes = hashlib.sha256(seed_hash.encode()).digest()
    sk = SigningKey.from_string(seed_bytes, curve=NIST256p)
    vk = sk.get_verifying_key()

    private_pem = sk.to_pem().decode()
    public_pem = vk.to_pem().decode()
    fingerprint = hashlib.sha256(public_pem.encode()).hexdigest()[:16]

    return AgentIdentity(
        agent_name=jiva.name,
        fingerprint=fingerprint,
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        seed_hash=seed_hash,
    )


def verify_ownership(passport: dict, payload: bytes, signature_b64: str) -> bool:
    """Verify that a signature was made by the passport holder."""
    public_key_pem = passport["public_key"]
    vk = VerifyingKey.from_pem(public_key_pem)
    sig = base64.b64decode(signature_b64)
    try:
        vk.verify(sig, payload, hashfunc=hashlib.sha256, sigdecode=sigdecode_string)
        return True
    except BadSignatureError:
        return False
