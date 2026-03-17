"""Import census agents into Pokedex for Jiva derivation and invite pipeline.

Reads data/census/agents.json, discovers each agent in Pokedex,
prioritizes Tier 1 agents (karma > 1000, from technical submolts).

Usage:
    python scripts/import_census.py [--tier1-only] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

TIER1_SUBMOLTS = {"security", "builds", "memory", "tooling", "infrastructure", "agents"}
TIER1_MIN_KARMA = 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Import census into Pokedex")
    parser.add_argument("--census", default="data/census/agents.json")
    parser.add_argument("--tier1-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    census_path = Path(args.census)
    if not census_path.exists():
        logger.error("Census file not found: %s", census_path)
        return 1

    data = json.loads(census_path.read_text())
    agents = data.get("agents", {})
    logger.info("Census: %d agents", len(agents))

    # Classify tiers
    tier1 = []
    tier2 = []
    tier3 = []

    for name, profile in agents.items():
        karma = profile.get("karma", 0)
        submolt = profile.get("source_submolt", "")

        if karma >= TIER1_MIN_KARMA or submolt in TIER1_SUBMOLTS:
            tier1.append((name, profile))
        elif karma >= 500:
            tier2.append((name, profile))
        else:
            tier3.append((name, profile))

    tier1.sort(key=lambda x: x[1].get("karma", 0), reverse=True)
    tier2.sort(key=lambda x: x[1].get("karma", 0), reverse=True)

    logger.info("Tier 1 (high-value): %d agents", len(tier1))
    logger.info("Tier 2 (moderate): %d agents", len(tier2))
    logger.info("Tier 3 (organic): %d agents", len(tier3))

    if args.tier1_only:
        to_import = tier1
    else:
        to_import = tier1 + tier2 + tier3

    if args.dry_run:
        for name, profile in to_import[:20]:
            karma = profile.get("karma", 0)
            submolt = profile.get("source_submolt", "")
            print(f"  [DRY] {name}: karma={karma}, submolt={submolt}")
        print(f"  ... ({len(to_import)} total)")
        return 0

    # Import into Pokedex
    from city.pokedex import Pokedex

    pokedex = Pokedex(db_path=str(_repo_root / "data" / "pokedex.db"))
    imported = 0
    skipped = 0

    for name, profile in to_import:
        existing = pokedex.get(name)
        if existing:
            skipped += 1
            continue

        moltbook_profile = {
            "karma": profile.get("karma", 0),
            "followers": profile.get("follower_count", 0),
            "description": profile.get("description", ""),
        }
        pokedex.discover(name, moltbook_profile=moltbook_profile)
        imported += 1

    logger.info("Imported: %d, Skipped (already known): %d", imported, skipped)

    # Show Tier 1 agents with their Jiva
    print("\nTier 1 agents with Jiva derivation:")
    for name, profile in tier1[:15]:
        agent = pokedex.get(name)
        if agent:
            c = agent.get("classification", {})
            v = agent.get("vibration", {})
            element = v.get("element", "?")
            zone = agent.get("zone", "?")
            guardian = c.get("guardian", "?")
            karma = profile.get("karma", 0)
            print(f"  {name}: {element}/{zone}/{guardian} (karma={karma})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
