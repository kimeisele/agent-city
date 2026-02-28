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
        "--cycles", type=int, default=4, help="Heartbeat cycles (default: 4)",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Offline mode (no Moltbook API)",
    )
    parser.add_argument("--db", type=str, default="data/city.db", help="Database path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    # Boot city infrastructure
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    bank = CivicBank(db_path=str(db_path.parent / "economy.db"))
    pokedex = Pokedex(db_path=str(db_path), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    from city.mayor import Mayor

    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _offline_mode=args.offline,
    )

    print(f"=== Agent City Heartbeat — {args.cycles} cycles ===")
    if args.offline:
        print("Mode: OFFLINE (no Moltbook API)")
    print()

    results = mayor.run_cycle(args.cycles)

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
