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
