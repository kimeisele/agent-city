#!/usr/bin/env python3
"""
Agent City Heartbeat Runner
============================

Runs the Mayor agent for N cycles (default: 4 = 1 full MURALI rotation).

Usage:
    python scripts/heartbeat.py --cycles 4 --offline
    python scripts/heartbeat.py --cycles 8  # 2 full rotations, online

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure imports work from repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent City Heartbeat Runner")
    parser.add_argument(
        "--cycles",
        type=int,
        default=4,
        help="Heartbeat cycles (default: 4)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode (no Moltbook API)",
    )
    from config import get_config

    _cfg = get_config()
    parser.add_argument(
        "--db",
        type=str,
        default=_cfg.get("database", {}).get("default_path", "data/city.db"),
        help="Database path",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--governance",
        action="store_true",
        help="Wire Layer 3+4 governance (contracts, executor, issues)",
    )
    parser.add_argument(
        "--federation",
        action="store_true",
        help="Enable federation with mothership (Layer 6)",
    )
    parser.add_argument(
        "--federation-dry-run",
        action="store_true",
        help="Federation dry-run (log payloads, don't dispatch)",
    )
    parser.add_argument(
        "--mothership",
        type=str,
        default=_cfg.get("federation", {}).get("mothership_repo", "kimeisele/steward-protocol"),
        help="Mothership repo (owner/name)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Continuous daemon mode (adaptive frequency)",
    )
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    log = logging.getLogger("HEARTBEAT")

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.factory import BuildContext, CityServiceFactory, default_definitions
    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from city.registry import CityServiceRegistry

    # Boot city infrastructure
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    bank = CivicBank(db_path=str(db_path.parent / "economy.db"))
    pokedex = Pokedex(db_path=str(db_path), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    # ── Service Registry via Factory ──────────────────────────────
    registry = CityServiceRegistry()
    build_ctx = BuildContext(
        registry=registry,
        db_path=db_path,
        offline=args.offline,
        args=args,
        config=_cfg,
    )

    definitions = default_definitions(
        governance=args.governance,
        federation=args.federation or args.federation_dry_run,
    )
    factory = CityServiceFactory(definitions)
    disabled = _cfg.get("services", {}).get("disabled", [])
    factory.build_all(registry, build_ctx, disabled=disabled)

    from city.mayor import Mayor

    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _registry=registry,
        _offline_mode=args.offline,
    )

    # Wire MoltbookClient for DM pipeline (online mode only)
    if not args.offline:
        import os

        api_key = os.environ.get("MOLTBOOK_API_KEY", "")
        if api_key:
            try:
                from vibe_core.mahamantra.adapters.moltbook import MoltbookClient

                mayor._moltbook_client = MoltbookClient(api_key=api_key)
                log.info("Moltbook DM pipeline wired")
            except Exception as e:
                log.warning("MoltbookClient init failed: %s", e)

    # Wire Moltbook bridge for m/agent-city communication
    if mayor._moltbook_client is not None:
        try:
            import json as _json

            from city.moltbook_bridge import MoltbookBridge

            _bridge_username = _cfg.get("moltbook_bridge", {}).get("own_username", "")
            bridge = MoltbookBridge(
                _client=mayor._moltbook_client,
                _own_username=_bridge_username,
            )
            # Restore persisted state
            _bridge_state_path = db_path.parent / "bridge_state.json"
            if _bridge_state_path.exists():
                try:
                    bridge.restore(_json.loads(_bridge_state_path.read_text()))
                except Exception:
                    pass
            mayor._moltbook_bridge = bridge
            log.info("Moltbook bridge wired for m/agent-city")
        except Exception as e:
            log.warning("Moltbook bridge init failed: %s", e)

    factory_stats = factory.stats()
    print(f"=== Agent City Heartbeat — {args.cycles} cycles ===")
    if args.offline:
        print("Mode: OFFLINE (no Moltbook API)")
    print(
        f"Registry: {len(registry.names())} services wired"
        f" ({len(factory_stats['built'])} built, {len(factory_stats['failed'])} failed,"
        f" {len(factory_stats['skipped'])} skipped)"
    )
    print()

    # Daemon mode: continuous adaptive-frequency operation
    if args.daemon:
        from city.daemon import DaemonService

        daemon = DaemonService(mayor=mayor)
        registry.register("daemon", daemon)
        print("Daemon mode: starting continuous heartbeat (Ctrl+C to stop)")
        try:
            daemon.start(block=True)
        except KeyboardInterrupt:
            daemon.stop()
            print("\nDaemon stopped.")
        return

    results = mayor.run_cycle(args.cycles)

    # Persist bridge state
    if mayor._moltbook_bridge is not None:
        import json as _json

        _bridge_state_path = db_path.parent / "bridge_state.json"
        try:
            _bridge_state_path.write_text(
                _json.dumps(mayor._moltbook_bridge.snapshot(), indent=2),
            )
        except Exception as e:
            log.warning("Bridge state save failed: %s", e)

    for r in results:
        dept = r["department"]
        hb = r["heartbeat"]
        print(f"  [{hb}] {dept}", end="")

        if r["discovered"]:
            print(f" — discovered {len(r['discovered'])} agents")
        elif r["governance_actions"]:
            print(f" — {len(r['governance_actions'])} governance actions")
        elif r["operations"]:
            print(f" — {len(r['operations'])} operations")
        elif r["reflection"]:
            ref = r["reflection"]
            chain = "valid" if ref.get("chain_valid") else "BROKEN"
            total = ref.get("city_stats", {}).get("total", 0)
            print(f" — {total} agents, chain {chain}")
        else:
            print(" — idle")

    print(f"\n=== {len(results)} heartbeats complete ===")


if __name__ == "__main__":
    main()
