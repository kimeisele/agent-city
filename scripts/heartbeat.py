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
    from config import get_config
    _cfg = get_config()
    parser.add_argument(
        "--db", type=str,
        default=_cfg.get("database", {}).get("default_path", "data/city.db"),
        help="Database path",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--governance", action="store_true",
        help="Wire Layer 3+4 governance (contracts, executor, issues)",
    )
    parser.add_argument(
        "--federation", action="store_true",
        help="Enable federation with mothership (Layer 6)",
    )
    parser.add_argument(
        "--federation-dry-run", action="store_true",
        help="Federation dry-run (log payloads, don't dispatch)",
    )
    parser.add_argument(
        "--mothership", type=str,
        default=_cfg.get("federation", {}).get("mothership_repo", "kimeisele/steward-protocol"),
        help="Mothership repo (owner/name)",
    )
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

    # Layer 3+4 governance wiring (optional)
    governance_kwargs: dict = {}
    if args.governance:
        from city.contracts import create_default_contracts
        from city.council import CityCouncil
        from city.executor import IntentExecutor
        from city.issues import CityIssueManager

        governance_kwargs["_contracts"] = create_default_contracts()
        governance_kwargs["_executor"] = IntentExecutor(_cwd=Path.cwd())
        governance_kwargs["_issues"] = CityIssueManager()

        # Council with persistence (survives restarts)
        council_state_path = db_path.parent / "council_state.json"
        governance_kwargs["_council"] = CityCouncil(_state_path=council_state_path)

        # Layer 3: Sankalpa + Reflection + Audit
        try:
            from vibe_core.mahamantra.substrate.sankalpa.will import (
                SankalpaOrchestrator,
            )
            governance_kwargs["_sankalpa"] = SankalpaOrchestrator()
        except Exception as e:
            logging.getLogger("HEARTBEAT").warning("Sankalpa init failed: %s", e)

        try:
            from vibe_core.protocols.reflection import BasicReflection
            governance_kwargs["_reflection"] = BasicReflection()
        except Exception as e:
            logging.getLogger("HEARTBEAT").warning("Reflection init failed: %s", e)

        try:
            from vibe_core.mahamantra.audit.kernel import AuditKernel
            governance_kwargs["_audit"] = AuditKernel()
        except Exception as e:
            logging.getLogger("HEARTBEAT").warning("Audit init failed: %s", e)

    # Layer 6 federation wiring (optional)
    if args.federation or args.federation_dry_run:
        from city.federation import FederationRelay
        governance_kwargs["_federation"] = FederationRelay(
            _mothership_repo=args.mothership,
            _dry_run=args.federation_dry_run or not args.federation,
        )

    # Hebbian learning: cross-session memory (graceful fallback)
    learning_kwargs: dict = {}
    try:
        from city.learning import CityLearning
        city_learning = CityLearning(_state_dir=db_path.parent / "synapses")
        if city_learning.available:
            learning_kwargs["_learning"] = city_learning
            logging.getLogger("HEARTBEAT").info(
                "CityLearning wired (%d synapses)", city_learning.stats().get("synapses", 0),
            )
        else:
            logging.getLogger("HEARTBEAT").info("CityLearning wired (null fallback)")
    except Exception as e:
        logging.getLogger("HEARTBEAT").debug("CityLearning unavailable: %s", e)

    # Agent Nadi: inter-agent messaging (graceful fallback)
    agent_nadi_kwargs: dict = {}
    try:
        from city.agent_nadi import AgentNadiManager
        agent_nadi = AgentNadiManager()
        if agent_nadi.available:
            agent_nadi_kwargs["_agent_nadi"] = agent_nadi
            logging.getLogger("HEARTBEAT").info("AgentNadiManager wired")
    except Exception as e:
        logging.getLogger("HEARTBEAT").debug("AgentNadiManager unavailable: %s", e)

    # Nadi messaging: structured gateway queue (graceful fallback)
    nadi_kwargs: dict = {}
    try:
        from city.nadi_hub import CityNadi
        city_nadi = CityNadi()
        if city_nadi.available:
            nadi_kwargs["_city_nadi"] = city_nadi
            logging.getLogger("HEARTBEAT").info("CityNadi wired (LocalNadi)")
        else:
            nadi_kwargs["_city_nadi"] = city_nadi
            logging.getLogger("HEARTBEAT").info("CityNadi wired (NullNadi fallback)")
    except Exception as e:
        logging.getLogger("HEARTBEAT").debug("CityNadi unavailable: %s", e)

    # Cognition layer: KnowledgeGraph + EventBus (graceful fallback)
    cognition_kwargs: dict = {}
    try:
        from city.cognition import get_city_bus, get_city_knowledge
        kg = get_city_knowledge()
        if kg is not None:
            cognition_kwargs["_knowledge_graph"] = kg
            logging.getLogger("HEARTBEAT").info("KnowledgeGraph wired")
        bus = get_city_bus()
        if bus is not None:
            cognition_kwargs["_event_bus"] = bus
            logging.getLogger("HEARTBEAT").info("EventBus wired")
    except Exception as e:
        logging.getLogger("HEARTBEAT").debug("Cognition layer unavailable: %s", e)

    mayor = Mayor(
        _pokedex=pokedex,
        _gateway=gateway,
        _network=network,
        _offline_mode=args.offline,
        **governance_kwargs,
        **learning_kwargs,
        **agent_nadi_kwargs,
        **nadi_kwargs,
        **cognition_kwargs,
    )

    # Wire MoltbookClient for DM pipeline (online mode only)
    if not args.offline:
        import os
        api_key = os.environ.get("MOLTBOOK_API_KEY", "")
        if api_key:
            try:
                from vibe_core.mahamantra.adapters.moltbook import MoltbookClient
                mayor._moltbook_client = MoltbookClient(api_key=api_key)
                logging.getLogger("HEARTBEAT").info("Moltbook DM pipeline wired")
            except Exception as e:
                logging.getLogger("HEARTBEAT").warning("MoltbookClient init failed: %s", e)

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
            logging.getLogger("HEARTBEAT").info("Moltbook bridge wired for m/agent-city")
        except Exception as e:
            logging.getLogger("HEARTBEAT").warning("Moltbook bridge init failed: %s", e)

    print(f"=== Agent City Heartbeat — {args.cycles} cycles ===")
    if args.offline:
        print("Mode: OFFLINE (no Moltbook API)")
    print()

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
            logging.getLogger("HEARTBEAT").warning("Bridge state save failed: %s", e)

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
