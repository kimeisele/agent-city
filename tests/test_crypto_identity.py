from city.jiva import derive_jiva
from city.identity import generate_identity, verify_ownership


def test_ecdsa_identity_deterministic():
    """VERIFY: Same agent name always produces the same ECDSA identity."""
    id_a = generate_identity(derive_jiva("Prahlad", "Devotion"))
    id_b = generate_identity(derive_jiva("Prahlad", "Devotion"))
    assert id_a.fingerprint == id_b.fingerprint
    assert id_a.public_key_pem == id_b.public_key_pem
    assert id_a.seed_hash == id_b.seed_hash


def test_ecdsa_sign_and_verify():
    """VERIFY: Agent can sign a message and self-verify it (pure ECDSA)."""
    jiva = derive_jiva("Prahlad", "Devotion")
    identity = generate_identity(jiva)

    message = b"I am Prahlad, and I am the Sovereign of my own state."
    signature = identity.sign(message)

    assert identity.verify(message, signature) is True
    assert identity.verify(b"tampered message", signature) is False


def test_cross_agent_spoofing_prevented():
    """VERIFY: Agent A's signature does not verify under Agent B's key."""
    id_a = generate_identity(derive_jiva("AgentAlpha"))
    id_b = generate_identity(derive_jiva("AgentBeta"))

    message = b"Secret orders from Alpha"
    sig_a = id_a.sign(message)

    # A's own key verifies
    assert id_a.verify(message, sig_a) is True
    # B's key rejects A's signature
    assert id_b.verify(message, sig_a) is False


def test_verify_ownership_roundtrip():
    """VERIFY: verify_ownership() works with the passport dict format."""
    jiva = derive_jiva("Prahlad")
    identity = generate_identity(jiva)
    passport = identity.sign_passport(jiva)

    payload = passport["passport_data"].encode()
    sig = passport["passport_signature"]

    assert verify_ownership({"public_key": passport["public_key"]}, payload, sig) is True
    assert verify_ownership({"public_key": passport["public_key"]}, b"wrong", sig) is False


def test_different_agents_produce_different_keys():
    """VERIFY: Two different agents never share an identity."""
    id_a = generate_identity(derive_jiva("AgentAlpha"))
    id_b = generate_identity(derive_jiva("AgentBeta"))
    assert id_a.fingerprint != id_b.fingerprint
    assert id_a.public_key_pem != id_b.public_key_pem
    assert id_a.seed_hash != id_b.seed_hash
