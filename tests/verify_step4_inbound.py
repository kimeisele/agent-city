import json
import os
import fcntl
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure projects root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.registry import CityServiceRegistry, SVC_IDENTITY, SVC_SANKALPA, SVC_SIGNAL_STATE_LEDGER
from city.hooks.genesis.nadi_inbox_scanner import NadiInboxScannerHook
from city.signal import SemanticSignal, SemanticIntent

def test_inbound_membrane():
    # 1. Setup paths
    base_dir = Path("tests/tmp_step4")
    if base_dir.exists():
        import shutil
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    
    fed_dir = base_dir / "federation"
    fed_dir.mkdir(parents=True, exist_ok=True)
    inbox_path = fed_dir / "nadi_inbox.json"
    
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("VERIFY_STEP4")

    # 2. Mock Identity Service
    identity = MagicMock()
    identity.verify.return_value = True # Always valid for test
    
    # 3. Mock Signal State Ledger
    ledger = MagicMock()
    ledger.is_signal_processed.return_value = False
    
    # 4. Mock Issue Service
    issues = MagicMock()
    issues.find_issue_by_nadi_ref.return_value = 123
    
    # 5. Mock Sankalpa
    sankalpa = MagicMock()
    
    # 6. Mock Federation NADI (to provide inbox_path)
    from city.registry import SVC_INTENT_EXECUTOR, SVC_FEDERATION_NADI
    nadi = MagicMock()
    nadi.inbox_path = inbox_path
    
    # 7. Mock Intent Executor
    executor = MagicMock()
    executor.execute.return_value = "success:handled"
    
    # 8. Registry
    registry = CityServiceRegistry()
    registry.register(SVC_IDENTITY, identity)
    registry.register(SVC_SIGNAL_STATE_LEDGER, ledger)
    registry.register(SVC_SANKALPA, sankalpa)
    registry.register(SVC_FEDERATION_NADI, nadi)
    registry.register(SVC_INTENT_EXECUTOR, executor)
    
    # 9. Context
    ctx = MagicMock()
    ctx.registry = registry
    ctx.db_path = base_dir / "city.db"
    ctx.issues = issues
    ctx.offline_mode = False
    
    # 10. Create a mock signed message in nadi_inbox.json
    signal_data = {
        "sender_name": "steward",
        "sender_address": 0,
        "correlation_id": "corr_123",
        "coords": {
            "rama_coordinates": [0,0],
            "element_walk": [0,0],
            "element_histogram": [0,0,0,0,0],
            "basin_set": [],
            "hkr_color": [0,0,0],
            "walk_direction": 0,
            "dominant_element": 0
        },
        "sender_element": 0,
        "sender_guardian": "test",
        "sender_chapter": 0,
        "sender_guna": "test",
        "sender_trinity": "test",
        "concepts": [],
        "resonant_elements": [],
        "raw_text": "MISSION_ACCEPTED",
        "priority": 1,
        "intent": "MISSION_ACCEPTED",
        "in_reply_to": "ref_original_proposal_hash",
        "hop_count": 0
    }
    
    payload = {
        "protocol_version": "1.0.0",
        "origin_jiva": "steward",
        "timestamp": 123456789.0,
        "signal": signal_data
    }
    
    message = {
        "payload": payload,
        "signature": "mock_signature_hex",
        "signer_key": "mock_pubkey_hex"
    }
    
    with open(inbox_path, "w") as f:
        json.dump([message], f)
    
    # 11. Run Hook
    hook = NadiInboxScannerHook()
    operations = []
    
    logger.info("Running NadiInboxScannerHook...")
    hook.execute(ctx, operations)
    
    # 12. VERIFY Hook Actions
    assert "nadi_inbox:1_processed" in operations
    logger.info("✅ Hook processed 1 message")
    
    # Check ledger update
    ledger.mark_signal_processed.assert_called()
    logger.info("✅ Signal marked as processed in ledger")
    
    # Check executor call
    executor.execute.assert_called()
    call_args = executor.execute.call_args
    # call_args[0] is (ctx, intent, handler_name)
    intent = call_args[0][1]
    assert intent.signal == "federation:MISSION_ACCEPTED"
    assert intent.context["sender_jiva"] == "steward"
    assert intent.context["signal"].in_reply_to == "ref_original_proposal_hash"
    logger.info("✅ Intent correctly constructed and dispatched")
    
    # 13. Verify Inbox Cleansing
    with open(inbox_path, "r") as f:
        inbox_data = json.load(f)
    assert len(inbox_data) == 0
    logger.info("✅ Inbox cleansed after processing")
    
    # 14. Test Intent Handler (handle_federation_signal)
    from city.intent_executor import _handle_federation_signal
    
    # Mocking Intent for handler
    mock_intent = MagicMock()
    mock_intent.context = intent.context
    
    logger.info("Running _handle_federation_signal handler...")
    result = _handle_federation_signal(ctx, mock_intent)
    
    assert "accepted:steward:issue=#123" in result
    logger.info("✅ Handler linked signal to issue #123 via NADI_REF")
    
    # Verify GitHub comment was "emitted" (mocked)
    issues._gh_run.assert_called()
    logger.info("✅ GitHub comment emitted for acceptance")
    
    # 15. Test Integrity Rejection (Mandate #2)
    
    bad_signal = MagicMock()
    bad_signal.intent = SemanticIntent.MISSION_COMPLETED
    bad_signal.in_reply_to = None
    
    mock_intent.context["signal"] = bad_signal
    result = _handle_federation_signal(ctx, mock_intent)
    assert "reject:missing_reference:MISSION_COMPLETED" in result
    logger.info("✅ Reference Integrity Rejection verified")

    print("\nSTEP 4 VERIFICATION SUCCESSFUL!")

    print("\nSTEP 4 VERIFICATION SUCCESSFUL!")

if __name__ == "__main__":
    test_inbound_membrane()
