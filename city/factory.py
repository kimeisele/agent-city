"""
SERVICE FACTORY — Declarative service wiring for Agent City.

Replaces 150 lines of manual try/except in scripts/heartbeat.py
with a ServiceDefinition list and topological build.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from city.registry import CityServiceRegistry

logger = logging.getLogger("AGENT_CITY.FACTORY")


@dataclass(frozen=True)
class ServiceDefinition:
    """Declarative service definition.

    name: Registry key (e.g. SVC_CONTRACTS).
    factory: Callable that returns the service instance.
    deps: Service names that must be registered first.
    optional: If True, failure is logged and skipped.
    """

    name: str
    factory: Callable[["BuildContext"], object]
    deps: tuple[str, ...] = ()
    optional: bool = True


@dataclass
class BuildContext:
    """Context passed to service factories during build."""

    registry: CityServiceRegistry
    db_path: Path
    offline: bool
    args: object  # argparse.Namespace
    config: dict = field(default_factory=dict)
    pokedex: object = None  # Pokedex (for services needing direct access)
    network: object = None  # CityNetwork (for services needing direct access)


class CityServiceFactory:
    """Builds all services from ServiceDefinition list.

    Features:
    - Topological dependency sort (deps honored)
    - Config-based disable list (config/city.yaml → services.disabled)
    - Optional services swallowed on failure
    - Stats for wiring report
    """

    def __init__(self, definitions: list[ServiceDefinition]) -> None:
        self._definitions = definitions
        self._built: list[str] = []
        self._failed: list[str] = []
        self._skipped: list[str] = []

    def build_all(
        self,
        registry: CityServiceRegistry,
        build_ctx: BuildContext,
        disabled: list[str] | None = None,
    ) -> CityServiceRegistry:
        """Build and register all services in dependency order.

        Args:
            registry: Target registry.
            build_ctx: Shared context for factories.
            disabled: Service names to skip (from config).

        Returns:
            The registry (for chaining).
        """
        disabled_set = set(disabled or [])
        ordered = self._topo_sort()

        for defn in ordered:
            if defn.name in disabled_set:
                self._skipped.append(defn.name)
                logger.info("Service %s disabled by config", defn.name)
                continue

            # Check deps
            missing_deps = [d for d in defn.deps if not registry.has(d)]
            if missing_deps:
                if defn.optional:
                    self._skipped.append(defn.name)
                    logger.debug(
                        "Service %s skipped (missing deps: %s)",
                        defn.name,
                        missing_deps,
                    )
                    continue
                else:
                    raise RuntimeError(
                        f"Service {defn.name} requires {missing_deps} which are not registered"
                    )

            try:
                instance = defn.factory(build_ctx)
                if instance is not None:
                    registry.register(defn.name, instance)
                    self._built.append(defn.name)
                    logger.info("Service %s wired", defn.name)
                else:
                    self._skipped.append(defn.name)
            except Exception as e:
                if defn.optional:
                    self._failed.append(defn.name)
                    logger.warning("Service %s failed: %s", defn.name, e)
                else:
                    raise

        return registry

    def _topo_sort(self) -> list[ServiceDefinition]:
        """Topological sort of definitions by deps."""
        name_to_defn = {d.name: d for d in self._definitions}
        visited: set[str] = set()
        result: list[ServiceDefinition] = []

        def _visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            defn = name_to_defn.get(name)
            if defn is None:
                return
            for dep in defn.deps:
                _visit(dep)
            result.append(defn)

        for d in self._definitions:
            _visit(d.name)
        return result

    def stats(self) -> dict:
        """Build statistics."""
        return {
            "built": self._built,
            "failed": self._failed,
            "skipped": self._skipped,
            "total_definitions": len(self._definitions),
        }


def default_definitions(
    governance: bool = False, federation: bool = False
) -> list[ServiceDefinition]:
    """Default service definitions for Agent City.

    Args:
        governance: Wire Layer 3+4 governance services.
        federation: Wire Layer 6 federation services.
    """
    from city.registry import (
        SVC_AGENT_NADI,
        SVC_ATTENTION,
        SVC_AUDIT,
        SVC_CARTRIDGE_FACTORY,
        SVC_CARTRIDGE_LOADER,
        SVC_CITY_BUILDER,
        SVC_CITY_NADI,
        SVC_CLAIMS,
        SVC_CONTRACTS,
        SVC_COUNCIL,
        SVC_EVENT_BUS,
        SVC_EXECUTOR,
        SVC_FEDERATION,
        SVC_FEDERATION_NADI,
        SVC_IMMUNE,
        SVC_ISSUES,
        SVC_KNOWLEDGE_GRAPH,
        SVC_LEARNING,
        SVC_PRAHLAD,
        SVC_REACTOR,
        SVC_REFLECTION,
        SVC_SANKALPA,
        SVC_SPAWNER,
        SVC_MOLTBOOK_ASSISTANT,
        SVC_PATHOGEN_INDEX,
    )

    defs: list[ServiceDefinition] = []

    # ── Layer 3+4: Governance ──────────────────────────────────────
    if governance:
        defs.extend(
            [
                ServiceDefinition(
                    name=SVC_CONTRACTS,
                    factory=lambda ctx: _build_contracts(ctx),
                ),
                ServiceDefinition(
                    name=SVC_EXECUTOR,
                    factory=lambda ctx: _build_executor(ctx),
                ),
                ServiceDefinition(
                    name=SVC_ISSUES,
                    factory=lambda ctx: _build_issues(),
                ),
                ServiceDefinition(
                    name=SVC_COUNCIL,
                    factory=lambda ctx: _build_council(ctx),
                ),
                ServiceDefinition(
                    name=SVC_SANKALPA,
                    factory=lambda ctx: _build_sankalpa(),
                ),
                ServiceDefinition(
                    name=SVC_REFLECTION,
                    factory=lambda ctx: _build_reflection(),
                ),
                ServiceDefinition(
                    name=SVC_AUDIT,
                    factory=lambda ctx: _build_audit(),
                ),
                ServiceDefinition(
                    name=SVC_CLAIMS,
                    factory=lambda ctx: _build_claims(),
                ),
            ]
        )

    # ── Layer 6: Federation ────────────────────────────────────────
    if federation:
        defs.append(
            ServiceDefinition(
                name=SVC_FEDERATION,
                factory=lambda ctx: _build_federation(ctx),
            )
        )

    # ── Always-on services ─────────────────────────────────────────
    defs.extend(
        [
            ServiceDefinition(
                name=SVC_ATTENTION,
                factory=lambda ctx: _build_attention(),
            ),
            ServiceDefinition(
                name=SVC_REACTOR,
                factory=lambda ctx: _build_reactor(),
            ),
            ServiceDefinition(
                name=SVC_CARTRIDGE_FACTORY,
                factory=lambda ctx: _build_cartridge_factory(ctx),
            ),
            ServiceDefinition(
                name=SVC_CITY_BUILDER,
                factory=lambda ctx: _build_city_builder(ctx),
            ),
            ServiceDefinition(
                name=SVC_CARTRIDGE_LOADER,
                factory=lambda ctx: _build_cartridge_loader(ctx),
                deps=(SVC_CARTRIDGE_FACTORY,),
            ),
            ServiceDefinition(
                name=SVC_SPAWNER,
                factory=lambda ctx: _build_spawner(ctx),
                deps=(SVC_CARTRIDGE_LOADER, SVC_CARTRIDGE_FACTORY, SVC_CITY_BUILDER),
            ),
            ServiceDefinition(
                name=SVC_FEDERATION_NADI,
                factory=lambda ctx: _build_federation_nadi(ctx),
            ),
            ServiceDefinition(
                name=SVC_LEARNING,
                factory=lambda ctx: _build_learning(ctx),
            ),
            ServiceDefinition(
                name=SVC_IMMUNE,
                factory=lambda ctx: _build_immune(ctx),
                deps=(SVC_LEARNING,),
            ),
            ServiceDefinition(
                name=SVC_PRAHLAD,
                factory=lambda ctx: _build_prahlad(ctx),
            ),
            ServiceDefinition(
                name=SVC_AGENT_NADI,
                factory=lambda ctx: _build_agent_nadi(),
            ),
            ServiceDefinition(
                name=SVC_CITY_NADI,
                factory=lambda ctx: _build_city_nadi(),
            ),
            ServiceDefinition(
                name=SVC_KNOWLEDGE_GRAPH,
                factory=lambda ctx: _build_knowledge_graph(),
            ),
            ServiceDefinition(
                name=SVC_EVENT_BUS,
                factory=lambda ctx: _build_event_bus(),
            ),
            ServiceDefinition(
                name=SVC_MOLTBOOK_ASSISTANT,
                factory=lambda ctx: _build_moltbook_assistant(ctx),
            ),
            ServiceDefinition(
                name=SVC_PATHOGEN_INDEX,
                factory=lambda ctx: _build_pathogen_index(ctx),
                deps=(SVC_REACTOR,),
            ),
        ]
    )

    return defs


# ── Individual Builders ──────────────────────────────────────────────


def _build_attention() -> object:
    from city.attention import CityAttention

    return CityAttention()


def _build_reactor() -> object:
    from city.reactor import CityReactor

    return CityReactor()


def _build_contracts(ctx: BuildContext) -> object:
    from city.contracts import create_default_contracts

    return create_default_contracts()


def _build_executor(ctx: BuildContext) -> object:
    from city.executor import IntentExecutor

    return IntentExecutor(_cwd=Path.cwd())


def _build_issues() -> object:
    from city.issues import CityIssueManager

    return CityIssueManager()


def _build_council(ctx: BuildContext) -> object:
    from city.council import CityCouncil

    council_state_path = ctx.db_path.parent / "council_state.json"
    return CityCouncil(_state_path=council_state_path)


def _build_sankalpa() -> object | None:
    from vibe_core.mahamantra.substrate.sankalpa.will import SankalpaOrchestrator

    return SankalpaOrchestrator()


def _build_reflection() -> object | None:
    from vibe_core.protocols.reflection import BasicReflection

    return BasicReflection()


def _build_audit() -> object | None:
    from vibe_core.mahamantra.audit.kernel import AuditKernel

    return AuditKernel()


def _build_federation(ctx: BuildContext) -> object:
    from city.federation import FederationRelay

    dry_run = getattr(ctx.args, "federation_dry_run", False)
    mothership = getattr(
        ctx.args,
        "mothership",
        ctx.config.get("federation", {}).get("mothership_repo", "kimeisele/steward-protocol"),
    )
    return FederationRelay(
        _mothership_repo=mothership,
        _dry_run=dry_run or not getattr(ctx.args, "federation", False),
    )


def _build_federation_nadi(ctx: BuildContext) -> object | None:
    from city.federation_nadi import FederationNadi

    fed_nadi_dir = ctx.db_path.parent / "federation"
    nadi = FederationNadi(_federation_dir=fed_nadi_dir)
    stats = nadi.stats()
    logger.info(
        "FederationNadi wired (outbox=%d, inbox=%d)",
        stats["outbox_on_disk"],
        stats["inbox_on_disk"],
    )
    return nadi


def _build_learning(ctx: BuildContext) -> object | None:
    from city.learning import CityLearning

    learning = CityLearning(_state_dir=ctx.db_path.parent / "synapses")
    if learning.available:
        logger.info(
            "CityLearning wired (%d synapses)",
            learning.stats().get("synapses", 0),
        )
    return learning


def _build_pathogen_index(ctx: BuildContext) -> object:
    from city.pathogen_index import PathogenIndex

    idx = PathogenIndex()
    reactor = ctx.registry.get("reactor")
    if reactor is not None:
        idx.connect_reactor(reactor)
        logger.info("PathogenIndex: %d pathogens, connected to CityReactor", len(idx.list_pathogens()))
    else:
        logger.info("PathogenIndex: %d pathogens (no reactor)", len(idx.list_pathogens()))
    return idx


def _build_immune(ctx: BuildContext) -> object | None:
    from city.immune import CityImmune

    learning = ctx.registry.get("learning")
    immune = CityImmune(_learning=learning)
    if immune.available:
        logger.info("CityImmune wired (%d remedies)", len(immune.list_remedies()))
    return immune


def _build_prahlad(ctx: BuildContext) -> object | None:
    from vibe_core.naga.services.prahlad.service import PrahladService

    prahlad = PrahladService()
    if ctx.registry.has("council"):
        prahlad.set_ledger(ctx.registry.get("council"))
    return prahlad


def _build_agent_nadi() -> object | None:
    from city.agent_nadi import AgentNadiManager

    nadi = AgentNadiManager()
    if nadi.available:
        logger.info("AgentNadiManager wired")
        return nadi
    return None


def _build_city_nadi() -> object | None:
    from city.nadi_hub import CityNadi

    nadi = CityNadi()
    logger.info("CityNadi wired (%s)", "LocalNadi" if nadi.available else "NullNadi fallback")
    return nadi


def _build_knowledge_graph() -> object | None:
    from city.cognition import get_city_knowledge

    return get_city_knowledge()


def _build_claims() -> object:
    from city.claims import ClaimManager

    return ClaimManager()


def _build_cartridge_factory(ctx: BuildContext) -> object | None:
    from city.cartridge_factory import CartridgeFactory

    if ctx.pokedex is None:
        logger.warning("CartridgeFactory skipped: pokedex not on BuildContext")
        return None
    factory = CartridgeFactory(_pokedex=ctx.pokedex)
    logger.info("CartridgeFactory wired")
    return factory


def _build_city_builder(ctx: BuildContext) -> object | None:
    from city.city_builder import CityBuilder

    if ctx.pokedex is None:
        logger.warning("CityBuilder skipped: pokedex not on BuildContext")
        return None
    base_path = ctx.db_path.parent / "agents"
    builder = CityBuilder(_base_path=base_path, _pokedex=ctx.pokedex)
    logger.info("CityBuilder wired → %s", base_path)
    return builder


def _build_cartridge_loader(ctx: BuildContext) -> object | None:
    from city.cartridge_loader import CityCartridgeLoader

    loader = CityCartridgeLoader()
    names = loader.discover()
    if names:
        logger.info("CartridgeLoader wired (%d static cartridges)", len(names))

    # Wire CartridgeFactory for dynamic cartridge generation
    factory = ctx.registry.get("cartridge_factory")
    if factory is not None:
        loader.set_factory(factory)
        logger.info("CartridgeLoader: dynamic factory wired")

    return loader


def _build_spawner(ctx: BuildContext) -> object | None:
    from city.spawner import AgentSpawner

    if ctx.pokedex is None or ctx.network is None:
        logger.warning("AgentSpawner skipped: pokedex/network not on BuildContext")
        return None
    loader = ctx.registry.get("cartridge_loader")
    factory = ctx.registry.get("cartridge_factory")
    builder = ctx.registry.get("city_builder")
    return AgentSpawner(
        _pokedex=ctx.pokedex,
        _network=ctx.network,
        _cartridge_loader=loader,
        _cartridge_factory=factory,
        _city_builder=builder,
    )


def _build_event_bus() -> object | None:
    from city.cognition import get_city_bus

    return get_city_bus()


def _build_moltbook_assistant(ctx: BuildContext) -> object | None:
    from city.moltbook_assistant import MoltbookAssistant
    from city.registry import SVC_MOLTBOOK_CLIENT

    client = ctx.registry.get(SVC_MOLTBOOK_CLIENT)
    if client is None:
        logger.info("MoltbookAssistant skipped: no MoltbookClient")
        return None
    return MoltbookAssistant(client=client, pokedex=ctx.pokedex)
