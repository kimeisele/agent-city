"""
Tests for D4: Identity Verification Service — ECDSA into governance.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.identity_service import IdentityService


def _make_jiva(name: str = "TestAgent"):
    """Create a Jiva via derive_jiva (the correct factory)."""
    from city.jiva import derive_jiva

    return derive_jiva(name)


def test_get_or_create():
    """get_or_create generates and caches an identity."""
    svc = IdentityService()
    jiva = _make_jiva("alice")
    identity = svc.get_or_create(jiva)

    assert identity.agent_name == "alice"
    assert identity.fingerprint
    assert len(identity.fingerprint) == 16

    # Second call returns cached
    identity2 = svc.get_or_create(jiva)
    assert identity2 is identity


def test_sign_and_verify():
    """sign_as_agent + verify_agent round-trip."""
    svc = IdentityService()
    jiva = _make_jiva("bob")
    svc.get_or_create(jiva)

    payload = b"test message"
    sig = svc.sign_as_agent("bob", payload)
    assert sig is not None

    assert svc.verify_agent("bob", payload, sig) is True
    assert svc.verify_agent("bob", b"tampered", sig) is False


def test_verify_unknown_agent():
    """verify_agent returns False for unknown agent."""
    svc = IdentityService()
    assert svc.verify_agent("unknown", b"data", "sig") is False


def test_get_passport():
    """get_passport creates a signed passport dict."""
    svc = IdentityService()
    jiva = _make_jiva("carol")
    passport = svc.get_passport("carol", jiva)

    assert passport is not None
    assert passport["agent_name"] == "carol"
    assert "passport_signature" in passport
    assert "public_key" in passport


def test_stats():
    """stats returns known agent count."""
    svc = IdentityService()
    svc.get_or_create(_make_jiva("x"))
    svc.get_or_create(_make_jiva("y"))
    stats = svc.stats()
    assert stats["known_agents"] == 2
    assert set(stats["agent_names"]) == {"x", "y"}


if __name__ == "__main__":
    test_get_or_create()
    test_sign_and_verify()
    test_verify_unknown_agent()
    test_get_passport()
    test_stats()
    print("All 5 identity service tests passed.")
