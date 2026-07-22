"""Injected reviewer-signing boundary for B1-S2."""

from __future__ import annotations

import base64
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class SignerError(ValueError):
    pass


class ReviewerSigner(Protocol):
    @property
    def reviewer_identity(self) -> str: ...

    @property
    def reviewer_key_id(self) -> str: ...

    def sign(self, payload: bytes) -> str: ...


class Ed25519ReviewerSigner:
    """Signer adapter requiring explicitly supplied private key material."""

    def __init__(
        self, *, reviewer_identity: str, reviewer_key_id: str, private_key: Ed25519PrivateKey
    ):
        if not reviewer_identity or not reviewer_key_id or private_key is None:
            raise SignerError("MISSING_SIGNER")
        self._reviewer_identity = reviewer_identity
        self._reviewer_key_id = reviewer_key_id
        self._private_key = private_key

    @property
    def reviewer_identity(self) -> str:
        return self._reviewer_identity

    @property
    def reviewer_key_id(self) -> str:
        return self._reviewer_key_id

    def sign(self, payload: bytes) -> str:
        if not isinstance(payload, bytes) or not payload:
            raise SignerError("INVALID_SIGNING_PAYLOAD")
        return base64.b64encode(self._private_key.sign(payload)).decode("ascii")
