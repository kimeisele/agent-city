#!/usr/bin/env python3
"""
FederationNadi Bridge CLI — Cross-repo Nadi interface.

Steward-protocol calls this to:
  1. Read agent-city's outbox (city reports, events)
  2. Write to agent-city's inbox (directives, intents)
  3. Stat the Nadi channel

Usage:
    # Read outbox (JSON to stdout)
    python scripts/nadi_bridge.py read-outbox

    # Write to inbox
    python scripts/nadi_bridge.py write-inbox \
        --source opus_1 --operation create_mission \
        --payload '{"topic":"fix ruff violations"}'

    # Show stats
    python scripts/nadi_bridge.py stats

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
        "--data-dir", type=str, default="data/federation",
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

    # clear-outbox
    sub.add_parser("clear-outbox", help="Clear processed outbox messages")

    # stats
    sub.add_parser("stats", help="Show Nadi channel stats")

    args = parser.parse_args()

    from city.federation_nadi import FederationNadi

    nadi = FederationNadi(_federation_dir=Path(args.data_dir))

    if args.command == "read-outbox":
        _read_outbox(nadi)
    elif args.command == "write-inbox":
        _write_inbox(nadi, args)
    elif args.command == "clear-outbox":
        _clear_outbox(nadi)
    elif args.command == "stats":
        _show_stats(nadi)


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
        "target": "agent-city",
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


if __name__ == "__main__":
    main()
