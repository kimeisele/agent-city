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
        
        # 1. Search is due (Daily)
        last_run_str = ctx.pokedex.get_meta("last_active_discovery")
        last_run = float(last_run_str) if last_run_str else 0.0
        if (time.time() - last_run) > _DISCOVERY_INTERVAL_S:
            return True

        # 2. Evaluation is due if unevaluated repos exist
        from city.registry import SVC_DISCOVERY_LEDGER
        ledger = ctx.registry.get(SVC_DISCOVERY_LEDGER)
        if ledger and hasattr(ledger, "get_unevaluated_repos"):
            if ledger.get_unevaluated_repos(limit=1):
                return True

        return False

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        last_run_str = ctx.pokedex.get_meta("last_active_discovery")
        last_run = float(last_run_str) if last_run_str else 0.0
        
        # 1. Routine Search (Daily)
        if (time.time() - last_run) > _DISCOVERY_INTERVAL_S:
            new_count = self._discover_new_candidates(ctx, operations)
            ctx.pokedex.set_meta("last_active_discovery", str(time.time()))
            operations.append(f"discovery_search:{new_count}_new")

        # 2. Cognitive Evaluation (Every heartbeat, max 3 per mandate)
        self._evaluate_candidates(ctx, operations)

    def _discover_new_candidates(self, ctx: PhaseContext, operations: list[str]) -> int:
        """Search GitHub for new candidates and add to ledger."""
        new_count = 0
        from city.registry import SVC_DISCOVERY_LEDGER
        ledger = ctx.registry.get(SVC_DISCOVERY_LEDGER)
        if not ledger:
            return 0

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
                
                # Calculate relevance for sorting, but LLM does the final decision
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
                
                # Use ledger instead of pokedex (Step 1 mandatum)
                if ledger.add_discovered_repo(repo_data):
                    new_count += 1
                    logger.info("ACTIVE_DISCOVERY: Scouted new repo: %s", full_name)
        
        return new_count

    def _evaluate_candidates(self, ctx: PhaseContext, operations: list[str]) -> None:
        """Select up to 3 unevaluated repos and perform semantic fit check."""
        from city.registry import SVC_DISCOVERY_LEDGER, SVC_BRAIN
        ledger = ctx.registry.get(SVC_DISCOVERY_LEDGER)
        brain = ctx.registry.get(SVC_BRAIN)
        if not ledger or not brain or not brain.is_available:
            return
            
        candidates = ledger.get_unevaluated_repos(limit=3)
        if not candidates:
            return
            
        fit_count = 0
        for repo in candidates:
            full_name = repo["full_name"]
            readme = self._fetch_readme(full_name)
            
            thought = brain.evaluate_federation_fit(
                repo_name=full_name,
                description=repo["description"],
                readme_snippet=readme
            )
            
            if not thought:
                continue
                
            # Senior Architect Mandate: FIT, REJECTED, NEEDS_HUMAN_REVIEW
            # Mapped from action_hint in DiscoveryBuilder
            status = thought.action_hint  # invite, reject, review
            reason = thought.comprehension
            
            fit_status = "REJECTED"
            if status == "invite":
                fit_status = "FIT"
                fit_count += 1
                self._initiate_federation_proposal(ctx, repo, reason)
            elif status == "review":
                fit_status = "NEEDS_HUMAN_REVIEW"
                
            ledger.update_evaluation(full_name, fit_status, reason)
            logger.info("SEMANTIC_DISCOVERY: Evaluated %s -> %s", full_name, fit_status)

        operations.append(f"semantic_eval:{len(candidates)}_checked:{fit_count}_fit")

    def _fetch_readme(self, full_name: str) -> str:
        """Fetch README.md from GitHub via gh CLI."""
        from city.gh_rate import get_gh_limiter
        import base64
        try:
            # gh repo view --json readme returns { "readme": { "content": "base64..." } }
            args = ["gh", "repo", "view", full_name, "--json", "readme"]
            result = get_gh_limiter().call(args, timeout=15)
            if result:
                data = json.loads(result)
                b64_content = data.get("readme", {}).get("content", "")
                if b64_content:
                    return base64.b64decode(b64_content).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Failed to fetch README for %s: %s", full_name, e)
        return ""

    def _initiate_federation_proposal(self, ctx: PhaseContext, repo: dict, reason: str) -> None:
        """Post a signed federation proposal to the NADI outbox (Step 2 Integration)."""
        from city.registry import SVC_SIGNAL_COMPOSER, SVC_FEDERATION_NADI
        composer = ctx.registry.get(SVC_SIGNAL_COMPOSER)
        nadi = ctx.registry.get(SVC_FEDERATION_NADI)
        
        if not composer or not nadi:
            return
            
        target = f"FEDERATION_INVITE:{repo['full_name']}"
        detail = f"Semantic fit detected: {reason[:200]}"
        
        # Compose signed signal using architectural bridge from Step 2
        # composer.compose_mission_proposal requires (target, detail, author)
        signal = composer.compose_mission_proposal(target, detail, author="genesis")
        if signal:
            # Emit to NADI outbox
            nadi.emit(
                source="genesis",
                operation="propose_mission",
                payload=signal
            )
            nadi.flush()
            logger.info("FEDERATION: Signed invite signal posted to NADI outbox for %s", repo['full_name'])

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
