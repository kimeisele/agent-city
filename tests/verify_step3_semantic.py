import json
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure projects root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.registry import CityServiceRegistry, SVC_DISCOVERY_LEDGER, SVC_BRAIN, SVC_SIGNAL_COMPOSER, SVC_FEDERATION_NADI, SVC_IDENTITY
from city.hooks.genesis.active_discovery import ActiveDiscoveryHook

def test_semantic_discovery():
    # 1. Setup paths
    base_dir = Path("tests/tmp_step3")
    if base_dir.exists():
        import shutil
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    
    fed_dir = base_dir / "federation"
    fed_dir.mkdir(parents=True, exist_ok=True)
    
    # Add peer.json for identity
    peer_path = fed_dir / "peer.json"
    peer_path.write_text(json.dumps({"identity": {"node_id": "test-node-1"}}))
    
    import logging
    logging.basicConfig(level=logging.INFO)
    
    db_path = base_dir / "discovery.db"
    
    # 2. Setup Ledger
    from city.discovery_ledger import DiscoveryLedger
    ledger = DiscoveryLedger(str(db_path))
    
    # Add 4 unevaluated repos (to test the 3-limit)
    for i in range(4):
        ledger.add_discovered_repo({
            "full_name": f"org/repo-{i}",
            "html_url": f"https://github.com/org/repo-{i}",
            "description": f"Agentic repo {i}",
            "stargazers_count": 100 * i,
            "relevance_score": 0.5 + (0.1 * i)
        })
    
    unevaluated_pre = ledger.get_unevaluated_repos(limit=10)
    print(f"Pre-hook unevaluated count: {len(unevaluated_pre)}")
    
    # 3. Setup Brain Mock
    thought_fit = MagicMock()
    thought_fit.action_hint = "invite"
    thought_fit.comprehension = "Excellent agentic architecture detected."
    
    brain = MagicMock()
    brain.is_available = True
    brain.evaluate_federation_fit.return_value = thought_fit
    
    # 4. Setup SignalComposer & NADI
    composer = MagicMock()
    # Mocking compose_mission_proposal to return a simple dict (signal)
    # New signature: (target, detail, author, correlation_id="")
    composer.compose_mission_proposal.side_effect = lambda target, detail, author, correlation_id="": {
        "target": target, "detail": detail, "author": author, "signed": True
    }
    
    from city.federation_nadi import FederationNadi
    nadi = FederationNadi(_federation_dir=fed_dir)
    
    # 5. Registry
    registry = CityServiceRegistry()
    registry.register(SVC_DISCOVERY_LEDGER, ledger)
    registry.register(SVC_BRAIN, brain)
    registry.register(SVC_SIGNAL_COMPOSER, composer)
    registry.register(SVC_FEDERATION_NADI, nadi)
    
    # 6. Context
    ctx = MagicMock()
    ctx.registry = registry
    ctx.offline_mode = False
    # Mock pokedex for meta - set last search to very recent to skip search phase
    import time
    ctx.pokedex = MagicMock()
    ctx.pokedex.get_meta.return_value = str(time.time() - 100.0)
    
    # 7. Mock gh CLI and base64 for fetch_readme
    mock_readme = base64.b64encode(b"This is a README for an autonomous agent.").decode()
    readme_json = json.dumps({"readme": {"content": mock_readme}})
    
    search_json = json.dumps([
        {"fullName": "org/new-repo", "stargazersCount": 10, "description": "New agentic repo", "language": "Python"}
    ])

    def gh_side_effect(args, timeout=None):
        if "search" in args:
            return search_json
        if "view" in args:
            return readme_json
        return None

    with patch("city.gh_rate.get_gh_limiter") as mock_limiter:
        mock_limiter.return_value.call.side_effect = gh_side_effect
        
        hook = ActiveDiscoveryHook()
        operations = []
        
        print("Running ActiveDiscoveryHook.execute...")
        hook.execute(ctx, operations)
        print(f"Operations: {operations}")
        
        # 8. VERIFY
        # Check limit of 3
        # operations should be ["semantic_eval:3_checked:3_fit"]
        assert "semantic_eval:3_checked:3_fit" in operations
        print("✅ Limit of 3 enforced")
        
        # Check brain calls
        assert brain.evaluate_federation_fit.call_count == 3
        print("✅ Brain called exactly 3 times")
        
        # Check Ledger update
        unevaluated = ledger.get_unevaluated_repos(limit=10)
        # 4 initial - 3 processed = 1 left
        assert len(unevaluated) == 1
        print("✅ Ledger state correctly updated (1 repo remains unevaluated)")
        
        # Check NADI outbox
        outbox_path = fed_dir / "nadi_outbox.json"
        assert outbox_path.exists()
        outbox = json.loads(outbox_path.read_text())
        print(f"Final Outbox length: {len(outbox)}")
        if len(outbox) != 3:
            print("Outbox Content:")
            print(json.dumps(outbox, indent=2))
        assert len(outbox) == 3
        print(f"✅ NADI outbox contains {len(outbox)} signed invites")

    print("\nSTEP 3 VERIFICATION SUCCESSFUL!")

if __name__ == "__main__":
    test_semantic_discovery()
