#!/usr/bin/env python3
"""
LIVE FIRE COGNITION TEST
========================
Tests the Step 8 Organic Loop against the live Moltbook API.

Senior Architect Mandate: No mocks, no fake data. Real API only.
"""

import os
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
from city.registry import (
    SVC_MOLTBOOK_ASSISTANT,
    SVC_MOLTBOOK_CLIENT,
    SVC_BRAIN,
    SVC_SANKALPA,
    SVC_SIGNAL_STATE_LEDGER,
    SVC_MOLTBOOK_BRIDGE,
)

logging.basicConfig(level=logging.WARNING)  # Reduce noise
logger = logging.getLogger("LIVE_FIRE")
logger.setLevel(logging.INFO)


def run():
    # Safety check
    if not os.environ.get("MOLTBOOK_API_KEY"):
        print("ERROR: MOLTBOOK_API_KEY environment variable not set.")
        print("Live Fire requires a real Moltbook API key.")
        sys.exit(1)

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
            self.offline = False

    runtime = build_city_runtime(args=MockArgs(args.db), config=config, log=logger)

    # Retrieve required services
    assistant = runtime.registry.get(SVC_MOLTBOOK_ASSISTANT)
    brain = runtime.registry.get(SVC_BRAIN)
    sankalpa = runtime.registry.get(SVC_SANKALPA)
    client = runtime.registry.get(SVC_MOLTBOOK_CLIENT)

    if assistant is None:
        logger.error("MoltbookAssistant not found in registry.")
        sys.exit(1)

    logger.info(
        "Services retrieved: Brain=%s, Sankalpa=%s, Client=%s",
        "yes" if brain else "no",
        "yes" if sankalpa else "no",
        "yes" if client else "no",
    )

    # 1. Boot Real Context with all required attributes
    ctx = PhaseContext(
        pokedex=runtime.pokedex,
        gateway=runtime.mayor._gateway,
        network=runtime.mayor._network,
        heartbeat_count=runtime.mayor._state.heartbeat_count,
        offline_mode=False,
        state_path=runtime.state_paths.mayor_state_path,
        registry=runtime.registry,
        brain=brain,
        sankalpa=sankalpa,
        recent_events=[],
    )
    # Ensure sensory buffer attribute exists
    ctx._sensory_buffer = []
    # Manually set brain and sankalpa attributes (in case PhaseContext doesn't store them)
    ctx.brain = brain
    ctx.sankalpa = sankalpa

    # Ensure missions are loaded from DB
    if ctx.sankalpa and hasattr(ctx.sankalpa, 'on_heartbeat'):
        ctx.sankalpa.on_heartbeat(ctx.heartbeat_count)

    # 2. Trigger Organic Loop
    ops = []

    print("\n--- [PHASE 1: GENESIS - SENSORY SAMPLING] ---")
    try:
        hook = MoltbookObservationHook()
        hook.execute(ctx, ops)
        logger.info("MoltbookObservationHook executed successfully")
    except Exception as e:
        logger.warning("MoltbookObservationHook failed: %s", e)
        # Fallback: try to fetch posts directly via client
        if hasattr(client, "sync_get_feed"):
            try:
                feed = client.sync_get_feed(limit=20)
                ctx._sensory_buffer = feed
                logger.info("Fallback: Fetched %d posts via client.sync_get_feed", len(feed))
            except Exception as feed_err:
                logger.error("Fallback feed fetch also failed: %s", feed_err)
        else:
            logger.error("Client has no sync_get_feed method")

    if not hasattr(ctx, "_sensory_buffer") or not ctx._sensory_buffer:
        print("Result: No unread posts found in live feed.")
        return

    print(f"Result: Observed {len(ctx._sensory_buffer)} unread posts.")
    # Print first post details as required by Senior Architect
    first_post = ctx._sensory_buffer[0]
    print("\n--- LIVE POST EVALUATED ---")
    print(f"Post ID: {first_post.get('id', 'N/A')}")
    print(f"Author: {first_post.get('author', {}).get('username', 'N/A')}")
    content_preview = f"{first_post.get('title', '')} {first_post.get('content', '')}"
    print(f"Content preview: {content_preview[:200]}...")
    print("---------------------------")

    print("\n--- [PHASE 2: DHARMA - STRATEGIC EVALUATION] ---")
    assistant.on_dharma(ctx)

    # 3. Output Requirements
    if not assistant._engagement_plan and not any(
        e.get("type") == "internal_governance_signal" for e in ctx.recent_events
    ):
        print("Result: No engagement planned (likely no active missions or low relevance).")
        # Print city_needs for debugging
        city_needs = []
        if ctx.sankalpa and hasattr(ctx.sankalpa, 'registry'):
            try:
                active = ctx.sankalpa.registry.list_missions(status="active")
                city_needs = [m.name for m in active[:5]]
            except Exception as e:
                logger.warning("Could not retrieve active missions: %s", e)
        print(f"Active missions: {city_needs}")
        return

    # Print detailed evaluation for each plan
    for plan in assistant._engagement_plan:
        post = next((p for p in ctx._sensory_buffer if p["id"] == plan["post_id"]), {})
        print(f"\n--- EVALUATION: HIGH CONFIDENCE (ENGAGING) ---")
        print(f"POST ID:   {plan['post_id']}")
        print(f"AUTHOR:    @{plan['author']}")
        content_preview = f"{post.get('title', '')} {post.get('content', '')}"
        print(f"CONTENT:   {content_preview[:200]}...")
        print(f"SCORE:     {plan['confidence'] * 100:.0f}%")
        print(f"STRATEGY:  {plan['strategy']}")
        print(f"DRAFT:     {plan['response'][:200]}...")

    # Print low confidence audits
    for event in ctx.recent_events:
        if event.get("type") == "internal_governance_signal":
            payload = event.get("payload", {})
            if payload.get("op") == "social_strategy_audit":
                post_id_short = payload["subject"].split(":")[-1]
                post = next(
                    (p for p in ctx._sensory_buffer if p["id"].startswith(post_id_short)),
                    {},
                )
                print(f"\n--- EVALUATION: LOW CONFIDENCE (STEWARD AUDIT) ---")
                print(f"POST ID:   {post.get('id', 'unknown')}")
                audit_content = f"{post.get('title', '')} {post.get('content', '')}"
                print(f"CONTENT:   {audit_content[:200]}...")
                print(f"SCORE:     {payload['confidence'] * 100:.0f}%")
                print(f"REASON:    {payload['reason']}")

    print("\n--- [PHASE 3: KARMA - SOVEREIGN EXECUTION] ---")
    # Ensure required services for on_karma are present
    ledger = runtime.registry.get(SVC_SIGNAL_STATE_LEDGER)
    bridge = runtime.registry.get(SVC_MOLTBOOK_BRIDGE)
    if ledger:
        ctx.registry.register(SVC_SIGNAL_STATE_LEDGER, ledger)
    if bridge:
        ctx.registry.register(SVC_MOLTBOOK_BRIDGE, bridge)

    res = assistant.on_karma(ctx, runtime.pokedex.stats())
    print(f"Raw result: {res}")

    # Detailed output for organic engagements
    if res.get('organic_engagements', 0) > 0:
        print("\n--- ORGANIC ENGAGEMENTS EXECUTED ---")
        for plan in assistant._engagement_plan:
            print(f"  Post {plan['post_id'][:8]}: {plan['strategy']}")
    else:
        print("\nNo organic engagements executed (confidence < 0.85 or other reasons).")

    # Summary
    print("\n=== LIVE FIRE RESULTS ===")
    print(f"Invites sent: {res.get('invites_sent', 0)}")
    print(f"Organic engagements: {res.get('organic_engagements', 0)}")
    print(f"Post created: {res.get('post_created', False)}")
    print("=========================\n")

    # If confidence >= 0.85, the system may have posted a reply.
    # The actual posting is handled inside on_karma via the bridge.
    # We rely on the logs to see what happened.
    logger.info("Live Fire test completed.")


if __name__ == "__main__":
    run()
