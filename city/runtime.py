from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from city.registry import (
    SVC_CAMPAIGNS,
    SVC_DISCUSSIONS,
    SVC_MOLTBOOK_ASSISTANT,
    SVC_MOLTBOOK_CLIENT,
    CityServiceRegistry,
)

if TYPE_CHECKING:
    from city.mayor import Mayor
    from city.mayor.lifecycle import MayorLifecycleBridge
    from city.pokedex import Pokedex
    from city.supervision import CitySupervisionBridge


@dataclass(frozen=True)
class RuntimeStatePaths:
    db_path: Path
    discovery_db_path: Path
    mayor_state_path: Path
    bridge_state_path: Path
    campaigns_state_path: Path
    assistant_state_path: Path
    discussions_state_path: Path
    venu_state_path: Path
    city_registry_state_path: Path

    @classmethod
    def from_db_path(cls, db_path: Path) -> "RuntimeStatePaths":
        root = db_path.parent
        return cls(
            db_path=db_path,
            discovery_db_path=root / "discovery.db",
            mayor_state_path=root / "mayor_state.json",
            bridge_state_path=root / "bridge_state.json",
            campaigns_state_path=root / "campaigns_state.json",
            assistant_state_path=root / "assistant_state.json",
            discussions_state_path=root / "discussions_state.json",
            venu_state_path=root / "venu_state.bin",
            city_registry_state_path=root / "city_registry_state.json",
        )


@dataclass
class CityRuntime:
    db_path: Path
    registry: CityServiceRegistry
    mayor: Mayor
    pokedex: Pokedex
    discovery_ledger: DiscoveryLedger
    factory_stats: dict
    state_paths: RuntimeStatePaths
    mayor_lifecycle: MayorLifecycleBridge | None = None
    supervision: CitySupervisionBridge | None = None
    assistant: object | None = None
    discussions: object | None = None


def bootstrap_steward_substrate(
    log: logging.Logger,
    *,
    silent: bool = False,
    lazy: bool = True,
) -> None:
    from vibe_core.mahamantra import BootMode, mahamantra

    mahamantra.bootstrap(silent=silent, lazy=lazy)
    modes = ", ".join(mode.value for mode in BootMode)
    log.info("Mahamantra substrate bootstrapped (lazy=%s, boot_modes=%s)", lazy, modes)


def build_city_runtime(*, args: object, config: dict, log: logging.Logger) -> CityRuntime:
    bootstrap_steward_substrate(log)

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank
    from city.factory import BuildContext, CityServiceFactory, default_definitions, _perform_state_migration
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.mayor.lifecycle import MayorLifecycleBridge
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from city.supervision import CitySupervisionBridge

    db_path = Path(getattr(args, "db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    state_paths = RuntimeStatePaths.from_db_path(db_path)

    from city.discovery_ledger import DiscoveryLedger
    from city.signal_state_ledger import SignalStateLedger

    discovery_ledger = DiscoveryLedger(db_path=str(state_paths.discovery_db_path))
    signal_state_ledger = SignalStateLedger(
        db_path=str(db_path.parent / "signal_state.db")
    )

    bank = CivicBank(db_path=str(db_path.parent / "economy.db"))
    pokedex = Pokedex(db_path=str(db_path), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    registry = CityServiceRegistry()
    # Register ledgers early so factory can reuse them
    from city.registry import SVC_DISCOVERY_LEDGER, SVC_SIGNAL_STATE_LEDGER
    registry.register(SVC_DISCOVERY_LEDGER, discovery_ledger)
    registry.register(SVC_SIGNAL_STATE_LEDGER, signal_state_ledger)

    build_ctx = BuildContext(
        registry=registry,
        db_path=db_path,
        offline=getattr(args, "offline", False),
        args=args,
        config=config,
        pokedex=pokedex,
        discovery_ledger=discovery_ledger,
        network=network,
    )

    from city.federation_propagation import get_propagation_engine
    get_propagation_engine().set_discovery_ledger(discovery_ledger)

    # Perform state migration once both ledgers are ready
    from city.factory import _perform_state_migration
    _perform_state_migration(pokedex, discovery_ledger, signal_state_ledger)

    # Wire MoltbookClient BEFORE factory — the assistant needs it during build
    _wire_moltbook_client_early(registry, log)

    definitions = default_definitions(
        governance=getattr(args, "governance", False),
        federation=(
            getattr(args, "federation", False)
            or getattr(args, "federation_dry_run", False)
        ),
    )
    factory = CityServiceFactory(definitions)
    disabled = config.get("services", {}).get("disabled", [])
    factory.build_all(registry, build_ctx, disabled=disabled)

    mayor_lifecycle = MayorLifecycleBridge(state_path=state_paths.mayor_state_path)
    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _state_path=state_paths.mayor_state_path,
        _lifecycle=mayor_lifecycle,
        _registry=registry,
        _offline_mode=getattr(args, "offline", False),
    )
    runtime = CityRuntime(
        db_path=db_path,
        registry=registry,
        mayor=mayor,
        pokedex=pokedex,
        discovery_ledger=discovery_ledger,
        factory_stats=factory.stats(),
        mayor_lifecycle=mayor_lifecycle,
        supervision=CitySupervisionBridge(mayor=mayor),
        assistant=registry.get(SVC_MOLTBOOK_ASSISTANT),
        discussions=registry.get(SVC_DISCUSSIONS),
        state_paths=state_paths,
    )

    _wire_moltbook_client(runtime=runtime, log=log)
    _wire_moltbook_bridge(runtime=runtime, config=config, log=log)
    _restore_json_state(
        runtime.registry.get(SVC_CAMPAIGNS),
        state_paths.campaigns_state_path,
        log,
        label="Campaigns",
    )
    _restore_json_state(
        runtime.assistant,
        state_paths.assistant_state_path,
        log,
        label="Assistant",
    )
    _restore_venu_state(state_paths.venu_state_path, log)
    _restore_discussions_state(state_paths.discussions_state_path, log)
    _spawn_system_agents(runtime.registry, log)
    return runtime


def persist_city_runtime(runtime: CityRuntime, log: logging.Logger) -> None:
    _persist_json_state(
        getattr(runtime.mayor, "_moltbook_bridge", None),
        runtime.state_paths.bridge_state_path,
        log,
        label="Bridge",
    )
    _persist_json_state(
        runtime.registry.get(SVC_CAMPAIGNS),
        runtime.state_paths.campaigns_state_path,
        log,
        label="Campaigns",
    )
    _persist_json_state(
        runtime.assistant,
        runtime.state_paths.assistant_state_path,
        log,
        label="Assistant",
    )
    _persist_discussions_state(runtime.state_paths.discussions_state_path, log)
    _persist_venu_state(runtime.state_paths.venu_state_path, log)
    _checkpoint_pokedex(runtime.pokedex, log)


def build_daemon_service(runtime: CityRuntime) -> object:
    from city.daemon import DaemonService

    return DaemonService(
        mayor=runtime.mayor,
        supervision=runtime.supervision,
    )


def _wire_moltbook_client_early(registry: object, log: logging.Logger) -> None:
    """Register MoltbookClient in registry BEFORE factory builds services.

    The MoltbookAssistant depends on SVC_MOLTBOOK_CLIENT in the registry.
    If we register the client after factory.build_all(), the assistant
    can't find it and gets skipped.
    """
    api_key = os.environ.get("MOLTBOOK_API_KEY", "")
    if not api_key:
        return

    try:
        from vibe_core.mahamantra.adapters.moltbook import MoltbookClient

        client = MoltbookClient(api_key=api_key)
        registry.register(SVC_MOLTBOOK_CLIENT, client)
        log.info("MoltbookClient registered early (before factory)")
    except Exception as exc:
        log.warning("MoltbookClient early init failed: %s", exc)


def _wire_moltbook_client(*, runtime: CityRuntime, log: logging.Logger) -> None:
    """Wire MoltbookClient to mayor (legacy path) + ensure registry."""
    if runtime.mayor._offline_mode:
        return

    client = runtime.registry.get(SVC_MOLTBOOK_CLIENT)
    if client is None:
        # Fallback: try late init if early init failed
        api_key = os.environ.get("MOLTBOOK_API_KEY", "")
        if not api_key:
            return
        try:
            from vibe_core.mahamantra.adapters.moltbook import MoltbookClient

            client = MoltbookClient(api_key=api_key)
            runtime.registry.register(SVC_MOLTBOOK_CLIENT, client)
        except Exception as exc:
            log.warning("MoltbookClient init failed: %s", exc)
            return

    runtime.mayor._moltbook_client = client
    log.info("Moltbook DM pipeline wired (client in registry)")


def _wire_moltbook_bridge(*, runtime: CityRuntime, config: dict, log: logging.Logger) -> None:
    if runtime.mayor._moltbook_client is None:
        return

    try:
        from city.moltbook_bridge import MoltbookBridge

        own_username = config.get("moltbook_bridge", {}).get("own_username", "")
        bridge = MoltbookBridge(
            _client=runtime.mayor._moltbook_client,
            _own_username=own_username,
        )
        if runtime.state_paths.bridge_state_path.exists():
            bridge.restore(json.loads(runtime.state_paths.bridge_state_path.read_text()))
        runtime.mayor._moltbook_bridge = bridge
        log.info("Moltbook bridge wired for m/agent-city")
    except Exception as exc:
        log.warning("Moltbook bridge init failed: %s", exc)


def _restore_json_state(
    service: object | None,
    path: Path,
    log: logging.Logger,
    *,
    label: str,
) -> None:
    if service is None or not path.exists() or not hasattr(service, "restore"):
        return
    try:
        service.restore(json.loads(path.read_text()))
    except Exception as exc:
        log.warning("%s state restore failed: %s", label, exc)


def _persist_json_state(
    service: object | None,
    path: Path,
    log: logging.Logger,
    *,
    label: str,
) -> None:
    if service is None or not hasattr(service, "snapshot"):
        return
    try:
        path.write_text(json.dumps(service.snapshot(), indent=2))
    except Exception as exc:
        log.warning("%s state save failed: %s", label, exc)


def _restore_venu_state(path: Path, log: logging.Logger) -> None:
    try:
        from vibe_core.mahamantra import mahamantra

        if path.exists():
            mahamantra.venu.from_bytes(path.read_bytes())
            log.info("VenuOrchestrator restored (tick=%d)", mahamantra.venu.tick)
    except Exception as exc:
        log.debug("VenuOrchestrator restore skipped: %s", exc)


def _persist_venu_state(path: Path, log: logging.Logger) -> None:
    try:
        from vibe_core.mahamantra import mahamantra

        path.write_bytes(mahamantra.venu.to_bytes())
        log.info("VenuOrchestrator saved (tick=%d)", mahamantra.venu.tick)
    except Exception as exc:
        log.warning("VenuOrchestrator save failed: %s", exc)


def _restore_city_registry_state(path: Path, log: logging.Logger) -> None:
    if path.exists():
        log.info(
            "CityRegistry snapshot ignored: %s is deprecated; city.db is authoritative",
            path,
        )


def _restore_discussions_state(path: Path, log: logging.Logger) -> None:
    if path.exists():
        log.info(
            "Discussions snapshot ignored: %s is deprecated; city.db is authoritative",
            path,
        )


def _persist_city_registry_state(path: Path, log: logging.Logger) -> None:
    log.debug(
        "CityRegistry snapshot disabled for %s; runtime authority lives in city.db",
        path,
    )


def _persist_discussions_state(path: Path, log: logging.Logger) -> None:
    log.debug(
        "Discussions snapshot disabled for %s; runtime authority lives in city.db",
        path,
    )


def _spawn_system_agents(registry: CityServiceRegistry, log: logging.Logger) -> None:
    from city.registry import SVC_SPAWNER

    spawner = registry.get(SVC_SPAWNER)
    if spawner is None:
        return

    sys_agents = spawner.spawn_system_agents()
    if sys_agents:
        log.info("Spawned %d system agents: %s", len(sys_agents), sys_agents)

    materialized = spawner.materialize_existing()
    if materialized:
        log.info("Materialized %d existing citizens", materialized)


def _checkpoint_pokedex(pokedex: object, log: logging.Logger) -> None:
    try:
        pokedex._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        pokedex._conn.close()
        log.info("Pokedex DB checkpointed and closed")
    except Exception as exc:
        log.warning("Pokedex DB checkpoint failed: %s", exc)
