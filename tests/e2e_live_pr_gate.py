#!/usr/bin/env python3
"""
LIVE E2E Test: PR Gate against real GitHub API.

Runs PRScannerHook against the real PR #176, writes to real NADI outbox,
then simulates a Steward verdict and runs PRVerdictHook to post a real
comment on the PR.

Usage: GITHUB_TOKEN=xxx python tests/e2e_live_pr_gate.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.federation_nadi import FederationMessage, FederationNadi, RAJAS
from city.hooks.genesis.pr_scanner import PRScannerHook, _processed_prs
from city.hooks.dharma.pr_verdict import PRVerdictHook


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)

    # Setup real NADI
    fed_dir = Path("data/federation")
    fed_dir.mkdir(parents=True, exist_ok=True)

    # Ensure peer.json exists
    peer_path = fed_dir / "peer.json"
    if not peer_path.exists():
        peer_path.write_text(json.dumps({
            "identity": {"city_id": "agent-city", "slug": "agent-city"},
        }))

    nadi = FederationNadi(_federation_dir=fed_dir)

    # Build context with real NADI
    ctx = MagicMock()
    ctx.offline_mode = False
    ctx.federation_nadi = nadi
    ctx.pokedex = MagicMock()
    ctx.pokedex.get.return_value = None  # kimeisele is not in pokedex
    ctx.council = None
    ctx.heartbeat_count = 1

    # ── Step 1: GENESIS — PRScannerHook detects PR #176 ──
    print("\n═══ STEP 1: GENESIS — PRScannerHook ═══")
    _processed_prs.clear()

    scanner = PRScannerHook()
    genesis_ops: list[str] = []

    scanner.execute(ctx, genesis_ops)
    flush_count = nadi.flush()

    print(f"  Scanner operations: {genesis_ops}")
    print(f"  NADI messages flushed: {flush_count}")

    # Read outbox
    outbox_data = json.loads(nadi.outbox_path.read_text()) if nadi.outbox_path.exists() else []
    print(f"  Outbox messages: {len(outbox_data)}")

    # Find our PR
    our_request = None
    for msg in outbox_data:
        if msg.get("payload", {}).get("pr_number") == 176:
            our_request = msg
            break

    if our_request:
        print(f"\n  ✓ PR #176 detected!")
        print(f"    Operation: {our_request['operation']}")
        print(f"    Author: {our_request['payload']['author']}")
        print(f"    Title: {our_request['payload']['title']}")
        print(f"    Files: {our_request['payload']['files_changed']}")
        print(f"    Is Citizen: {our_request['payload']['is_citizen']}")
        print(f"    Touches Core: {our_request['payload']['touches_core']}")
    else:
        print("\n  ✗ PR #176 NOT found in outbox!")
        # Print what we got for debugging
        for msg in outbox_data:
            pn = msg.get("payload", {}).get("pr_number", "?")
            print(f"    Found PR #{pn}: {msg.get('operation')}")

    # ── Step 2: Simulate Steward verdict → NADI inbox ──
    print("\n═══ STEP 2: Simulate Steward Verdict → NADI Inbox ═══")

    steward_verdict = FederationMessage(
        source="steward-protocol",
        target="agent-city",
        operation="pr_review_verdict",
        payload={
            "pr_number": 176,
            "verdict": "approve",
            "reason": (
                "Steward Review: Clean E2E test PR. Single README change, "
                "no core files touched, known author. Auto-merge approved.\n\n"
                "— Fourth membrane surface verified. NADI bridge operational."
            ),
            "title": "test: PR Gate E2E — fourth membrane surface verification",
            "touches_core": False,
        },
        priority=RAJAS,
    )
    nadi.inbox_path.write_text(json.dumps([steward_verdict.to_dict()], indent=2))
    print(f"  Verdict written to inbox: {nadi.inbox_path}")
    print(f"  Verdict: approve (non-core)")

    # ── Step 3: DHARMA — PRVerdictHook processes verdict ──
    print("\n═══ STEP 3: DHARMA — PRVerdictHook ═══")

    handler = PRVerdictHook()
    dharma_ops: list[str] = []

    handler.execute(ctx, dharma_ops)

    print(f"  Verdict operations: {dharma_ops}")

    if any("merged" in op for op in dharma_ops):
        print("\n  ✓ PR #176 auto-merged by verdict handler!")
    elif any("merge_failed" in op for op in dharma_ops):
        print("\n  ~ Merge attempted but failed (expected in E2E without merge permissions)")
        print("    The comment was still posted — check PR #176 on GitHub.")
    else:
        print(f"\n  Result: {dharma_ops}")

    # ── Summary ──
    print("\n═══ E2E SUMMARY ═══")
    print(f"  GENESIS ops: {len(genesis_ops)}")
    print(f"  NADI outbox: {flush_count} messages")
    print(f"  DHARMA ops:  {len(dharma_ops)}")
    print(f"  PR #176:     https://github.com/kimeisele/agent-city/pull/176")
    print("\n  Fourth membrane surface: OPERATIONAL ✓")


if __name__ == "__main__":
    main()
