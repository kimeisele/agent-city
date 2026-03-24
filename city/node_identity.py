"""
NODE IDENTITY — Deterministic Federation DID for this Node.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.NODE_IDENTITY")


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


class NodeIdentity:
    """Deterministic Ed25519 identity for this City Node.

    Used for signing NADI federation messages to prove authenticity
    to the Steward and other peers.
    """

    def __init__(self, node_id: str, private_key_hex: str, public_key_hex: str):
        self.node_id = node_id
        self.private_key_hex = private_key_hex
        self.public_key_hex = public_key_hex

        # Pre-load keys for performance
        self._sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
        self._pk = self._sk.public_key()

    def sign(self, payload: bytes) -> str:
        """Sign payload, return hex-encoded signature."""
        return self._sk.sign(payload).hex()

    def verify(self, payload: bytes, signature_hex: str) -> bool:
        """Verify hex-encoded signature against payload."""
        from cryptography.exceptions import InvalidSignature

        try:
            self._pk.verify(bytes.fromhex(signature_hex), payload)
            return True
        except (InvalidSignature, ValueError):
            return False

    def to_dict(self) -> dict:
        """Serialize to dict (match legacy format)."""
        return {
            "node_id": self.node_id,
            "public_key": self.public_key_hex,
            "private_key": self.private_key_hex,
        }


def derive_node_id(public_key_hex: str, length: int = 16) -> str:
    digest = hashlib.sha256(str(public_key_hex).encode()).hexdigest()
    return f"ag_{digest[:length]}"


def ensure_node_identity(federation_dir: Path, override_path: Path | None = None) -> NodeIdentity:
    """Ensure node identity exists and return a NodeIdentity instance.

    If override_path is provided, it is prioritized.
    """
    if override_path and override_path.exists():
        identity = _load_identity_any_format(override_path)
        if identity:
            _patch_peer_identity(
                federation_dir / "peer.json", identity.node_id, identity.public_key_hex
            )
            return identity

    keys_path = federation_dir / ".node_keys.json"
    identity = _load_or_generate_identity(keys_path)
    _patch_peer_identity(
        federation_dir / "peer.json", identity.node_id, identity.public_key_hex
    )
    return identity


def _load_identity_any_format(path: Path) -> NodeIdentity | None:
    """Try to load identity from JSON, base64 raw, or hex raw."""
    # 1. Try JSON (.node_keys.json format)
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and data.get("private_key") and data.get("public_key"):
            node_id = data.get("node_id") or derive_node_id(data["public_key"])
            return NodeIdentity(
                node_id=node_id,
                private_key_hex=data["private_key"],
                public_key_hex=data["public_key"],
            )
    except (json.JSONDecodeError, OSError, ValueError, KeyError):
        pass

    # 2. Try raw base64 or hex
    try:
        content = path.read_text().strip()
        raw = None

        # Try base64 (standard and URL-safe)
        try:
            # Try standard first
            raw = base64.b64decode(content)
            if len(raw) != 32:
                # Try URL-safe
                raw = base64.urlsafe_b64decode(content)
            
            if len(raw) != 32:
                raw = None
        except Exception:
            # Fallback to pure URL-safe if standard threw error
            try:
                raw = base64.urlsafe_b64decode(content)
                if len(raw) != 32:
                    raw = None
            except Exception:
                raw = None

        # Try hex
        if raw is None:
            try:
                raw = bytes.fromhex(content)
                if len(raw) != 32:
                    raw = None
            except Exception:
                pass

        if raw:
            sk = Ed25519PrivateKey.from_private_bytes(raw)
            pk = sk.public_key()
            priv_hex = raw.hex()
            pub_hex = pk.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ).hex()
            return NodeIdentity(derive_node_id(pub_hex), priv_hex, pub_hex)

    except Exception as e:
        logger.warning("Failed to load raw key from %s: %s", path, e)

    return None


def _load_or_generate_identity(path: Path) -> NodeIdentity:
    identity = _load_identity_any_format(path)
    if identity:
        return identity

    return _generate_identity(path)



def _generate_identity(path: Path) -> NodeIdentity:
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    priv_hex = sk.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ).hex()
    pub_hex = pk.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    ).hex()
    node_id = derive_node_id(pub_hex)

    identity = NodeIdentity(
        node_id=node_id, private_key_hex=priv_hex, public_key_hex=pub_hex
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity.to_dict(), indent=2))
    logger.info("Generated new node identity: %s", node_id)
    return identity


def _patch_peer_identity(peer_path: Path, node_id: str, public_key: str) -> None:
    if not peer_path.exists():
        return
    try:
        data = json.loads(peer_path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    identity = data.get("identity", {})
    if identity.get("node_id") == node_id and identity.get("public_key") == public_key:
        return
    identity["node_id"] = node_id
    identity["public_key"] = public_key
    data["identity"] = identity
    peer_path.write_text(json.dumps(data, indent=2))
    logger.info("Patched peer.json with node_id=%s", node_id)

