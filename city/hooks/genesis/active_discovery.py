"""
GENESIS Hook: Active Discovery — find compatible repos and agents on GitHub.

Scans GitHub for:
1. agent-federation-node topic (direct protocol compatibility)
2. "autonomous agent" / "agentic" keywords (ecosystem discovery)
3. A2A / agent-to-agent protocol repos

Runs ONCE PER DAY (or per interval). Discovered repos are stored in Pokedex.db
for persistent tracking.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.ACTIVE_DISCOVERY")

_DISCOVERY_INTERVAL_S = 86400  # Once per day
_OWN_ORG = "kimeisele"  # Skip our own repos


class ActiveDiscoveryHook(BasePhaseHook):
    """Discover compatible repos and agents on GitHub via Search API."""

    @property
    def name(self) -> str:
        return "active_discovery"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 58  # After discussion scanner

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.offline_mode:
            return False
        
        last_run_str = ctx.pokedex.get_meta("last_active_discovery")
        last_run = float(last_run_str) if last_run_str else 0.0
        
        return (time.time() - last_run) > _DISCOVERY_INTERVAL_S

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        new_count = 0
        
        # Search queries
        queries = [
            ("topic:agent-federation-node", 1.0),
            ("autonomous agent", 0.7),
            ("agentic", 0.6),
            ("a2a agent protocol", 0.9),
            ("agentic workflow", 0.5),
        ]

        for query, base_score in queries:
            repos = self._search_repos(query, limit=15)
            for repo in repos:
                full_name = repo.get("fullName")
                if not full_name or full_name.startswith(_OWN_ORG + "/"):
                    continue
                
                # Calculate relevance
                stars = repo.get("stargazersCount", 0)
                relevance = base_score * (1.0 + (min(stars, 1000) / 1000.0))
                
                repo_data = {
                    "full_name": full_name,
                    "html_url": f"https://github.com/{full_name}",
                    "description": repo.get("description", ""),
                    "stargazers_count": stars,
                    "language": repo.get("language", ""),
                    "relevance_score": relevance,
                }
                
                if ctx.pokedex.add_discovered_repo(repo_data):
                    new_count += 1
                    logger.info("ACTIVE_DISCOVERY: Discovered new repo: %s (score=%.2f)", full_name, relevance)

        operations.append(f"active_discovery:{new_count}_new")
        
        # Mark discovery time
        ctx.pokedex.set_meta("last_active_discovery", str(time.time()))

    def _search_repos(self, query: str, limit: int = 15) -> list[dict]:
        """Search GitHub repos via gh CLI."""
        try:
            from city.gh_rate import get_gh_limiter

            args = ["gh", "search", "repos", query, "--limit", str(limit),
                    "--json", "fullName,stargazersCount,description,language"]

            result = get_gh_limiter().call(args, timeout=20)
            if result:
                return json.loads(result)
        except Exception as e:
            logger.debug("Active discovery search failed for '%s': %s", query, e)
        return []
