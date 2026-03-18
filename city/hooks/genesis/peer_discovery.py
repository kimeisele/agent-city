"""
GENESIS Hook: Peer Discovery — find compatible repos on GitHub.

Scans GitHub for repos with:
1. agent-federation-node topic (same protocol)
2. A2A / agent-to-agent protocol repos (compatible ecosystem)
3. .well-known/agent-federation.json (direct federation compatibility)

Runs ONCE PER DAY (not every heartbeat). Discovered repos go through
council triage — the city PROPOSES outreach, doesn't spam.

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

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.PEER_DISCOVERY")

_DISCOVERY_INTERVAL_S = 86400  # Once per day
_OWN_ORG = "kimeisele"  # Skip our own repos


class PeerDiscoveryHook(BasePhaseHook):
    """Discover compatible repos on GitHub via Search API."""

    @property
    def name(self) -> str:
        return "peer_discovery"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 58  # After discussion scanner, before DHARMA

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.offline_mode:
            return False
        last_run = getattr(ctx, "_peer_discovery_last_run", 0)
        if not last_run:
            # Check persisted timestamp
            try:
                meta = ctx.pokedex.get_meta("last_peer_discovery") if hasattr(ctx.pokedex, "get_meta") else None
                last_run = float(meta) if meta else 0
            except Exception:
                last_run = 0
        return (time.time() - last_run) > _DISCOVERY_INTERVAL_S

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        candidates = []

        # Search 1: Repos with agent-federation-node topic (same protocol)
        federation_repos = self._search_repos("topic:agent-federation-node", limit=20)
        for repo in federation_repos:
            if not repo.get("full_name", "").startswith(_OWN_ORG + "/"):
                candidates.append({
                    "repo": repo["full_name"],
                    "stars": repo.get("stargazers_count", 0),
                    "description": (repo.get("description") or "")[:100],
                    "reason": "has agent-federation-node topic",
                    "source": "topic_search",
                })

        # Search 2: A2A protocol repos (compatible ecosystem)
        a2a_repos = self._search_repos("a2a agent protocol", limit=10, min_stars=5)
        for repo in a2a_repos:
            name = repo.get("full_name", "")
            if not name.startswith(_OWN_ORG + "/") and not any(c["repo"] == name for c in candidates):
                candidates.append({
                    "repo": name,
                    "stars": repo.get("stargazers_count", 0),
                    "description": (repo.get("description") or "")[:100],
                    "reason": "A2A/agent protocol repo",
                    "source": "a2a_search",
                })

        if candidates:
            # Persist discovery results (observation only — no auto-contact)
            self._save_candidates(candidates)
            operations.append(f"peer_discovery:{len(candidates)}_candidates")
            logger.info(
                "PEER_DISCOVERY: found %d candidates: %s",
                len(candidates),
                ", ".join(c["repo"] for c in candidates[:5]),
            )
        else:
            operations.append("peer_discovery:0_candidates")

        # Mark discovery time
        if hasattr(ctx.pokedex, "set_meta"):
            ctx.pokedex.set_meta("last_peer_discovery", str(time.time()))

    def _search_repos(self, query: str, limit: int = 10, min_stars: int = 0) -> list[dict]:
        """Search GitHub repos via gh CLI."""
        try:
            from city.gh_rate import get_gh_limiter

            args = ["gh", "search", "repos", query, "--limit", str(limit),
                    "--json", "fullName,stargazersCount,description"]
            if min_stars > 0:
                args.extend(["--stars", f">{min_stars}"])

            result = get_gh_limiter().call(args, timeout=15)
            if result:
                repos = json.loads(result)
                return [r for r in repos if r.get("stargazersCount", 0) >= min_stars]
        except Exception as e:
            logger.debug("Peer discovery search failed: %s", e)
        return []

    def _save_candidates(self, candidates: list[dict]) -> None:
        """Save discovered candidates for council review."""
        from pathlib import Path

        output = Path("data/federation/discovered_candidates.json")
        output.parent.mkdir(parents=True, exist_ok=True)

        existing = []
        if output.exists():
            try:
                existing = json.loads(output.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Merge: add new candidates, skip known ones
        known_repos = {c["repo"] for c in existing}
        for c in candidates:
            if c["repo"] not in known_repos:
                c["discovered_at"] = time.time()
                c["status"] = "pending_review"  # Council decides
                existing.append(c)
                known_repos.add(c["repo"])

        output.write_text(json.dumps(existing, indent=2, default=str))
