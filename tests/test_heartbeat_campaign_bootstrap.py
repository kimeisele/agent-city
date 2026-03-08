"""Heartbeat campaign bootstrap tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_heartbeat_module():
    spec = importlib.util.spec_from_file_location(
        "agent_city_heartbeat_script",
        Path(__file__).parent.parent / "scripts" / "heartbeat.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_apply_campaign_manifest_replaces_runtime_campaigns(tmp_path: Path):
    from city.runtime import build_city_runtime

    heartbeat = _load_heartbeat_module()
    args = SimpleNamespace(
        db=str(tmp_path / "city.db"),
        offline=True,
        governance=True,
        federation=False,
        federation_dry_run=False,
    )
    runtime = build_city_runtime(args=args, config={}, log=heartbeat.logging.getLogger("TEST_HEARTBEAT"))

    payload_path = tmp_path / "campaign.json"
    payload_path.write_text(
        json.dumps(
            {
                "campaigns": [
                    {
                        "id": "heartbeat-campaign",
                        "title": "Heartbeat campaign",
                        "north_star": "Stay oriented.",
                    }
                ]
            }
        )
    )

    applied = heartbeat._apply_campaign_manifest(
        runtime,
        manifest_path=payload_path,
        replace=True,
        log=heartbeat.logging.getLogger("TEST_HEARTBEAT"),
        disabled=False,
    )
    assert applied == 1

    campaigns = runtime.registry.get("campaigns")
    summary = campaigns.summary(active_only=True)
    assert summary == [
        {
            "id": "heartbeat-campaign",
            "title": "Heartbeat campaign",
            "north_star": "Stay oriented.",
            "status": "active",
            "last_gap_summary": [],
            "last_evaluated_heartbeat": 0,
        }
    ]


def test_heartbeat_cli_smoke_with_campaign_manifest(tmp_path: Path):
    payload_path = tmp_path / "campaign.json"
    payload_path.write_text(
        json.dumps(
            {
                "campaigns": [
                    {
                        "id": "heartbeat-cli-campaign",
                        "title": "Heartbeat CLI campaign",
                        "north_star": "Stay oriented through heartbeat.",
                    }
                ]
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts/heartbeat.py",
            "--cycles",
            "1",
            "--offline",
            "--governance",
            "--db",
            str(tmp_path / "city.db"),
            "--campaign-file",
            str(payload_path),
        ],
        cwd=Path(__file__).parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "heartbeats complete" in result.stdout.lower()