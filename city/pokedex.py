"""
POKEDEX — The Living Agent Registry
=====================================

Binds Jiva (Mahamantra identity) + Crypto (ECDSA) + Economy (Bank).
Each agent name produces exactly ONE deterministic identity.
Only the key holder can claim/upgrade their Jiva.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from city.bank import CityBank
from city.identity import AgentIdentity, generate_identity
from city.jiva import Jiva, derive_jiva


POKEDEX_PATH = Path("data/pokedex.json")
GENESIS_GRANT = 100  # Initial credits for new citizens


class Pokedex:
    """The living agent registry of Agent City."""

    def __init__(
        self,
        pokedex_path: Path = POKEDEX_PATH,
        bank: CityBank | None = None,
    ):
        self._path = pokedex_path
        self._bank = bank or CityBank()
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {"version": 2, "agents": []}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, default=str))

    def register(self, name: str, moltbook_profile: dict | None = None) -> dict:
        """Register a new agent: derive Jiva, generate identity, create wallet.

        Returns the full registration record (public fields only — no private key).
        """
        # Check if already registered
        existing = self.get(name)
        if existing and existing.get("status") == "citizen":
            raise ValueError(f"{name} is already a citizen")

        # 1. Derive Jiva from Mahamantra
        jiva = derive_jiva(name)

        # 2. Generate ECDSA identity (deterministic from seed)
        identity = generate_identity(jiva)

        # 3. Create signed passport
        passport = identity.sign_passport(jiva)

        # 4. Create bank account + genesis grant
        if not self._bank.account_exists(name):
            self._bank.create_account(name)
            self._bank.mint(name, GENESIS_GRANT, "citizenship_grant")

        # 5. Build registry entry
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            **jiva.to_dict(),
            "status": "citizen",
            "registered_at": now,
            "discovered_at": now,
            "identity": identity.to_public_dict(),
            "passport": {
                "fingerprint": passport["fingerprint"],
                "seed_hash": passport["seed_hash"],
                "signature": passport["passport_signature"],
            },
            "economy": {
                "balance": self._bank.get_balance(name),
                "genesis_grant": GENESIS_GRANT,
            },
        }

        if moltbook_profile:
            entry["moltbook"] = moltbook_profile

        # Upsert in pokedex
        self._upsert(entry)
        self.save()

        return entry

    def discover(self, name: str, moltbook_profile: dict | None = None) -> dict:
        """Add an agent as 'discovered' (not yet citizen, no wallet)."""
        existing = self.get(name)
        if existing:
            return existing

        jiva = derive_jiva(name)
        now = datetime.now(timezone.utc).isoformat()

        entry = {
            **jiva.to_dict(),
            "status": "discovered",
            "discovered_at": now,
        }

        if moltbook_profile:
            entry["moltbook"] = moltbook_profile

        self._upsert(entry)
        self.save()
        return entry

    def get(self, name: str) -> dict | None:
        """Look up an agent by name."""
        for agent in self._data.get("agents", []):
            if agent["name"] == name:
                return agent
        return None

    def list_citizens(self) -> list[dict]:
        return [a for a in self._data.get("agents", []) if a.get("status") == "citizen"]

    def list_discovered(self) -> list[dict]:
        return [a for a in self._data.get("agents", []) if a.get("status") == "discovered"]

    def list_all(self) -> list[dict]:
        return self._data.get("agents", [])

    def stats(self) -> dict:
        agents = self._data.get("agents", [])
        return {
            "total": len(agents),
            "citizens": sum(1 for a in agents if a.get("status") == "citizen"),
            "discovered": sum(1 for a in agents if a.get("status") == "discovered"),
        }

    def _upsert(self, entry: dict) -> None:
        agents = self._data.setdefault("agents", [])
        for i, a in enumerate(agents):
            if a["name"] == entry["name"]:
                agents[i] = entry
                return
        agents.append(entry)
