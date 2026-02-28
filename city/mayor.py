"""
MAYOR AGENT — The Autonomous City Operator
=============================================

Runs the city via MURALI 4-phase cycle, exactly like the Moltbook plugin.

MURALI Departments:
  0 GENESIS: Census (discover agents from Moltbook feed)
  1 DHARMA:  Governance (cell homeostasis, zone health, proposals)
  2 KARMA:   Operations (process gateway queue, agent interactions)
  3 MOKSHA:  Reflection (verify event chain, verify integrity, stats)

Cell metabolism per heartbeat:
- Each active agent's cell: metabolize(0) → loses METABOLIC_COST (3) prana
- Agents with activity: metabolize(energy) → gains energy
- Dead cells (prana=0): trigger archive("prana_exhaustion")

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from city.gateway import CityGateway
from city.network import CityNetwork
from city.pokedex import Pokedex

logger = logging.getLogger("AGENT_CITY.MAYOR")

# MURALI departments — same pattern as Moltbook plugin
GENESIS = 0
DHARMA = 1
KARMA = 2
MOKSHA = 3

DEPARTMENT_NAMES = {
    GENESIS: "GENESIS",
    DHARMA: "DHARMA",
    KARMA: "KARMA",
    MOKSHA: "MOKSHA",
}

# THE_FLUTE_CYCLE from steward-protocol (static LUT, 16 entries)
# We use heartbeat_count % 4 for department routing (same as Moltbook)
QUARTERS = 4


class HeartbeatResult(TypedDict):
    """Result of a single heartbeat cycle."""
    heartbeat: int
    department: str
    department_idx: int
    timestamp: float
    discovered: list[str]
    governance_actions: list[str]
    operations: list[str]
    reflection: dict


class MayorState(TypedDict):
    """Persistent state for the Mayor agent."""
    heartbeat_count: int
    last_heartbeat: float
    discovered_agents: list[str]
    archived_agents: list[str]
    total_governance_actions: int
    total_operations: int


@dataclass
class Mayor:
    """The autonomous city operator.

    Runs MURALI 4-phase cycles. Each heartbeat advances one department.
    4 heartbeats = 1 full MURALI rotation.
    """

    _pokedex: Pokedex
    _gateway: CityGateway
    _network: CityNetwork
    _state_path: Path = field(default=Path("data/mayor_state.json"))
    _heartbeat_count: int = 0
    _offline_mode: bool = False
    _active_agents: set[str] = field(default_factory=set)
    _gateway_queue: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def heartbeat(self) -> HeartbeatResult:
        """Execute one heartbeat cycle.

        Routes to the correct MURALI department based on heartbeat_count % 4.
        """
        department = self._heartbeat_count % QUARTERS
        dept_name = DEPARTMENT_NAMES[department]

        logger.info(
            "Mayor heartbeat #%d — department %s",
            self._heartbeat_count, dept_name,
        )

        result: HeartbeatResult = {
            "heartbeat": self._heartbeat_count,
            "department": dept_name,
            "department_idx": department,
            "timestamp": time.time(),
            "discovered": [],
            "governance_actions": [],
            "operations": [],
            "reflection": {},
        }

        if department == GENESIS:
            result["discovered"] = self._genesis_census()
        elif department == DHARMA:
            result["governance_actions"] = self._dharma_governance()
        elif department == KARMA:
            result["operations"] = self._karma_operations()
        elif department == MOKSHA:
            result["reflection"] = self._moksha_reflection()

        self._heartbeat_count += 1
        self._save_state()
        return result

    def run_cycle(self, cycles: int = 4) -> list[HeartbeatResult]:
        """Run multiple heartbeat cycles (default: 1 full MURALI rotation)."""
        results = []
        for _ in range(cycles):
            results.append(self.heartbeat())
        return results

    # ── GENESIS: Census ──────────────────────────────────────────────

    def _genesis_census(self) -> list[str]:
        """Discover agents from Moltbook feed (or offline cache).

        In offline mode, just returns already-known agents.
        """
        discovered: list[str] = []

        if self._offline_mode:
            # Offline: report existing population
            all_agents = self._pokedex.list_all()
            for agent in all_agents:
                discovered.append(agent["name"])
            logger.info("GENESIS (offline): %d agents in registry", len(discovered))
            return discovered

        # Online: scan Moltbook feed for new agents
        try:
            from vibe_core.mahamantra.adapters.moltbook import MoltbookClient
            client = MoltbookClient()
            feed = client.get_feed(limit=20)

            for post in feed:
                author = post.get("author", {}).get("username")
                if not author:
                    continue
                existing = self._pokedex.get(author)
                if not existing:
                    self._pokedex.discover(author, moltbook_profile={
                        "karma": post.get("author", {}).get("karma"),
                        "follower_count": post.get("author", {}).get("follower_count"),
                    })
                    discovered.append(author)
                    logger.info("GENESIS: Discovered agent %s", author)
        except Exception as e:
            logger.warning("GENESIS: Moltbook scan failed: %s", e)

        return discovered

    # ── DHARMA: Governance ───────────────────────────────────────────

    def _dharma_governance(self) -> list[str]:
        """Cell homeostasis, zone health, metabolism.

        Runs metabolize_all() on all living agents.
        """
        actions: list[str] = []

        # Metabolize all living agents
        dead = self._pokedex.metabolize_all(active_agents=self._active_agents)
        for name in dead:
            actions.append(f"archived:{name}:prana_exhaustion")
            logger.info("DHARMA: Agent %s archived (prana exhaustion)", name)

        # Clear active set for next cycle
        self._active_agents.clear()

        # Zone health check
        stats = self._pokedex.stats()
        zones = stats.get("zones", {})
        for zone, count in zones.items():
            if count == 0:
                actions.append(f"warning:zone_{zone}_empty")
                logger.warning("DHARMA: Zone %s has 0 agents", zone)

        if actions:
            logger.info("DHARMA: %d governance actions", len(actions))
        return actions

    # ── KARMA: Operations ────────────────────────────────────────────

    def _karma_operations(self) -> list[str]:
        """Process gateway queue and agent interactions."""
        operations: list[str] = []

        # Process queued gateway items
        while self._gateway_queue:
            item = self._gateway_queue.pop(0)
            source = item.get("source", "unknown")
            text = item.get("text", "")
            try:
                result = self._gateway.process(text, source)
                operations.append(f"processed:{source}:seed={result['seed']}")
            except Exception as e:
                operations.append(f"error:{source}:{e}")
                logger.warning("KARMA: Gateway processing failed for %s: %s", source, e)

        if operations:
            logger.info("KARMA: %d operations processed", len(operations))
        return operations

    # ── MOKSHA: Reflection ───────────────────────────────────────────

    def _moksha_reflection(self) -> dict:
        """Verify event chain, verify integrity, collect stats."""
        stats = self._pokedex.stats()
        chain_valid = self._pokedex.verify_event_chain()
        network_stats = self._network.stats()

        reflection = {
            "chain_valid": chain_valid,
            "heartbeat": self._heartbeat_count,
            "city_stats": stats,
            "network_stats": network_stats,
        }

        if not chain_valid:
            logger.warning("MOKSHA: Event chain integrity BROKEN")
        else:
            logger.info(
                "MOKSHA: Reflection — %d agents, chain valid, %d events",
                stats.get("total", 0), stats.get("events", 0),
            )
        return reflection

    # ── External Interface ───────────────────────────────────────────

    def enqueue(self, source: str, text: str) -> None:
        """Add an item to the gateway queue for KARMA processing."""
        self._gateway_queue.append({"source": source, "text": text})

    def mark_active(self, name: str) -> None:
        """Mark an agent as active for the current metabolism cycle."""
        self._active_agents.add(name)

    # ── State Persistence ────────────────────────────────────────────

    def _load_state(self) -> None:
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                self._heartbeat_count = data.get("heartbeat_count", 0)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_state(self) -> None:
        state: MayorState = {
            "heartbeat_count": self._heartbeat_count,
            "last_heartbeat": time.time(),
            "discovered_agents": [a["name"] for a in self._pokedex.list_all()],
            "archived_agents": [a["name"] for a in self._pokedex.list_by_status("archived")],
            "total_governance_actions": 0,
            "total_operations": 0,
        }
        self._state_path.write_text(json.dumps(state, indent=2))
