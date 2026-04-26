#!/usr/bin/env python3
"""verify_local_heartbeat.py — round-trip self-test for the canonical wire format.

Generates a fake heartbeat, signs it via FederationRelay._sign_payload, then
verifies it byte-for-byte using the same primitives steward.federation_crypto
uses on the receiver side. Exit 0 on success, non-zero on mismatch.

This is a CI/dev guardrail to make sure agent-city's outbound format never
drifts from the verifier in steward. Run it locally before pushing changes
to federation.py:

    NODE_PRIVATE_KEY=<hex32> python3 scripts/verify_local_heartbeat.py

If NODE_PRIVATE_KEY is unset, an ephemeral key is generated for the test.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _ensure_env_key() -> tuple[str, str]:
    """Return (private_hex, public_hex). Generate ephemeral if env unset."""
    env = (os.environ.get("NODE_PRIVATE_KEY") or "").strip()
    if env:
        raw = bytes.fromhex(env)
        if len(raw) != 32:
            raise SystemExit("NODE_PRIVATE_KEY must decode to 32 bytes")
        sk = Ed25519PrivateKey.from_private_bytes(raw)
    else:
        sk = Ed25519PrivateKey.generate()
        raw = sk.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        os.environ["NODE_PRIVATE_KEY"] = raw.hex()
    pub = sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return raw.hex(), pub.hex()


def _verify_steward_side(public_key_hex: str, payload_hash: str, signature_b64: str) -> bool:
    """Mirror of steward.federation_crypto.verify_payload_signature."""
    try:
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pk.verify(base64.b64decode(signature_b64.encode()), payload_hash.encode())
        return True
    except Exception:
        return False


def main() -> int:
    _, public_hex = _ensure_env_key()

    from city.federation import FederationRelay

    relay = FederationRelay()
    heartbeat = {
        "operation": "heartbeat",
        "source": "ag_test",
        "timestamp": 1700000000.0,
        "heartbeat": 1,
        "agent_id": "agent-city",
        "node_id": "ag_test",
        "population": 0,
        "alive": 0,
        "dead": 0,
    }
    signed = relay._sign_payload(heartbeat)

    required = {"payload_hash", "signature"}
    missing = required - set(signed.keys())
    if missing:
        print(f"FAIL: signed message missing fields: {missing}", file=sys.stderr)
        return 1

    canonical = {k: v for k, v in signed.items() if k not in required}
    expected_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if signed["payload_hash"] != expected_hash:
        print("FAIL: payload_hash mismatch", file=sys.stderr)
        print(f"  got      : {signed['payload_hash']}", file=sys.stderr)
        print(f"  expected : {expected_hash}", file=sys.stderr)
        return 2

    try:
        base64.b64decode(signed["signature"].encode(), validate=True)
    except Exception as e:
        print(f"FAIL: signature is not valid base64: {e}", file=sys.stderr)
        return 3

    if not _verify_steward_side(public_hex, signed["payload_hash"], signed["signature"]):
        print("FAIL: receiver-side verification rejected signature", file=sys.stderr)
        return 4

    print("OK: signed heartbeat round-trips through steward verify_payload_signature")
    print(f"  payload_hash = {signed['payload_hash']}")
    print(f"  signature    = {signed['signature'][:32]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
