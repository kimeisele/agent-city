"""
NODE IDENTITY — Deterministic Federation DID for this Node.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.NODE_IDENTITY")


def derive_node_id(public_key_hex: str, length: int = 16) -> str:
    digest = hashlib.sha256(str(public_key_hex).encode()).hexdigest()
    return f"ag_{digest[:length]}"


def ensure_node_identity(federation_dir: Path) -> dict:
    keys_path = federation_dir / ".node_keys.json"
    keys = _load_or_generate_keys(keys_path)
    _patch_peer_identity(federation_dir / "peer.json", keys["node_id"], keys["public_key"])
    return keys


def _load_or_generate_keys(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if data.get("private_key") and data.get("public_key"):
                if not data.get("node_id"):
                    data["node_id"] = derive_node_id(data["public_key"])
                    path.write_text(json.dumps(data, indent=2))
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return _generate_keys(path)


def _generate_keys(path: Path) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    priv_hex = sk.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption(),
    ).hex()
    pub_hex = pk.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ).hex()
    node_id = derive_node_id(pub_hex)
    payload = {"private_key": priv_hex, "public_key": pub_hex, "node_id": node_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    logger.info("Generated node identity: %s", node_id)
    return payload


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
