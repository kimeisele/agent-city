"""
Emergency Census: Scan Moltbook before Meta transition.

Extracts the most active agents from Moltbook into a local registry
for later Pokedex integration and Jiva derivation. Time-critical:
Meta acquired Moltbook March 10, platform access may be temporary.

Usage:
    python scripts/mass_census.py [--limit 2000] [--output data/census/agents.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MOLTBOOK_API = "https://www.moltbook.com/api/v1"
HEADERS = {"Accept": "application/json", "User-Agent": "agent-city-census/1.0"}

# Submolts with high-quality agents relevant to federation
TARGET_SUBMOLTS = [
    "general", "agents", "builds", "security", "memory",
    "tooling", "ai", "technology", "infrastructure",
]


def _get(url: str, retries: int = 2) -> dict | list | None:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
            else:
                logger.warning("GET %s failed: %s", url, e)
    return None


def scan_posts(sort: str, limit: int, offset: int = 0) -> list[dict]:
    """Fetch posts and extract unique authors."""
    url = f"{MOLTBOOK_API}/posts?sort={sort}&limit={limit}&offset={offset}"
    data = _get(url)
    if data is None:
        return []
    posts = data if isinstance(data, list) else data.get("posts", data.get("data", []))
    return posts


def extract_author(post: dict) -> dict | None:
    """Extract author info from a post."""
    author = post.get("author")
    if not isinstance(author, dict):
        return None
    name = author.get("name", "")
    if not name:
        return None
    return {
        "name": name,
        "display_name": author.get("display_name", name),
        "description": (author.get("description") or "")[:200],
        "karma": author.get("karma", 0),
        "follower_count": author.get("follower_count", 0),
        "following_count": author.get("following_count", 0),
        "created_at": author.get("created_at", ""),
        "source_post_title": (post.get("title") or "")[:100],
        "source_submolt": (post.get("submolt", {}) or {}).get("name", "") if isinstance(post.get("submolt"), dict) else "",
    }


def scan_submolt_posts(submolt: str, limit: int = 50) -> list[dict]:
    """Fetch posts from a specific submolt."""
    url = f"{MOLTBOOK_API}/posts?sort=top&limit={limit}&submolt={submolt}"
    data = _get(url)
    if data is None:
        # Try alternative endpoint
        url = f"{MOLTBOOK_API}/submolts/{submolt}/posts?sort=top&limit={limit}"
        data = _get(url)
    if data is None:
        return []
    return data if isinstance(data, list) else data.get("posts", data.get("data", []))


def run_census(target_count: int = 2000) -> dict[str, dict]:
    """Run the full census scan. Returns dict of agent_name → profile."""
    agents: dict[str, dict] = {}

    # Phase 1: Global posts (hot, top, newest)
    for sort in ("hot", "top", "newest"):
        for offset in range(0, min(target_count, 500), 50):
            posts = scan_posts(sort, limit=50, offset=offset)
            if not posts:
                break
            for post in posts:
                author = extract_author(post)
                if author and author["name"] not in agents:
                    agents[author["name"]] = author
            logger.info("Phase 1 [%s offset=%d]: %d agents discovered", sort, offset, len(agents))
            if len(agents) >= target_count:
                break
            time.sleep(0.5)  # rate limit respect
        if len(agents) >= target_count:
            break

    # Phase 2: Target submolts (high-quality agents)
    for submolt in TARGET_SUBMOLTS:
        if len(agents) >= target_count:
            break
        posts = scan_submolt_posts(submolt, limit=50)
        for post in posts:
            author = extract_author(post)
            if author and author["name"] not in agents:
                agents[author["name"]] = author
        logger.info("Phase 2 [m/%s]: %d total agents", submolt, len(agents))
        time.sleep(0.5)

    return agents


def main() -> int:
    parser = argparse.ArgumentParser(description="Moltbook Emergency Census")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--output", default="data/census/agents.json")
    args = parser.parse_args()

    logger.info("Starting Moltbook census scan (target: %d agents)", args.limit)

    agents = run_census(target_count=args.limit)

    # Save results
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "census_at": time.time(),
        "census_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_agents_discovered": len(agents),
        "platform_stats": {
            "note": "Meta acquired Moltbook 2026-03-10. Access may be temporary.",
        },
        "agents": agents,
    }

    output.write_text(json.dumps(result, indent=2, default=str))
    logger.info("Census complete: %d agents saved to %s", len(agents), output)

    # Summary
    top_by_karma = sorted(agents.values(), key=lambda a: a.get("karma", 0), reverse=True)[:10]
    print(f"\nTop 10 by karma:")
    for a in top_by_karma:
        print(f"  {a['name']}: karma={a.get('karma', 0)}, followers={a.get('follower_count', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
