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
import fcntl
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Heartbeat file-lock path (Issue #17 S1b — prevents concurrent overlap)
_LOCK_PATH = Path("data/.heartbeat.lock")


def _acquire_heartbeat_lock() -> object:
    """Acquire exclusive file-lock. Exits if another heartbeat is running."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        return fd
    except BlockingIOError:
        print(
            "FATAL: Another heartbeat is already running (lock held). Exiting.",
            file=sys.stderr,
        )
        raise SystemExit(1)


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
    parser.add_argument(
        "--campaign-file",
        type=str,
        default=_cfg.get("campaigns", {}).get("default_manifest", "campaigns/default.json"),
        help="Campaign manifest applied before heartbeat cycles when present",
    )
    parser.add_argument(
        "--no-campaign-bootstrap",
        action="store_true",
        help="Disable automatic campaign manifest application",
    )
    parser.add_argument(
        "--campaign-merge",
        action="store_true",
        help="Merge campaign manifest into existing state instead of replacing campaign state",
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

    # Acquire exclusive heartbeat lock (Issue #17 S1b — single-writer daemon)
    _lock_fd = _acquire_heartbeat_lock()  # noqa: F841 — held for process lifetime
    log.info("Heartbeat lock acquired (pid=%d)", os.getpid())

    from city.registry import SVC_DAEMON
    from city.runtime import build_city_runtime, build_daemon_service, persist_city_runtime

    runtime = build_city_runtime(args=args, config=_cfg, log=log)
    applied_campaigns = _apply_campaign_manifest(
        runtime,
        manifest_path=Path(args.campaign_file),
        replace=not args.campaign_merge,
        log=log,
        disabled=args.no_campaign_bootstrap,
    )

    print(f"=== Agent City Heartbeat — {args.cycles} cycles ===")
    if args.offline:
        print("Mode: OFFLINE (no Moltbook API)")
    print(
        f"Registry: {len(runtime.registry.names())} services wired"
        f" ({len(runtime.factory_stats['built'])} built,"
        f" {len(runtime.factory_stats['failed'])} failed,"
        f" {len(runtime.factory_stats['skipped'])} skipped)"
    )
    print()

    # Daemon mode: continuous adaptive-frequency operation
    if args.daemon:
        daemon = build_daemon_service(runtime)
        runtime.registry.register(SVC_DAEMON, daemon)
        print("Daemon mode: starting continuous heartbeat (Ctrl+C to stop)")
        try:
            daemon.start(block=True)
        except KeyboardInterrupt:
            print("\nDaemon stopped.")
        finally:
            daemon.stop()
            persist_city_runtime(runtime, log)
        return

    results = runtime.mayor.run_cycle(args.cycles)
    persist_city_runtime(runtime, log)

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


def _apply_campaign_manifest(
    runtime,
    *,
    manifest_path: Path,
    replace: bool,
    log: logging.Logger,
    disabled: bool,
) -> int:
    if disabled:
        log.info("Campaign bootstrap disabled")
        return 0

    from city.campaigns import load_campaign_payload
    from city.registry import SVC_CAMPAIGNS

    campaigns = runtime.registry.get(SVC_CAMPAIGNS)
    if campaigns is None:
        log.info("Campaign service unavailable; skipping manifest bootstrap")
        return 0
    if not manifest_path.exists():
        log.info("No campaign manifest at %s; skipping bootstrap", manifest_path)
        return 0

    try:
        payload = load_campaign_payload(manifest_path)
    except ValueError as exc:
        log.warning("Invalid campaign manifest %s: %s", manifest_path, exc)
        return 0

    applied = campaigns.apply_payload(payload, replace=replace)
    log.info(
        "Applied %d campaigns from %s (replace=%s)",
        len(applied),
        manifest_path,
        replace,
    )
    return len(applied)


if __name__ == "__main__":
    main()
