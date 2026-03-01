"""
TEST IDENTITY CHANNELS
======================

Validates the "Radio Frequency" identity abstraction.
Agents are not just their name, but the channel/frequency they originate from.
"""

import pytest

def test_identical_names_on_different_channels_have_different_identities():
    """Agents with same name but different channels MUST have different cryptographic identities.
    
    Attack vector: An agent on Local CLI names themselves 'Admin'.
    Because identity was only derived from name, they got the exact same
    ECDSA private key as the real 'Admin' on the Moltbook channel.
    
    Impact: Total identity spoofing across federation boundaries.
    """
    from city.identity import generate_identity
    from city.jiva import derive_jiva
    
    # 1. Moltbook Channel Agent
    jiva_moltbook = derive_jiva("Admin", channel="moltbook")
    id_moltbook = generate_identity(jiva_moltbook)
    
    # 2. Local CLI Channel Agent (Attacker)
    jiva_cli = derive_jiva("Admin", channel="local_cli")
    id_cli = generate_identity(jiva_cli)
    
    # INVARIANT: Even with the exact same name, different interaction channels
    # MUST yield completely isolated cryptographic keypairs.
    assert id_moltbook.fingerprint != id_cli.fingerprint, (
        "VULNERABILITY: Identity collision across channels! "
        "The Local CLI agent successfully spoofed the Moltbook agent's keypair "
        "just by using the same name."
    )
