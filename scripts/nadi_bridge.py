#!/usr/bin/env python3
"""
FederationNadi Bridge CLI — Cross-repo Nadi interface.

Steward-protocol and peer cities call this to:
  1. Read agent-city's outbox (city reports, events)
  2. Write to agent-city's inbox (directives, intents)
  3. Stat the Nadi channel
  4. Manage diplomatic relationships (discover, list-peers, list-allies)

Usage:
    # Read outbox (JSON to stdout)
    python scripts/nadi_bridge.py read-outbox

    # Write to inbox
    python scripts/nadi_bridge.py write-inbox \
        --source opus_1 --operation create_mission \
        --payload '{"topic":"fix ruff violations"}'

    # Show stats
    python scripts/nadi_bridge.py stats

    # Diplomacy: send a diplomatic hello to announce this city
    python scripts/nadi_bridge.py diplomatic-hello --city-repo user/agent-city-fork

    # Diplomacy: list known peer cities
    python scripts/nadi_bridge.py list-peers

    # Diplomacy: list allied/federated cities
    python scripts/nadi_bridge.py list-allies

    # Diplomacy: show diplomacy stats
    python scripts/nadi_bridge.py diplomacy-stats

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure imports work from repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="FederationNadi Bridge CLI")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/federation",
        help="Federation data directory (default: data/federation)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # read-outbox
    sub.add_parser("read-outbox", help="Read outbox messages (JSON to stdout)")

    # write-inbox
    write_cmd = sub.add_parser("write-inbox", help="Write a message to inbox")
    write_cmd.add_argument("--source", required=True, help="Message source (e.g., opus_1)")
    write_cmd.add_argument("--operation", required=True, help="Operation name")
    write_cmd.add_argument("--payload", default="{}", help="JSON payload")
    write_cmd.add_argument("--priority", type=int, default=1, help="Priority (0-3)")
    write_cmd.add_argument("--correlation-id", default="", help="Correlation ID")
    write_cmd.add_argument(
        "--target", default="agent-city",
        help="Target endpoint (default: agent-city)",
    )

    # clear-outbox
    sub.add_parser("clear-outbox", help="Clear processed outbox messages")

    # stats
    sub.add_parser("stats", help="Show Nadi channel stats")

    # diplomatic-hello
    hello_cmd = sub.add_parser(
        "diplomatic-hello",
        help="Announce this city to the federation via outbox",
    )
    hello_cmd.add_argument(
        "--city-repo", required=True,
        help="This city's repo identifier (e.g., user/agent-city)",
    )
    hello_cmd.add_argument(
        "--population", type=int, default=0,
        help="Current population count",
    )

    # list-peers
    sub.add_parser("list-peers", help="List all known peer cities")

    # list-allies
    sub.add_parser("list-allies", help="List allied and federated cities")

    # diplomacy-stats
    sub.add_parser("diplomacy-stats", help="Show diplomacy statistics")

    args = parser.parse_args()
    data_dir = Path(args.data_dir)

    from city.federation_nadi import FederationNadi

    nadi = FederationNadi(_federation_dir=data_dir)

    if args.command == "read-outbox":
        _read_outbox(nadi)
    elif args.command == "write-inbox":
        _write_inbox(nadi, args)
    elif args.command == "clear-outbox":
        _clear_outbox(nadi)
    elif args.command == "stats":
        _show_stats(nadi)
    elif args.command == "diplomatic-hello":
        _diplomatic_hello(nadi, args, data_dir)
    elif args.command == "list-peers":
        _list_peers(data_dir)
    elif args.command == "list-allies":
        _list_allies(data_dir)
    elif args.command == "diplomacy-stats":
        _diplomacy_stats(data_dir)


def _read_outbox(nadi) -> None:
    """Read outbox and print as JSON."""
    if not nadi.outbox_path.exists():
        print("[]")
        return
    data = json.loads(nadi.outbox_path.read_text())
    print(json.dumps(data, indent=2))


def _write_inbox(nadi, args) -> None:
    """Write a message to inbox."""
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON payload: {e}", file=sys.stderr)
        sys.exit(1)

    # Read existing inbox
    inbox_data = []
    if nadi.inbox_path.exists():
        try:
            inbox_data = json.loads(nadi.inbox_path.read_text())
            if not isinstance(inbox_data, list):
                inbox_data = []
        except (json.JSONDecodeError, OSError):
            inbox_data = []

    import time

    message = {
        "source": args.source,
        "target": getattr(args, "target", "agent-city"),
        "operation": args.operation,
        "payload": payload,
        "priority": args.priority,
        "correlation_id": args.correlation_id,
        "timestamp": time.time(),
        "ttl_s": 900.0,
    }
    inbox_data.append(message)

    # Write atomically
    temp = nadi.inbox_path.with_suffix(".tmp")
    temp.write_text(json.dumps(inbox_data, indent=2))
    temp.replace(nadi.inbox_path)

    print(json.dumps({"written": True, "operation": args.operation, "source": args.source}))


def _clear_outbox(nadi) -> None:
    """Clear outbox after mothership has read it."""
    if nadi.outbox_path.exists():
        nadi.outbox_path.write_text("[]")
        print('{"cleared": true}')
    else:
        print('{"cleared": false, "reason": "no outbox file"}')


def _show_stats(nadi) -> None:
    """Print Nadi stats."""
    stats = nadi.stats()
    print(json.dumps(stats, indent=2))


def _diplomatic_hello(nadi, args, data_dir: Path) -> None:
    """Emit a diplomatic_hello to the outbox for federation discovery."""
    import hashlib

    # Compute constitution hash if available
    constitution_hash = ""
    constitution_path = Path("docs/CONSTITUTION.md")
    if constitution_path.exists():
        constitution_hash = hashlib.sha256(
            constitution_path.read_bytes()
        ).hexdigest()[:16]

    nadi.emit(
        source="diplomacy",
        operation="diplomatic_hello",
        payload={
            "city_repo": args.city_repo,
            "population": args.population,
            "constitution_hash": constitution_hash,
        },
        target="federation",  # broadcast to federation, not just mothership
        priority=2,  # SATTVA
    )
    flushed = nadi.flush()

    print(json.dumps({
        "emitted": True,
        "city_repo": args.city_repo,
        "constitution_hash": constitution_hash,
        "flushed": flushed,
    }, indent=2))


def _list_peers(data_dir: Path) -> None:
    """List all known peer cities from diplomacy ledger."""
    from city.federation import DiplomacyLedger

    ledger = DiplomacyLedger(_federation_dir=data_dir)
    peers = ledger.list_peers()
    print(json.dumps([p.to_dict() for p in peers], indent=2))


def _list_allies(data_dir: Path) -> None:
    """List allied and federated cities."""
    from city.federation import DiplomacyLedger

    ledger = DiplomacyLedger(_federation_dir=data_dir)
    allies = ledger.list_allies()
    print(json.dumps([a.to_dict() for a in allies], indent=2))


def _diplomacy_stats(data_dir: Path) -> None:
    """Show diplomacy statistics."""
    from city.federation import DiplomacyLedger

    ledger = DiplomacyLedger(_federation_dir=data_dir)
    print(json.dumps(ledger.stats(), indent=2))


if __name__ == "__main__":
    main()
