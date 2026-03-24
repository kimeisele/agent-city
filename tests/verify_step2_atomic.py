import json
import hashlib
from pathlib import Path
from unittest.mock import MagicMock
import sys

# Ensure projects root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.node_identity import NodeIdentity
from city.signal_composer import SignalComposer
from city.registry import CityServiceRegistry, SVC_IDENTITY, SVC_SIGNAL_COMPOSER, SVC_FEDERATION_NADI
from city.factory import BuildContext
from city.intent_executor import _handle_brain_propose_mission

def test_atomic_mission_proposal():
    # 1. Setup paths
    base_dir = Path("tests/tmp_step2")
    base_dir.mkdir(parents=True, exist_ok=True)
    fed_dir = base_dir / "federation"
    fed_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a mock master key (base64 32 bytes)
    # This is matching the format we found in tests/data/security/master.key
    # VHvOvBFXrY77RGHGyKyPN-Bk0P66KG2dCL81uKw19MA=
    master_key_file = base_dir / "master.key"
    master_key_file.write_text("VHvOvBFXrY77RGHGyKyPN-Bk0P66KG2dCL81uKw19MA=")
    
    # 2. Setup Registry & BuildContext
    registry = CityServiceRegistry()
    
    # Mock Jiva
    mayor_jiva = MagicMock()
    mayor_jiva.name = "Architect"
    mayor_jiva.address = 108
    mayor_jiva.elements.dominant = "akasha"
    # classification needs to be a mock with attributes
    mayor_jiva.classification = MagicMock()
    mayor_jiva.classification.guardian = "Indra"
    mayor_jiva.classification.chapter = 1
    mayor_jiva.classification.guna = "sattva"
    mayor_jiva.classification.trinity_function = "creator"

    # Mock Pokedex
    pokedex = MagicMock()
    pokedex.get_jiva.return_value = mayor_jiva
    
    # Load NodeIdentity manually for the test
    from city.node_identity import _load_identity_any_format
    identity = _load_identity_any_format(master_key_file)
    registry.register(SVC_IDENTITY, identity)
    
    # Build SignalComposer
    composer = SignalComposer(identity, mayor_jiva)
    registry.register(SVC_SIGNAL_COMPOSER, composer)
    
    # Mock NADI
    from city.federation_nadi import FederationNadi
    nadi = FederationNadi(_federation_dir=fed_dir)
    registry.register(SVC_FEDERATION_NADI, nadi)
    
    # Mock Issues
    issues = MagicMock()
    issues.create_issue.return_value = {"number": 123}
    
    # Mock Context
    ctx = MagicMock()
    ctx.registry = registry
    ctx.issues = issues
    ctx.db_path = base_dir / "city.db"
    ctx.config = {"executor": {"git_author_name": "Architect"}}
    ctx.pokedex = pokedex
    
    # Mock Intent
    intent = MagicMock()
    intent.context = {
        "target": "Step 2 Verification",
        "detail": "Finalizing NADI neural link",
        "author": "senior-architect",
        "discussion_number": 42
    }
    
    # 3. RUN HANDLER
    print("Running _handle_brain_propose_mission...")
    result = _handle_brain_propose_mission(ctx, intent)
    print(f"Result: {result}")
    
    # 4. VERIFY ATOMICITY & SIGNATURE
    # Outbox should exist
    outbox_path = fed_dir / "nadi_outbox.json"
    assert outbox_path.exists(), "NADI outbox missing!"
    
    outbox = json.loads(outbox_path.read_text())
    assert len(outbox) == 1
    msg = outbox[0]
    
    # Check signature
    package = msg["payload"]
    signature = package["signature"]
    payload = package["payload"]
    
    # Verify signature using the identity
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    is_valid = identity.verify(payload_bytes, signature)
    assert is_valid, "Ed25519 Signature INVALID!"
    print("✅ Signature Verified")
    
    # Check protocol version
    assert payload["protocol_version"] == "1.0.0"
    print("✅ Protocol Version Verified (1.0.0)")
    
    # Check NADI_REF in Issue
    # body is in the first call args of create_issue
    call_args = issues.create_issue.call_args[1]
    body = call_args["body"]
    
    signed_package_json = json.dumps(package, sort_keys=True)
    expected_ref = hashlib.sha256(signed_package_json.encode()).hexdigest()
    
    assert expected_ref in body, "NADI_REF mismatch in GitHub Issue!"
    print(f"✅ NADI_REF Verified: {expected_ref}")

    print("\nSTEP 2 VERIFICATION SUCCESSFUL!")

if __name__ == "__main__":
    test_atomic_mission_proposal()
