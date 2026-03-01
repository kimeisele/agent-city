"""
CITY BUILDER — Materialize the Physical City on Disk
=====================================================

Each citizen agent gets a directory under data/agents/{name}/ with
identity, jiva, and cell state files. The city physically builds
itself as agents are discovered and promoted.

Pokedex (SQLite) is SSOT. These files are human-readable snapshots
for inspection, federation, and physical city structure.

manifest.json contains the full AgentSpec — the complete semantic
derivation from Jiva data (guardian, capabilities, QoS, chapter, tier).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from city.guardian_spec import build_agent_spec

logger = logging.getLogger("AGENT_CITY.CITY_BUILDER")


@dataclass
class CityBuilder:
    """Materialize agent directories on disk.

    Creates data/agents/{name}/ with manifest, identity, jiva, and cell
    snapshots when agents are promoted to citizen.
    """

    _base_path: Path  # data/agents/
    _pokedex: object  # city.pokedex.Pokedex

    def materialize(self, name: str) -> Path | None:
        """Create physical agent directory from Pokedex data.

        Returns the agent directory path, or None if agent not found.
        manifest.json is always rewritten (derived snapshot from Pokedex SSOT).
        identity.json and jiva.json are immutable after creation.
        cell.json is always updated.
        """
        agent_data = self._pokedex.get(name)
        if agent_data is None:
            logger.warning("CityBuilder: agent %s not in Pokedex", name)
            return None

        agent_dir = self._base_path / name
        agent_dir.mkdir(parents=True, exist_ok=True)

        classification = agent_data.get("classification", {})
        vibration = agent_data.get("vibration", {})
        identity = agent_data.get("identity")
        oath = agent_data.get("oath")

        # manifest.json — full AgentSpec (always rewritten, derived snapshot)
        spec = build_agent_spec(name, agent_data)
        spec["status"] = agent_data.get("status", "citizen")
        spec["created_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path = agent_dir / "manifest.json"
        manifest_path.write_text(json.dumps(spec, indent=2))

        # identity.json — cryptographic identity (immutable after creation)
        identity_path = agent_dir / "identity.json"
        if not identity_path.exists() and identity is not None:
            identity_data = {
                "fingerprint": identity.get("fingerprint"),
                "public_key": identity.get("public_key"),
                "seed_hash": identity.get("seed_hash"),
                "claim_level": agent_data.get("claim_level", 0),
            }
            if oath is not None:
                identity_data["oath_hash"] = oath.get("hash")
            identity_path.write_text(json.dumps(identity_data, indent=2))

        # jiva.json — immutable classification + vibration
        jiva_path = agent_dir / "jiva.json"
        if not jiva_path.exists():
            jiva_data = {
                "classification": classification,
                "vibration": vibration,
            }
            jiva_path.write_text(json.dumps(jiva_data, indent=2))

        # cell.json — living state snapshot (always updated)
        self._write_cell(name, agent_dir)

        logger.info("CityBuilder: materialized %s → %s", name, agent_dir)
        return agent_dir

    def update_cell(self, name: str) -> None:
        """Update cell.json snapshot for a living agent."""
        agent_dir = self._base_path / name
        if not agent_dir.exists():
            return
        self._write_cell(name, agent_dir)

    def exists(self, name: str) -> bool:
        """Check if agent directory exists."""
        return (self._base_path / name).is_dir()

    def census(self) -> dict:
        """Count physical agent directories."""
        if not self._base_path.exists():
            return {"total": 0, "agents": []}
        agents = [d.name for d in self._base_path.iterdir() if d.is_dir()]
        return {"total": len(agents), "agents": sorted(agents)}

    def _write_cell(self, name: str, agent_dir: Path) -> None:
        """Write cell.json with current prana/cycle state."""
        cell = self._pokedex.get_cell(name)
        if cell is None:
            return
        cell_data = {
            "prana": cell.prana,
            "is_alive": cell.is_alive,
            "age": cell.age,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (agent_dir / "cell.json").write_text(json.dumps(cell_data, indent=2))
