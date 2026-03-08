"""CLI tests for campaign bootstrap and inspection."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_campaign_cli_apply_list_show(tmp_path: Path):
    payload_path = tmp_path / "campaign.json"
    payload_path.write_text(
        json.dumps(
            {
                "id": "internet-adaptation",
                "title": "Internet adaptation",
                "north_star": "Continuously adapt to relevant new protocols and standards.",
                "success_signals": [
                    {
                        "kind": "active_missions_at_most",
                        "target": 2,
                        "description": "keep execution bounded",
                    }
                ],
            }
        )
    )
    db_path = tmp_path / "city.db"

    apply_result = subprocess.run(
        [
            sys.executable,
            "scripts/campaigns.py",
            "--db",
            str(db_path),
            "--offline",
            "apply",
            "--file",
            str(payload_path),
        ],
        cwd=Path(__file__).parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    apply_payload = json.loads(apply_result.stdout)
    assert apply_payload == {
        "applied": 1,
        "replace": False,
        "campaign_ids": ["internet-adaptation"],
    }

    list_result = subprocess.run(
        [sys.executable, "scripts/campaigns.py", "--db", str(db_path), "--offline", "list"],
        cwd=Path(__file__).parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(list_result.stdout)
    assert summary[0]["id"] == "internet-adaptation"
    assert summary[0]["status"] == "active"

    show_result = subprocess.run(
        [
            sys.executable,
            "scripts/campaigns.py",
            "--db",
            str(db_path),
            "--offline",
            "show",
            "internet-adaptation",
        ],
        cwd=Path(__file__).parent.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    campaign = json.loads(show_result.stdout)
    assert campaign["id"] == "internet-adaptation"
    assert campaign["north_star"].startswith("Continuously adapt")