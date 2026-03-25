#!/usr/bin/env python3
"""
LIVE FIRE COGNITION TEST
========================
Tests the Step 8 Organic Loop against the live Moltbook API.
"""

import sys
import logging
import argparse
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.runtime import build_city_runtime
from config import get_config
from city.phases import PhaseContext
from city.hooks.genesis.moltbook_scan import MoltbookObservationHook
from city.registry import SVC_MOLTBOOK_ASSISTANT, SVC_MOLTBOOK_CLIENT, SVC_BRAIN, SVC_SANKALPA

logging.basicConfig(level=logging.WARNING) # Reduce noise
logger = logging.getLogger("LIVE_FIRE")
logger.setLevel(logging.INFO)

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/city.db")
    args = parser.parse_args()
    
    config = get_config()
    # Mocking args for build_city_runtime
    class MockArgs:
        def __init__(self, db):
            self.db = db
            self.governance = True
            self.federation = False
    
    runtime = build_city_runtime(args=MockArgs(args.db), config=config, log=logger)
    
    # 1. Boot Real Context
    ctx = PhaseContext(
        pokedex=runtime.pokedex,
        gateway=runtime.mayor._gateway,
        network=runtime.mayor._network,
        heartbeat_count=runtime.mayor._state.heartbeat_count,
        offline_mode=False,
        state_path=runtime.state_paths.mayor_state_path,
        registry=runtime.registry
    )
    
    # Ensure missions are loaded from DB
    if ctx.sankalpa:
        ctx.sankalpa.on_heartbeat(ctx.heartbeat_count)
    
    # 2. Trigger Organic Loop
    ops = []
    
    print("\n--- [PHASE 1: GENESIS - SENSORY SAMPLING] ---")
    hook = MoltbookObservationHook()
    hook.execute(ctx, ops)
    
    if not hasattr(ctx, "_sensory_buffer") or not ctx._sensory_buffer:
        print("Result: No unread posts found in live feed.")
        return

    print(f"Result: Observed {len(ctx._sensory_buffer)} unread posts.")
    
    print("\n--- [PHASE 2: DHARMA - STRATEGIC EVALUATION] ---")
    assistant = runtime.registry.get(SVC_MOLTBOOK_ASSISTANT)
    assistant.on_dharma(ctx)
    
    # 3. Output Requirements
    if not assistant._engagement_plan and not any(e.get("type") == "internal_governance_signal" for e in ctx.recent_events):
        print("Result: No engagement planned (likely no active missions or low relevance).")
        return

    for plan in assistant._engagement_plan:
        post = next((p for p in ctx._sensory_buffer if p["id"] == plan["post_id"]), {})
        print(f"\n--- EVALUATION: HIGH CONFIDENCE (ENGAGING) ---")
        print(f"POST ID:   {plan['post_id']}")
        print(f"AUTHOR:    @{plan['author']}")
        print(f"CONTENT:   {post.get('title', '')} {post.get('content', '')}")
        print(f"SCORE:     {plan['confidence']*100:.0f}%")
        print(f"STRATEGY:  {plan['strategy']}")
        print(f"DRAFT:     {plan['response']}")

    for event in ctx.recent_events:
        if event.get("type") == "internal_governance_signal":
            payload = event.get("payload", {})
            if payload.get("op") == "social_strategy_audit":
                post_id_short = payload['subject'].split(":")[-1]
                post = next((p for p in ctx._sensory_buffer if p["id"].startswith(post_id_short)), {})
                print(f"\n--- EVALUATION: LOW CONFIDENCE (STEWARD AUDIT) ---")
                print(f"POST ID:   {post.get('id', 'unknown')}")
                print(f"CONTENT:   {post.get('title', '')} {post.get('content', '')}")
                print(f"SCORE:     {payload['confidence']*100:.0f}%")
                print(f"REASON:    {payload['reason']}")

    print("\n--- [PHASE 3: KARMA - SOVEREIGN EXECUTION] ---")
    res = assistant.on_karma(ctx, runtime.pokedex.stats())
    print(f"Result: {res}")

if __name__ == "__main__":
    run()
#!/usr/bin/env python3
"""
LIVE FIRE TEST — Step 8: Dynamic Social Cognition Loop on Moltbook API.

Boots the real city runtime, pulls the live Moltbook feed, evaluates posts
against active city missions, and executes organic engagement if confidence >= 0.85.

Senior Architect Mandate: No mocks, no fake data. Real API only.
"""

import os
import sys
import logging
from pathlib import Path

# Ensure we are in the project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from city.runtime import build_city_runtime
from city.phases import PhaseContext
from city.registry import (
    SVC_MOLTBOOK_ASSISTANT,
    SVC_BRAIN,
    SVC_SANKALPA,
    SVC_MOLTBOOK_CLIENT,
    SVC_DISCOVERY_LEDGER,
    SVC_SIGNAL_STATE_LEDGER,
    SVC_SIGNAL_COMPOSER,
)

def main():
    # Safety check
    if not os.environ.get("MOLTBOOK_API_KEY"):
        print("ERROR: MOLTBOOK_API_KEY environment variable not set.")
        print("Live Fire requires a real Moltbook API key.")
        sys.exit(1)

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log = logging.getLogger("LIVE_FIRE")

    # Simulate minimal args and config as in heartbeat.py
    class Args:
        db = "data/city.db"
        offline = False
        governance = True
        federation = False
        federation_dry_run = False

    args = Args()
    config = {
        "services": {"disabled": []},
        "discussions": {"repo_id": "test", "owner": "kimeisele", "repo": "agent-city"},
        "moltbook_bridge": {"own_username": "agent-city"},
        "moltbook_assistant": {"max_follows_per_cycle": 3, "max_invites_per_cycle": 2, "post_cooldown_s": 1800},
        "database": {
            "discovery_path": "data/discovery.db",
            "signal_state_path": "data/signal_state.db",
        },
        "executor": {"git_author_name": "Mayor"},
    }

    log.info("Building city runtime...")
    runtime = build_city_runtime(args=args, config=config, log=log)

    # Retrieve required services
    assistant = runtime.registry.get(SVC_MOLTBOOK_ASSISTANT)
    if assistant is None:
        log.error("MoltbookAssistant not found in registry.")
        sys.exit(1)

    brain = runtime.registry.get(SVC_BRAIN)
    sankalpa = runtime.registry.get(SVC_SANKALPA)
    client = runtime.registry.get(SVC_MOLTBOOK_CLIENT)

    log.info("Services retrieved: Brain=%s, Sankalpa=%s, Client=%s",
             "yes" if brain else "no",
             "yes" if sankalpa else "no",
             "yes" if client else "no")

    # Create a realistic PhaseContext
    ctx = PhaseContext(
        heartbeat_count=1,
        brain=brain,
        sankalpa=sankalpa,
        registry=runtime.registry,
        recent_events=[],
        # Sensory buffer will be filled by observation hook
        _sensory_buffer=[],
    )

    # 1. GENESIS: Pull live Moltbook feed into sensory buffer
    log.info("GENESIS: Fetching live Moltbook feed...")
    try:
        # Use the MoltbookClient to fetch recent posts
        # The exact method depends on the client's API; we assume sync_get_feed exists
        if hasattr(client, "sync_get_feed"):
            feed = client.sync_get_feed(limit=20)
            ctx._sensory_buffer = feed
            log.info("Fetched %d posts from live feed.", len(feed))
        else:
            # Fallback: try to use the MoltbookObservationHook if available
            from city.hooks.moltbook_observation import MoltbookObservationHook
            hook = MoltbookObservationHook()
            hook.execute(ctx, [])
            log.info("Observation hook executed, sensory buffer size: %d", len(ctx._sensory_buffer))
    except Exception as e:
        log.error("Failed to fetch live feed: %s", e)
        sys.exit(1)

    if not ctx._sensory_buffer:
        log.warning("No posts in sensory buffer. Exiting.")
        sys.exit(0)

    # Print first post for inspection
    first_post = ctx._sensory_buffer[0]
    print("\n--- LIVE POST EVALUATED ---")
    print(f"Post ID: {first_post.get('id', 'N/A')}")
    print(f"Author: {first_post.get('author', {}).get('username', 'N/A')}")
    print(f"Content preview: {first_post.get('content', '')[:200]}...")
    print("---------------------------\n")

    # 2. DHARMA: Plan organic engagement
    log.info("DHARMA: Executing assistant.on_dharma...")
    try:
        assistant.on_dharma(ctx)
    except Exception as e:
        log.error("on_dharma failed: %s", e)
        sys.exit(1)

    # 3. KARMA: Execute planned actions
    log.info("KARMA: Executing assistant.on_karma...")
    city_stats = runtime.pokedex.stats() if runtime.pokedex else {}
    result = assistant.on_karma(ctx, city_stats)

    # Output results
    print("\n=== LIVE FIRE RESULTS ===")
    print(f"Invites sent: {result.get('invites_sent', 0)}")
    print(f"Organic engagements: {result.get('organic_engagements', 0)}")
    print(f"Post created: {result.get('post_created', False)}")
    print("=========================\n")

    # If confidence >= 0.85, the system may have posted a reply.
    # The actual posting is handled inside on_karma via the bridge.
    # We rely on the logs to see what happened.
    log.info("Live Fire test completed.")

if __name__ == "__main__":
    main()
