"""The heartbeat must execute the pinned Nadi kit, never mutable remote code (S1)."""

from pathlib import Path

NADI_KIT_BLOB_SHA = "47d8e3bbd9cb4256612df1e21ded38b3beb48aa3"


def test_heartbeat_pins_nadi_kit_blob_and_verifies_digest():
    workflow = Path(".github/workflows/agent-city-heartbeat.yml").read_text(encoding="utf-8")
    assert "steward-federation/main/nadi_kit.py" not in workflow
    assert f"git/blobs/{NADI_KIT_BLOB_SHA}" in workflow
    assert "git hash-object nadi_kit.py" in workflow
    assert "digest mismatch" in workflow
