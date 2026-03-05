"""
CityRouter — O(1) Agent Routing via Mahamantra Lotus.
======================================================

Schritt 4: Replaces all O(n) linear scans in gateway and mission_router
with O(1) MahaAttention lookups.

Three index dimensions (each a separate MahaAttention instance):
  1. CapabilityIndex: capability_name → set[agent_name]
  2. DomainIndex:     domain_name → set[agent_name]
  3. TierIndex:       tier_name → set[agent_name]

Agents are registered at spawn/promote time. Removal on freeze/archive.
The router is the SINGLE authority for "which agents can do X?" queries.

No LLM. No linear scan. O(1) hash → Lotus lookup → set intersection.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from vibe_core.mahamantra.adapters.attention import MahaAttention

logger = logging.getLogger("AGENT_CITY.ROUTER")


# =============================================================================
# CITY ROUTER
# =============================================================================


@dataclass
class CityRouter:
    """O(1) agent routing via Mahamantra Lotus indices.

    Three index dimensions:
      cap:  "cap:{capability}" → frozenset[agent_name]
      dom:  "dom:{domain}"     → frozenset[agent_name]
      tier: "tier:{tier}"      → frozenset[agent_name]

    Queries:
      agents_with_capability("execute") → frozenset in O(1)
      agents_in_domain("ENGINEERING")   → frozenset in O(1)
      agents_at_tier("contributor")     → frozenset in O(1)

    Compound queries use set intersection:
      agents_for_requirement(["execute"], "verified") →
        cap_set("execute") & tier_set("verified") in O(1) + O(|result|)
    """

    _index: MahaAttention = field(default_factory=MahaAttention)

    # Reverse index: agent → registered keys (for removal)
    _agent_keys: dict[str, set[str]] = field(default_factory=dict)

    # Live sets per key (mutable, frozen on memorize)
    _live_sets: dict[str, set[str]] = field(default_factory=dict)

    # Stats
    _registered_count: int = 0
    _removed_count: int = 0
    _query_count: int = 0

    def register(self, name: str, spec: dict) -> None:
        """Register an agent's capabilities, domain, and tier for O(1) routing.

        Called at spawn/promote time. Overwrites if already registered.
        Extracts from AgentSpec: capabilities, domain, capability_tier,
        capability_protocol, guardian.
        """
        # Remove stale entries if re-registering
        if name in self._agent_keys:
            self._remove(name)

        keys: set[str] = set()

        # Capabilities index
        for cap in spec.get("capabilities", []):
            key = f"cap:{cap}"
            self._add_to_set(key, name)
            keys.add(key)

        # Domain index
        domain = spec.get("domain", "")
        if domain:
            key = f"dom:{domain}"
            self._add_to_set(key, name)
            keys.add(key)

        # Tier index
        tier = spec.get("capability_tier", "observer")
        key = f"tier:{tier}"
        self._add_to_set(key, name)
        keys.add(key)

        # Protocol index (parse/validate/infer/route/enforce)
        protocol = spec.get("capability_protocol", "")
        if protocol:
            key = f"proto:{protocol}"
            self._add_to_set(key, name)
            keys.add(key)

        # Guardian index
        guardian = spec.get("guardian", "")
        if guardian:
            key = f"guard:{guardian}"
            self._add_to_set(key, name)
            keys.add(key)

        self._agent_keys[name] = keys
        self._registered_count += 1

        logger.debug(
            "CityRouter: registered %s (%d keys: domain=%s, tier=%s, caps=%d)",
            name, len(keys), domain, tier, len(spec.get("capabilities", [])),
        )

    def remove(self, name: str) -> None:
        """Remove an agent from all indices (on freeze/archive/death)."""
        if name not in self._agent_keys:
            return
        self._remove(name)
        self._removed_count += 1
        logger.debug("CityRouter: removed %s", name)

    # ── O(1) Queries ─────────────────────────────────────────────────

    def agents_with_capability(self, capability: str) -> frozenset[str]:
        """O(1): All agents that have this capability."""
        return self._lookup(f"cap:{capability}")

    def agents_in_domain(self, domain: str) -> frozenset[str]:
        """O(1): All agents in this domain."""
        return self._lookup(f"dom:{domain}")

    def agents_at_tier(self, tier: str) -> frozenset[str]:
        """O(1): All agents at this capability tier."""
        return self._lookup(f"tier:{tier}")

    def agents_with_protocol(self, protocol: str) -> frozenset[str]:
        """O(1): All agents with this capability protocol."""
        return self._lookup(f"proto:{protocol}")

    def agents_with_guardian(self, guardian: str) -> frozenset[str]:
        """O(1): All agents with this guardian archetype."""
        return self._lookup(f"guard:{guardian}")

    def agents_for_requirement(
        self,
        required_caps: list[str],
        min_tier: str = "observer",
        domain: str = "",
    ) -> frozenset[str]:
        """O(1) compound query: agents matching ALL required caps + tier.

        Replaces the O(n) for-loop in mission_router and gateway pre-filter.

        Steps:
          1. Intersect all required capability sets → O(|smallest_set|)
          2. Intersect with eligible tiers → O(|result|)
          3. Optionally filter by domain → O(|result|)

        The Lotus lookups are O(1). Only the set intersections scale
        with result size, not total population.
        """
        self._query_count += 1

        if not required_caps:
            # No capability requirement → all registered agents
            result = self._all_agents()
        else:
            # Intersect capability sets
            sets = [self._lookup(f"cap:{cap}") for cap in required_caps]
            # Start with smallest set for efficiency
            sets.sort(key=len)
            result = sets[0]
            for s in sets[1:]:
                result = result & s
                if not result:
                    return frozenset()

        # Tier filter: include all tiers >= min_tier
        from city.mission_router import TIER_RANK
        min_rank = TIER_RANK.get(min_tier, 0)
        eligible_tiers = frozenset(
            t for t, rank in TIER_RANK.items() if rank >= min_rank
        )
        tier_agents: set[str] = set()
        for tier in eligible_tiers:
            tier_agents.update(self._lookup(f"tier:{tier}"))
        result = result & frozenset(tier_agents)

        # Optional domain filter
        if domain and result:
            domain_agents = self._lookup(f"dom:{domain}")
            domain_filtered = result & domain_agents
            # Only apply domain filter if it doesn't eliminate everyone
            if domain_filtered:
                result = domain_filtered

        return result

    def _all_agents(self) -> frozenset[str]:
        """All registered agent names."""
        return frozenset(self._agent_keys.keys())

    # ── Internal ─────────────────────────────────────────────────────

    def _lookup(self, key: str) -> frozenset[str]:
        """O(1) Lotus lookup. Returns empty frozenset on miss."""
        self._query_count += 1
        result = self._index.attend(key)
        if result.found and isinstance(result.handler, frozenset):
            return result.handler
        return frozenset()

    def _add_to_set(self, key: str, name: str) -> None:
        """Add agent to a key's set, then re-memorize the frozen version."""
        if key not in self._live_sets:
            self._live_sets[key] = set()
        self._live_sets[key].add(name)
        self._index.memorize(key, frozenset(self._live_sets[key]))

    def _remove(self, name: str) -> None:
        """Remove agent from all its registered keys."""
        keys = self._agent_keys.pop(name, set())
        for key in keys:
            live = self._live_sets.get(key)
            if live is not None:
                live.discard(name)
                if live:
                    self._index.memorize(key, frozenset(live))
                else:
                    # Empty set — memorize empty frozenset (can't delete from Lotus)
                    self._index.memorize(key, frozenset())
                    del self._live_sets[key]

    def stats(self) -> dict:
        """Router statistics for reflection."""
        return {
            "registered_agents": len(self._agent_keys),
            "index_keys": len(self._live_sets),
            "total_registrations": self._registered_count,
            "total_removals": self._removed_count,
            "total_queries": self._query_count,
            "lotus_stats": {
                "mechanism": self._index.stats().mechanism,
                "registered": self._index.stats().registered_intents,
                "ops_saved": self._index.stats().estimated_ops_saved,
            },
        }
