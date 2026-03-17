"""
AGENT SPAWNER — Lifecycle Engine for Agent City
=================================================

Orchestrates the full agent lifecycle:
  discovered → citizen → network-registered → cartridge-bound → active

System agents: spawned at boot from CartridgeRegistry (prefixed sys_).
Community agents: promoted in DHARMA from Moltbook discoveries.

Delegates to existing infrastructure — zero new logic:
- Pokedex.register() for citizenship (Jiva + Identity + Wallet + Oath)
- CityNetwork.register_agent() for routing + AnantaShesha health
- CartridgeLoader for cartridge binding

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.SPAWNER")


@dataclass
class AgentSpawner:
    """Thin orchestrator for agent lifecycle.

    Wires together Pokedex (identity), CityNetwork (routing),
    and CartridgeLoader (capability binding).
    """

    _pokedex: object  # city.pokedex.Pokedex
    _network: object  # city.network.CityNetwork
    _cartridge_loader: object = None  # city.cartridge_loader.CityCartridgeLoader
    _cartridge_factory: object = None  # city.cartridge_factory.CartridgeFactory
    _city_builder: object = None  # city.city_builder.CityBuilder
    _router: object = None  # city.router.CityRouter
    _agent_cartridges: dict[str, str] = field(default_factory=dict)
    _system_agents: list[str] = field(default_factory=list)
    _promoted_total: int = 0
    _network_registered: int = 0

    def spawn_system_agents(self) -> list[str]:
        """Boot-time: create system agents from CartridgeLoader.

        Each cartridge becomes a sys_{name} agent with full citizenship.
        Returns list of newly spawned agent names.
        """
        if self._cartridge_loader is None:
            return []

        cartridge_names = self._cartridge_loader.list_available()
        spawned: list[str] = []

        for cart_name in cartridge_names:
            agent_name = f"sys_{cart_name}"

            existing = self._pokedex.get(agent_name)
            if existing and existing["status"] in ("citizen", "active"):
                # Already registered — just ensure network + binding
                self._bind_and_register(agent_name, cart_name)
                continue

            try:
                self._pokedex.register(agent_name)
                self._bind_and_register(agent_name, cart_name)

                # Get CartridgeInfo (YAML metadata: real domain + capabilities)
                cartridge_info = None
                if self._cartridge_loader is not None:
                    cartridge_info = self._cartridge_loader.get_info(cart_name)

                # Generate cartridge: Jiva identity + CartridgeInfo capabilities
                if self._cartridge_factory is not None:
                    self._cartridge_factory.generate(agent_name, cartridge_info=cartridge_info)

                # Materialize physical agent directory
                if self._city_builder is not None:
                    self._city_builder.materialize(agent_name)

                # Index in CityRouter for O(1) routing
                self._index_agent(agent_name)

                spawned.append(agent_name)
                logger.info("Spawned system agent: %s → cartridge %s", agent_name, cart_name)
            except Exception as e:
                logger.warning("Failed to spawn system agent %s: %s", agent_name, e)

        self._system_agents = [f"sys_{n}" for n in cartridge_names]
        return spawned

    def promote_eligible(
        self, heartbeat: int, *, immigration: object = None
    ) -> list[str]:
        """DHARMA: upgrade discovered agents to citizens.

        Two paths:
        1. Direct promotion (system/census agents): pokedex.register() immediately
        2. Immigration pipeline (community agents): submit application → review → council → visa

        System agents (sys_* prefix) and census-seeded agents (discovered_at == registered
        in same heartbeat window) get direct promotion. Community agents discovered via
        Moltbook/Discussions go through the immigration pipeline.

        Returns list of promoted agent names (direct path only; immigration is async).
        """
        discovered = self._pokedex.list_by_status("discovered")
        promoted: list[str] = []

        for agent in discovered:
            name = agent["name"]

            # Community agents go through immigration if service available
            if immigration is not None and not name.startswith("sys_"):
                # Skip if agent already has an application (e.g. from IssueScanner)
                if immigration.get_application_by_agent(name) is not None:
                    continue
                try:
                    from city.immigration import ApplicationReason
                    from city.visa import VisaClass

                    immigration.submit_application(
                        agent_name=name,
                        reason=ApplicationReason.CITIZEN_APPLICATION,
                        requested_visa_class=VisaClass.WORKER,
                    )
                    logger.info(
                        "Immigration application submitted for %s (heartbeat %d)",
                        name,
                        heartbeat,
                    )
                except Exception as e:
                    logger.warning("Immigration application failed for %s: %s", name, e)
                continue

            # Direct promotion: system agents or no immigration service
            try:
                self._pokedex.register(name)
                cell = self._pokedex.get_cell(name)
                if cell is not None and cell.is_alive:
                    self._network.register_agent(name, cell)
                    self._network_registered += 1

                # Generate cartridge from Jiva data
                if self._cartridge_factory is not None:
                    self._cartridge_factory.generate(name)

                # Materialize physical agent directory
                if self._city_builder is not None:
                    self._city_builder.materialize(name)

                # Index in CityRouter for O(1) routing
                self._index_agent(name)

                promoted.append(name)
                self._promoted_total += 1
                logger.info("Promoted %s: discovered → citizen (heartbeat %d)", name, heartbeat)
            except Exception as e:
                logger.warning("Failed to promote %s: %s", name, e)

        return promoted

    def mark_citizens_active(self, active_set: set[str]) -> int:
        """KARMA: activate living citizens and populate the active set.

        Two things happen:
        1. SQLite status transitions citizen → active (via pokedex.activate())
        2. Populates active_set for DHARMA's metabolize_all() (10 prana feeding)

        Returns count of active citizens.
        """
        count = 0
        for agent in self._pokedex.list_citizens():
            name = agent["name"]
            cell = self._pokedex.get_cell(name)
            if cell is not None and cell.is_alive:
                # Actually transition status in SQLite (was missing before)
                try:
                    self._pokedex.activate(name)
                    logger.info("Activated %s: citizen → active", name)
                except (ValueError, KeyError):
                    pass  # already active or invalid state — fine
                active_set.add(name)
                count += 1
        return count

    def materialize_existing(self) -> int:
        """Boot-time: generate cartridges + physical dirs for existing citizens.

        Called once at boot to catch citizens promoted in previous runs
        who don't have cartridges or physical directories yet.
        Also ensures claim_level >= 1 for citizens (migration for pre-fix agents).
        """
        count = 0
        for agent in self._pokedex.list_citizens():
            name = agent["name"]
            cell = self._pokedex.get_cell(name)
            if cell is None or not cell.is_alive:
                continue

            # Ensure citizens are at least claim_level 1 (contributor)
            if self._pokedex.get_claim_level(name) < 1:
                from city.membrane import internal_membrane_snapshot

                self._pokedex.update_claim_level(
                    name,
                    1,
                    membrane=internal_membrane_snapshot(source_class="spawner"),
                )
                logger.info("Migrated %s to claim_level=1 (contributor)", name)

            # Generate cartridge if not already cached
            if self._cartridge_factory is not None:
                self._cartridge_factory.generate(name)

            # Materialize physical directory (rewrites manifest with latest spec)
            if self._city_builder is not None:
                self._city_builder.materialize(name)

            # Index in CityRouter for O(1) routing
            self._index_agent(name)

            count += 1
        return count

    def bind_cartridge(self, agent_name: str, cartridge_name: str) -> None:
        """Bind an agent to a cartridge for mission routing."""
        self._agent_cartridges[agent_name] = cartridge_name

    def get_cartridge(self, agent_name: str) -> str | None:
        """Get the bound cartridge for an agent."""
        return self._agent_cartridges.get(agent_name)

    def stats(self) -> dict:
        """Population stats for MOKSHA reflection."""
        return {
            "system_agents": len(self._system_agents),
            "cartridge_bindings": len(self._agent_cartridges),
            "promoted_total": self._promoted_total,
            "network_registered": self._network_registered,
        }

    def _index_agent(self, name: str) -> None:
        """Register agent in CityRouter for O(1) capability/domain/tier lookup."""
        if self._router is None or self._cartridge_factory is None:
            return
        spec = self._cartridge_factory.get_spec(name)
        if spec is not None:
            self._router.register(name, spec)

    def _bind_and_register(self, agent_name: str, cartridge_name: str) -> None:
        """Bind cartridge + register in network (if cell alive)."""
        self._agent_cartridges[agent_name] = cartridge_name
        cell = self._pokedex.get_cell(agent_name)
        if cell is not None and cell.is_alive:
            if agent_name not in self._network._registered_agents:
                self._network.register_agent(agent_name, cell)
                self._network_registered += 1
