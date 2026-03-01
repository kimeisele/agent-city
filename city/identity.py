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
    channel: str           # The frequency channel this identity belongs to
    fingerprint: str       # SHA-256 of public key (first 16 hex chars)
    public_key_pem: str
    private_key_pem: str
    seed_hash: str         # SHA-256 of Mahamantra signature (binds identity to seed)
    gpg_fingerprint: str | None = None  # RSA 4096 or Ed25519 Fingerprint
    gpg_public_key: str | None = None   # GPG Armored Public Key
    gpg_email: str | None = None        # Email used for GPG (noreply or local)

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
            "channel": jiva.channel,
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
            "channel": self.channel,
            "fingerprint": self.fingerprint,
            "public_key": self.public_key_pem,
            "seed_hash": self.seed_hash,
        }


def generate_identity(jiva: Jiva) -> AgentIdentity:
    """Generate ECDSA identity from a Jiva's unique properties.

    Entropy chain: name + address + rama_coordinates → SHA-256 → ECDSA key.

    IMPORTANT: jiva.seed.signature is the Mahamantra sequence signature,
    which is IDENTICAL for all agents. The actual per-agent uniqueness
    comes from: name (always unique) + address (MahaCompression seed)
    + rama_coordinates (derived per name).
    """
    # Build per-agent entropy string:
    #   - name: the ONLY guaranteed-unique input across identities
    #   - channel: abstract source frequency (prevents cross-channel spoofing)
    #   - address: MahaCompression(name).seed — unique for most names
    #   - coordinates: RAMA coordinate tuple — uniqueness varies
    #   - signature: Mahamantra sequence (constant) — binds to protocol
    entropy_parts = [
        jiva.name,
        jiva.channel,
        str(jiva.address),
        str(jiva.seed.rama_coordinates),
        jiva.seed.signature,
    ]
    entropy_string = "|".join(entropy_parts)

    # Seed hash binds crypto identity to both name AND Mahamantra
    seed_hash = hashlib.sha256(entropy_string.encode()).hexdigest()

    # Deterministic key from seed (same name = same keys, always)
    seed_bytes = hashlib.sha256(seed_hash.encode()).digest()
    sk = SigningKey.from_string(seed_bytes, curve=NIST256p)
    vk = sk.get_verifying_key()

    private_pem = sk.to_pem().decode()
    public_pem = vk.to_pem().decode()
    fingerprint = hashlib.sha256(public_pem.encode()).hexdigest()[:16]

    return AgentIdentity(
        agent_name=jiva.name,
        channel=jiva.channel,
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
