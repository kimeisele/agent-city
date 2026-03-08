#!/usr/bin/env python3
"""Campaign CLI — seed and inspect heartbeat-driven long-horizon campaigns."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Campaign CLI")
    from config import get_config

    cfg = get_config()
    parser.add_argument(
        "--db",
        default=cfg.get("database", {}).get("default_path", "data/city.db"),
        help="Database path",
    )
    parser.add_argument("--offline", action="store_true", help="Offline mode")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="List campaign summaries")
    list_cmd.add_argument("--active-only", action="store_true", help="Only show active campaigns")

    show_cmd = sub.add_parser("show", help="Show one campaign")
    show_cmd.add_argument("campaign_id", help="Campaign id")

    apply_cmd = sub.add_parser("apply", help="Apply campaigns from JSON")
    apply_cmd.add_argument("--file", required=True, help="JSON file containing campaign data")
    apply_cmd.add_argument("--replace", action="store_true", help="Replace all campaigns before applying")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    runtime = _build_runtime(db=args.db, offline=args.offline, cfg=cfg)

    from city.registry import SVC_CAMPAIGNS
    from city.runtime import persist_city_runtime

    campaigns = runtime.registry.get(SVC_CAMPAIGNS)
    if campaigns is None:
        raise SystemExit("campaign service unavailable")

    if args.command == "list":
        print(json.dumps(campaigns.summary(active_only=args.active_only), indent=2))
        return

    if args.command == "show":
        campaign = campaigns.get_campaign(args.campaign_id)
        if campaign is None:
            raise SystemExit(f"unknown campaign: {args.campaign_id}")
        print(json.dumps(campaign.to_dict(), indent=2))
        return

    payload = _load_payload(Path(args.file))
    applied = campaigns.apply_payload(payload, replace=args.replace)
    persist_city_runtime(runtime, logging.getLogger("CAMPAIGNS"))
    print(
        json.dumps(
            {
                "applied": len(applied),
                "replace": args.replace,
                "campaign_ids": [campaign.id for campaign in applied],
            },
            indent=2,
        )
    )


def _build_runtime(*, db: str, offline: bool, cfg: dict):
    from city.runtime import build_city_runtime

    args = SimpleNamespace(
        db=db,
        offline=offline,
        governance=True,
        federation=False,
        federation_dry_run=False,
    )
    return build_city_runtime(args=args, config=cfg, log=logging.getLogger("CAMPAIGNS"))


def _load_payload(path: Path) -> dict:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "campaigns" in payload:
        return payload
    if isinstance(payload, dict) and "id" in payload:
        return {"campaigns": [payload]}
    raise SystemExit("campaign file must contain a campaign object or {\"campaigns\": [...]} payload")


if __name__ == "__main__":
    main()