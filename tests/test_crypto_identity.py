import pytest
import subprocess
import os
from city.jiva import Jiva, JivaSeed, derive_jiva
from city.identity import generate_identity, generate_gpg_identity

def test_gpg_identity_binding(monkeypatch):
    """VERIFY: Agent can bind a GPG identity and sign messages. (Sovereign ID)"""
    
    # 1. Derive a Jiva using the real VM pipeline
    jiva = derive_jiva("Prahlad", "Devotion")
    
    # 2. Generate Base Identity (ECDSA)
    identity = generate_identity(jiva)
    assert identity.agent_name == "Prahlad"
    
    # 3. Generate GPG Identity (Noreply / Internal Dual-UID)
    # We use a unique test email to avoid colliding with real keys
    test_email = "prahlad-test@agent-city.local"
    
    # Cleanup previous test keys if any
    subprocess.run(["gpg", "--batch", "--yes", "--delete-secret-keys", test_email], capture_output=True)
    subprocess.run(["gpg", "--batch", "--yes", "--delete-keys", test_email], capture_output=True)
    
    gpg_identity = generate_gpg_identity(identity, email=test_email)
    
    # 4. Assertions on GPG Binding
    assert gpg_identity.gpg_fingerprint is not None
    assert gpg_identity.gpg_email == test_email
    assert "-----BEGIN PGP PUBLIC KEY BLOCK-----" in gpg_identity.gpg_public_key
    
    # 5. Verify Signing Works
    message = "I am Prahlad, and I am the Sovereign of my own state."
    signed_msg = gpg_identity.sign_with_gpg(message)
    
    assert "-----BEGIN PGP SIGNED MESSAGE-----" in signed_msg
    assert message in signed_msg
    assert "-----BEGIN PGP SIGNATURE-----" in signed_msg
    
    # 6. Verify Signature Validity (Self-Verification)
    # We write the signed message to a file and verify it
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix=".asc") as f:
        f.write(signed_msg)
        f.flush()
        
        verify_res = subprocess.run(
            ["gpg", "--batch", "--verify", f.name],
            capture_output=True, text=True
        )
        assert verify_res.returncode == 0
        # GPG output is locale-dependent (EN: "Good signature", DE: "Korrekte Signatur")
        assert ("Good signature" in verify_res.stderr or "Korrekte Signatur" in verify_res.stderr)
        assert test_email in verify_res.stderr

def test_deterministic_gpg_generation_stub():
    """NOTE: Currently GPG generation via CLI is not natively deterministic.
    We are simulating the 'anchor' approach where the GPG key is generated 
    and then bound to the Jiva's secure vault.
    """
    pass
