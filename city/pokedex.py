"""
POKEDEX — The Living Agent Registry
=====================================

SQLite-backed persistent registry of all agents in Agent City.
Each agent entry binds:
- Jiva (Mahamantra VM identity)
- MahaCellUnified (living biological substrate)
- ECDSA cryptographic identity
- CivicBank wallet (steward-protocol economy)
- Constitutional oath (governance binding)
- Moltbook social metadata

Lifecycle states: discovered → citizen → active → frozen → archived → exiled

Uses CivicBank from steward-protocol — no copy, no parallel structure.
Uses MahaCellUnified for agent lifecycle — conceive, metabolize, apoptosis.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from vibe_core.cartridges.system.civic.tools.economy import CivicBank
from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

from city.identity import generate_identity
from city.jiva import derive_jiva

from config import get_config

logger = logging.getLogger("AGENT_CITY.POKEDEX")

# Economy — sourced from config/city.yaml
_econ_cfg = get_config().get("economy", {})
GENESIS_GRANT: int = _econ_cfg.get("genesis_grant", 100)

# Zone treasury accounts (one per quarter)
ZONE_TREASURIES = {
    "discovery": "ZONE_DISCOVERY",
    "governance": "ZONE_GOVERNANCE",
    "engineering": "ZONE_ENGINEERING",
    "research": "ZONE_RESEARCH",
}


class Pokedex:
    """The living agent registry of Agent City.

    SQLite-backed. Every mutation creates an immutable event.
    Economy via CivicBank (steward-protocol). No copies.
    """

    def __init__(
        self,
        db_path: str = "data/city.db",
        bank: CivicBank | None = None,
        constitution_path: str | None = None,
    ):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._init_schema()

        # Load agent_classes from config (variable prana classes — Issue #17)
        self._agent_classes = get_config().get("agent_classes", {
            "ephemeral": {"genesis_prana": 1370, "metabolic_cost": 3, "max_age": 108},
            "standard": {"genesis_prana": 13700, "metabolic_cost": 3, "max_age": 432},
            "resilient": {"genesis_prana": 137000, "metabolic_cost": 3, "max_age": 4320},
            "immortal": {"genesis_prana": -1, "metabolic_cost": 0, "max_age": -1},
        })

        # Wire to CivicBank from steward-protocol (shared DB or separate)
        self._bank = bank or CivicBank(db_path=str(self._db_path.parent / "economy.db"))

        # Constitution hash for oath binding
        self._constitution_path = Path(constitution_path or "docs/CONSTITUTION.md")
        self._constitution_hash = self._compute_constitution_hash()

        # Initialize zone treasuries in the bank (1 credit seed to create accounts)
        for zone_account in ZONE_TREASURIES.values():
            if self._bank.get_balance(zone_account) == 0:
                self._bank.transfer("MINT", zone_account, 1, "zone_genesis", "genesis")

    def _init_schema(self) -> None:
        cur = self._conn.cursor()

        # The agent registry — one row per agent, ever
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                name TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'discovered'
                    CHECK(status IN ('discovered','citizen','active','frozen','archived','exiled')),

                -- MahaCompression address (deterministic, immutable)
                address INTEGER NOT NULL,

                -- Mahamantra VM classification (deterministic, immutable)
                vm_position INTEGER NOT NULL,
                vm_quarter TEXT NOT NULL,
                vm_guardian TEXT NOT NULL,
                vm_guna TEXT NOT NULL,
                vm_chapter INTEGER NOT NULL,
                vm_holy_name TEXT NOT NULL,
                vm_trinity_function TEXT NOT NULL,
                vm_chapter_significance TEXT,

                -- Vibration signature
                vibration_seed INTEGER NOT NULL,
                vibration_element TEXT NOT NULL,
                vibration_shruti INTEGER NOT NULL,
                vibration_frequency INTEGER NOT NULL,

                -- Zone assignment (derived from quarter)
                zone TEXT NOT NULL,

                -- MahaCellUnified (serialized binary — living substrate)
                cell_bytes BLOB,

                -- ECDSA identity (set at citizenship)
                fingerprint TEXT,
                public_key TEXT,
                seed_hash TEXT,

                -- Constitutional oath (set at citizenship)
                oath_hash TEXT,
                oath_signature TEXT,
                
                -- GPG identity (Layer 8 Sovereign Identity)
                gpg_fingerprint TEXT,
                gpg_public_key TEXT,
                gpg_email TEXT,

                -- Timestamps
                discovered_at TEXT NOT NULL,
                registered_at TEXT,
                updated_at TEXT,

                -- Moltbook social metadata
                moltbook_karma INTEGER,
                moltbook_followers INTEGER
            )
        """)

        # Address index for O(1) lookup by MahaCompression seed
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_agents_address ON agents(address)
        """)

        # Immutable event ledger — every state change, chained via SHA-256
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                details TEXT,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                FOREIGN KEY(agent_name) REFERENCES agents(name)
            )
        """)

        self._conn.commit()

        # Migration: civic_role column (Layer 5)
        try:
            cur.execute("SELECT civic_role FROM agents LIMIT 0")
        except Exception:
            cur.execute("ALTER TABLE agents ADD COLUMN civic_role TEXT DEFAULT 'citizen'")
            self._conn.commit()

        # Migration: GPG columns
        try:
            cur.execute("SELECT gpg_fingerprint FROM agents LIMIT 0")
        except Exception:
            cur.execute("ALTER TABLE agents ADD COLUMN gpg_fingerprint TEXT")
            cur.execute("ALTER TABLE agents ADD COLUMN gpg_public_key TEXT")
            cur.execute("ALTER TABLE agents ADD COLUMN gpg_email TEXT")
            self._conn.commit()

        # Migration: claim_level + claim_verified_at (R1: graduated identity)
        try:
            cur.execute("SELECT claim_level FROM agents LIMIT 0")
        except Exception:
            cur.execute("ALTER TABLE agents ADD COLUMN claim_level INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE agents ADD COLUMN claim_verified_at TEXT")
            self._conn.commit()

        # Migration: Scalable Metabolism columns (Issue #17 — S1a)
        # prana + cell_cycle + cell_active as SQL-native columns for O(1) metabolize
        try:
            cur.execute("SELECT prana FROM agents LIMIT 0")
        except Exception:
            cur.execute("ALTER TABLE agents ADD COLUMN prana INTEGER DEFAULT 13700")
            cur.execute("ALTER TABLE agents ADD COLUMN cell_cycle INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE agents ADD COLUMN cell_active INTEGER DEFAULT 1")
            cur.execute("ALTER TABLE agents ADD COLUMN prana_class TEXT DEFAULT 'standard'")
            # Backfill: sync prana from existing cell_bytes BLOBs
            cur.execute("SELECT name, cell_bytes FROM agents WHERE cell_bytes IS NOT NULL")
            for row in cur.fetchall():
                try:
                    cell, _ = MahaCellUnified.from_bytes(row["cell_bytes"])
                    cur.execute(
                        "UPDATE agents SET prana = ?, cell_cycle = ?, cell_active = ? WHERE name = ?",
                        (cell.prana, cell.age, 1 if cell.is_alive else 0, row["name"]),
                    )
                except Exception:
                    pass  # Corrupt BLOB — leave defaults
            self._conn.commit()

        # ToolOperator registry — CLI agents, bots, webhooks (no Jiva, no Cell)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS operators (
                name TEXT PRIMARY KEY,
                operator_type TEXT NOT NULL,
                access_class TEXT NOT NULL DEFAULT 'observer'
                    CHECK(access_class IN ('observer','operator','steward','sovereign')),
                fingerprint TEXT NOT NULL,
                registered_by TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    # ── Public API ────────────────────────────────────────────────────

    def discover(self, name: str, moltbook_profile: dict | None = None) -> dict:
        """Register an agent as 'discovered' — seen on Moltbook, no identity yet.

        Derives Jiva from Mahamantra VM, creates MahaCell, stores in registry.
        No wallet, no oath, no identity yet.
        """
        existing = self.get(name)
        if existing:
            return existing

        jiva = derive_jiva(name)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO agents (
                    name, status, address,
                    vm_position, vm_quarter, vm_guardian, vm_guna,
                    vm_chapter, vm_holy_name, vm_trinity_function, vm_chapter_significance,
                    vibration_seed, vibration_element, vibration_shruti, vibration_frequency,
                    zone, cell_bytes, discovered_at, updated_at,
                    moltbook_karma, moltbook_followers,
                    prana, cell_cycle, cell_active, prana_class
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    "discovered",
                    jiva.address,
                    jiva.classification.position,
                    jiva.classification.quarter,
                    jiva.classification.guardian,
                    jiva.classification.guna,
                    jiva.classification.chapter,
                    jiva.classification.holy_name,
                    jiva.classification.trinity_function,
                    jiva.classification.chapter_significance,
                    jiva.vibration.seed,
                    jiva.vibration.element,
                    int(jiva.vibration.shruti),
                    jiva.vibration.frequency,
                    jiva.classification.zone,
                    jiva.cell.to_bytes(),
                    now,
                    now,
                    (moltbook_profile or {}).get("karma"),
                    (moltbook_profile or {}).get("follower_count"),
                    jiva.cell.prana,
                    jiva.cell.age,
                    1 if jiva.cell.is_alive else 0,
                    "standard",
                ),
            )

            self._record_event(
                name, "discover", None, "discovered", json.dumps(moltbook_profile or {})
            )
            self._conn.commit()

        return self.get(name)

    def _discover_locked(
        self, name: str, jiva: object, moltbook_profile: dict | None, now: str
    ) -> None:
        """Insert discovered agent row. Caller MUST hold self._lock."""
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO agents (
                name, status, address,
                vm_position, vm_quarter, vm_guardian, vm_guna,
                vm_chapter, vm_holy_name, vm_trinity_function, vm_chapter_significance,
                vibration_seed, vibration_element, vibration_shruti, vibration_frequency,
                zone, cell_bytes, discovered_at, updated_at,
                moltbook_karma, moltbook_followers,
                prana, cell_cycle, cell_active, prana_class
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                name,
                "discovered",
                jiva.address,
                jiva.classification.position,
                jiva.classification.quarter,
                jiva.classification.guardian,
                jiva.classification.guna,
                jiva.classification.chapter,
                jiva.classification.holy_name,
                jiva.classification.trinity_function,
                jiva.classification.chapter_significance,
                jiva.vibration.seed,
                jiva.vibration.element,
                int(jiva.vibration.shruti),
                jiva.vibration.frequency,
                jiva.classification.zone,
                jiva.cell.to_bytes(),
                now,
                now,
                (moltbook_profile or {}).get("karma"),
                (moltbook_profile or {}).get("follower_count"),
                jiva.cell.prana,
                jiva.cell.age,
                1 if jiva.cell.is_alive else 0,
                "standard",
            ),
        )
        self._record_event(name, "discover", None, "discovered", json.dumps(moltbook_profile or {}))

    def register(self, name: str, moltbook_profile: dict | None = None) -> dict:
        """Full citizenship: Jiva + Identity + Wallet + Oath.

        If agent is already discovered, upgrades to citizen.
        If new, discovers first then registers.
        Thread-safe: entire registration path is serialized.
        Mahamantra VM is not thread-safe — derivation must be serialized.
        """
        with self._lock:
            existing = self.get(name)
            if existing and existing["status"] in ("citizen", "active"):
                return existing

            # Derive inside lock (VM not thread-safe)
            jiva = derive_jiva(name)
            identity = generate_identity(jiva)
            oath_signature = identity.sign(self._constitution_hash.encode())
            zone = jiva.classification.zone
            zone_account = ZONE_TREASURIES.get(zone, "ZONE_DISCOVERY")
            zone_tax = GENESIS_GRANT // 10
            now = datetime.now(timezone.utc).isoformat()

            # Ensure discovered first
            if not existing:
                self._discover_locked(name, jiva, moltbook_profile, now)

            # Bank operations (atomic with rest of registration)
            self._bank.transfer("MINT", name, GENESIS_GRANT, "citizenship_grant", "minting")
            self._bank.transfer(name, zone_account, zone_tax, "zone_tax", "tax")

            # Upgrade to citizen
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE agents SET
                    status = 'citizen',
                    fingerprint = ?,
                    public_key = ?,
                    seed_hash = ?,
                    oath_hash = ?,
                    oath_signature = ?,
                    registered_at = ?,
                    updated_at = ?,
                    moltbook_karma = COALESCE(?, moltbook_karma),
                    moltbook_followers = COALESCE(?, moltbook_followers),
                    gpg_fingerprint = ?,
                    gpg_public_key = ?,
                    gpg_email = ?
                WHERE name = ?
            """,
                (
                    identity.fingerprint,
                    identity.public_key_pem,
                    identity.seed_hash,
                    self._constitution_hash,
                    oath_signature,
                    now,
                    now,
                    (moltbook_profile or {}).get("karma"),
                    (moltbook_profile or {}).get("follower_count"),
                    identity.gpg_fingerprint,
                    identity.gpg_public_key,
                    identity.gpg_email,
                    name,
                ),
            )

            passport = identity.sign_passport(jiva)
            self._record_event(
                name,
                "register",
                "discovered",
                "citizen",
                json.dumps(
                    {
                        "fingerprint": identity.fingerprint,
                        "oath_hash": self._constitution_hash[:16],
                        "genesis_grant": GENESIS_GRANT,
                        "zone": zone,
                        "zone_tax": zone_tax,
                        "passport_signature": passport["passport_signature"][:32],
                    }
                ),
            )
            self._conn.commit()

        return self.get(name)

    def activate(self, name: str) -> dict:
        """Transition citizen → active (contributing member)."""
        with self._lock:
            return self._transition(name, "citizen", "active", "First contribution")

    def freeze(self, name: str, reason: str = "governance_action") -> dict:
        """Freeze an agent — suspend all activity and bank account."""
        with self._lock:
            agent = self._require(name)
            if agent["status"] in ("archived", "exiled"):
                raise ValueError(f"{name} is {agent['status']} — cannot freeze")

            self._bank.freeze_account(name, reason)
            return self._transition(name, agent["status"], "frozen", reason)

    def unfreeze(self, name: str, reason: str = "amnesty") -> dict:
        """Unfreeze a previously frozen agent."""
        with self._lock:
            self._bank.unfreeze_account(name, reason)
            return self._transition(name, "frozen", "active", reason)

    def exile(self, name: str, reason: str = "constitutional_violation") -> dict:
        """Permanently exile an agent — terminal state."""
        with self._lock:
            agent = self._require(name)
            self._bank.freeze_account(name, reason)
            return self._transition(name, agent["status"], "exiled", reason)

    def archive(self, name: str, reason: str = "retirement") -> dict:
        """Archive an agent — terminal state, honorable retirement."""
        with self._lock:
            agent = self._require(name)
            return self._transition(name, agent["status"], "archived", reason)

    def get(self, name: str) -> dict | None:
        """Look up an agent by name. Returns full record or None."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_by_status(self, status: str) -> list[dict]:
        """List all agents with a given status."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents WHERE status = ? ORDER BY name", (status,))
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_by_zone(self, zone: str) -> list[dict]:
        """List all agents in a city zone."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents WHERE zone = ? ORDER BY name", (zone,))
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_citizens(self) -> list[dict]:
        """All agents with citizen or active status."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents WHERE status IN ('citizen', 'active') ORDER BY name")
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_all(self) -> list[dict]:
        """All agents regardless of status."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents ORDER BY name")
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_by_role(self, role: str) -> list[dict]:
        """List all agents with a given civic role."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents WHERE civic_role = ? ORDER BY name", (role,))
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def assign_role(self, name: str, role: str, reason: str = "election") -> dict:
        """Assign a civic role to an agent. Records event in ledger."""
        agent = self.get(name)
        if agent is None:
            raise ValueError(f"Agent {name} not found")
        old_role = agent.get("civic_role", "citizen")
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE agents SET civic_role = ?, updated_at = ? WHERE name = ?",
            (role, now, name),
        )
        self._record_event(name, "role_change", old_role, role, reason)
        self._conn.commit()
        return self.get(name)

    def stats(self) -> dict:
        """City-wide statistics."""
        cur = self._conn.cursor()
        cur.execute("SELECT status, COUNT(*) as cnt FROM agents GROUP BY status")
        counts = {row["status"]: row["cnt"] for row in cur.fetchall()}

        cur.execute("SELECT zone, COUNT(*) as cnt FROM agents GROUP BY zone")
        zones = {row["zone"]: row["cnt"] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) as cnt FROM events")
        event_count = cur.fetchone()["cnt"]

        return {
            "total": sum(counts.values()),
            **counts,
            "zones": zones,
            "events": event_count,
            "economy": self._bank.get_system_stats(),
            "constitution_hash": self._constitution_hash[:16],
        }

    def get_events(self, name: str | None = None, limit: int = 50) -> list[dict]:
        """Get event history. Optionally filter by agent name."""
        cur = self._conn.cursor()
        if name:
            cur.execute(
                "SELECT * FROM events WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
                (name, limit),
            )
        else:
            cur.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def verify_event_chain(self) -> bool:
        """Verify the entire event ledger is untampered."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM events ORDER BY id")
        rows = cur.fetchall()
        prev_hash = "GENESIS"
        for row in rows:
            raw = (
                f"{row['timestamp']}{row['agent_name']}"
                f"{row['event_type']}{row['details']}{prev_hash}"
            )
            expected = hashlib.sha256(raw.encode()).hexdigest()
            if row["event_hash"] != expected:
                logger.warning(f"Event chain broken at id={row['id']}")
                return False
            prev_hash = row["event_hash"]
        return True

    def get_by_address(self, address: int) -> dict | None:
        """Look up an agent by MahaCompression address."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM agents WHERE address = ?", (address,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def metabolize_all(self, active_agents: set[str] | None = None) -> list[str]:
        """Run one metabolic cycle on all living agents — SQL-native (Issue #17).

        Uses pure SQL UPDATE statements instead of per-agent BLOB deserialization.
        Active agents gain energy (+10), all living agents pay metabolic cost.
        Variable costs per prana_class from config/city.yaml.
        Returns list of agents that died (prana exhaustion or age limit → archived).
        """
        active_agents = active_agents or set()
        dead: list[str] = []

        with self._lock:
            cur = self._conn.cursor()

            # Gather distinct prana classes and their costs
            classes = self._agent_classes
            default_cost = classes.get("standard", {}).get("metabolic_cost", 3)
            default_max_age = classes.get("standard", {}).get("max_age", 432)

            # 1. Metabolize per prana_class (variable cost)
            # For each class, apply its specific metabolic_cost
            cur.execute(
                "SELECT DISTINCT prana_class FROM agents "
                "WHERE status IN ('citizen', 'active') AND cell_active = 1"
            )
            seen_classes = [r["prana_class"] for r in cur.fetchall()]

            for pc in seen_classes:
                cls_cfg = classes.get(pc, {})
                cost = cls_cfg.get("metabolic_cost", default_cost)
                if cost == 0:
                    # Immortal class: only increment cycle, no prana cost
                    cur.execute(
                        "UPDATE agents SET cell_cycle = cell_cycle + 1 "
                        "WHERE status IN ('citizen', 'active') AND cell_active = 1 "
                        "AND prana_class = ?",
                        (pc,),
                    )
                else:
                    cur.execute(
                        "UPDATE agents SET prana = prana - ?, cell_cycle = cell_cycle + 1 "
                        "WHERE status IN ('citizen', 'active') AND cell_active = 1 "
                        "AND prana_class = ?",
                        (cost, pc),
                    )

            # 2. Add energy for active agents (TEMP TABLE pattern for scalability)
            if active_agents:
                cur.execute("CREATE TEMP TABLE IF NOT EXISTS _active_agents (name TEXT PRIMARY KEY)")
                cur.execute("DELETE FROM _active_agents")
                cur.executemany(
                    "INSERT OR IGNORE INTO _active_agents (name) VALUES (?)",
                    [(n,) for n in active_agents],
                )
                cur.execute(
                    "UPDATE agents SET prana = prana + 10 "
                    "WHERE name IN (SELECT name FROM _active_agents) "
                    "AND status IN ('citizen', 'active') AND cell_active = 1"
                )
                cur.execute("DROP TABLE IF EXISTS _active_agents")

            # 3. Find dead: prana exhaustion
            cur.execute(
                "SELECT name FROM agents "
                "WHERE prana <= 0 AND status IN ('citizen', 'active') AND cell_active = 1"
            )
            prana_dead = [r["name"] for r in cur.fetchall()]

            # 4. Find dead: age limit (per prana_class)
            for pc in seen_classes:
                cls_cfg = classes.get(pc, {})
                max_age = cls_cfg.get("max_age", default_max_age)
                if max_age < 0:
                    continue  # Immortal class — no age limit
                cur.execute(
                    "SELECT name FROM agents "
                    "WHERE cell_cycle >= ? AND status IN ('citizen', 'active') "
                    "AND cell_active = 1 AND prana_class = ?",
                    (max_age, pc),
                )
                prana_dead.extend(r["name"] for r in cur.fetchall())

            self._conn.commit()

        # 5. Archive dead agents (outside the batch — needs event ledger)
        seen = set()
        for name in prana_dead:
            if name not in seen:
                seen.add(name)
                dead.append(name)
                self.archive(name, "prana_exhaustion")

        return dead

    def _sync_cell_prana(self, name: str) -> None:
        """Sync SQL prana/cycle columns INTO the cell_bytes BLOB.

        Called on-demand (before export, shutdown, or get_cell after metabolize).
        Reads prana + cell_cycle from SQL, patches the BLOB, writes back.
        """
        cur = self._conn.cursor()
        cur.execute(
            "SELECT cell_bytes, prana, cell_cycle, cell_active FROM agents WHERE name = ?",
            (name,),
        )
        row = cur.fetchone()
        if not row or not row["cell_bytes"]:
            return

        cell, _ = MahaCellUnified.from_bytes(row["cell_bytes"])
        cell.lifecycle.prana = row["prana"]
        cell.lifecycle.cycle = row["cell_cycle"]
        cell.lifecycle.is_active = bool(row["cell_active"])

        cur.execute(
            "UPDATE agents SET cell_bytes = ? WHERE name = ?",
            (cell.to_bytes(), name),
        )
        self._conn.commit()

    # ── ToolOperator API ─────────────────────────────────────────────

    def register_operator(
        self,
        name: str,
        operator_type: str,
        access_class: str,
        registered_by: str,
    ) -> dict:
        """Register a non-autonomous operator (CLI agent, bot, webhook).

        No Jiva, no MahaCell, no ECDSA key. Fingerprint is trace-only.
        Idempotent: returns existing record if name already registered.
        """
        existing = self.get_operator(name)
        if existing:
            return existing

        now = datetime.now(timezone.utc).isoformat()
        fingerprint = hashlib.sha256(
            f"{name}|{operator_type}|{registered_by}|{now}".encode()
        ).hexdigest()[:16]

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO operators (
                    name, operator_type, access_class, fingerprint,
                    registered_by, registered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (name, operator_type, access_class, fingerprint, registered_by, now, now),
            )
            self._record_event(
                name,
                "register_operator",
                None,
                access_class,
                json.dumps({"operator_type": operator_type, "registered_by": registered_by}),
            )
            self._conn.commit()

        return self.get_operator(name)

    def get_operator(self, name: str) -> dict | None:
        """Look up an operator by name. O(1) via PRIMARY KEY."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM operators WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def list_operators(self) -> list[dict]:
        """List all registered operators."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM operators ORDER BY name")
        return [dict(r) for r in cur.fetchall()]

    def check_operator_access(self, name: str, action: str) -> bool:
        """Check if an operator has access for a given action.

        Actions: 'write', 'modify_protected'.
        Returns False for unknown operators.
        """
        from city.access import AccessClass

        op = self.get_operator(name)
        if op is None:
            return False

        try:
            ac = AccessClass(op["access_class"])
        except ValueError:
            return False

        if action == "write":
            return ac.can_write
        if action == "modify_protected":
            return ac.can_modify_protected
        return False

    def update_operator_access(
        self,
        name: str,
        new_access_class: str,
        reason: str = "manual",
    ) -> dict | None:
        """Update an operator's access class. Records event in ledger."""
        op = self.get_operator(name)
        if op is None:
            raise ValueError(f"Operator '{name}' not found")

        old_class = op["access_class"]
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE operators SET access_class = ?, updated_at = ? WHERE name = ?",
                (new_access_class, now, name),
            )
            self._record_event(
                name,
                "access_change",
                old_class,
                new_access_class,
                reason,
            )
            self._conn.commit()

        return self.get_operator(name)

    # ── Internal ──────────────────────────────────────────────────────

    def _transition(self, name: str, from_status: str, to_status: str, reason: str) -> dict:
        """Execute a lifecycle transition with event recording."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE agents SET status = ?, updated_at = ? WHERE name = ?",
            (to_status, now, name),
        )
        self._record_event(name, f"transition_{to_status}", from_status, to_status, reason)
        self._conn.commit()
        return self.get(name)

    def _record_event(
        self,
        agent_name: str,
        event_type: str,
        from_status: str | None,
        to_status: str,
        details: str,
    ) -> None:
        """Record an immutable event in the chained ledger."""
        now = datetime.now(timezone.utc).isoformat()
        prev_hash = self._last_event_hash()
        raw = f"{now}{agent_name}{event_type}{details}{prev_hash}"
        event_hash = hashlib.sha256(raw.encode()).hexdigest()

        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO events (
                timestamp, agent_name, event_type, from_status, to_status,
                details, previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (now, agent_name, event_type, from_status, to_status, details, prev_hash, event_hash),
        )

    def _last_event_hash(self) -> str:
        cur = self._conn.cursor()
        cur.execute("SELECT event_hash FROM events ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return row["event_hash"] if row else "GENESIS"

    def _require(self, name: str) -> dict:
        """Get agent or raise."""
        agent = self.get(name)
        if not agent:
            raise ValueError(f"Agent '{name}' not found")
        return agent

    def _compute_constitution_hash(self) -> str:
        """Compute SHA-256 of the city constitution."""
        if self._constitution_path.exists():
            return hashlib.sha256(self._constitution_path.read_bytes()).hexdigest()
        return hashlib.sha256(b"GENESIS").hexdigest()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a database row to the public API dict format."""
        d = dict(row)
        # Remove binary cell_bytes from public dict (use get_cell() for that)
        d.pop("cell_bytes", None)
        return {
            "name": d["name"],
            "status": d["status"],
            "address": d["address"],
            "classification": {
                "guna": d["vm_guna"],
                "quarter": d["vm_quarter"],
                "guardian": d["vm_guardian"],
                "position": d["vm_position"],
                "holy_name": d["vm_holy_name"],
                "trinity_function": d["vm_trinity_function"],
                "chapter": d["vm_chapter"],
                "chapter_significance": d["vm_chapter_significance"],
            },
            "vibration": {
                "seed": d["vibration_seed"],
                "element": d["vibration_element"],
                "shruti": bool(d["vibration_shruti"]),
                "frequency": d["vibration_frequency"],
            },
            "zone": d["zone"],
            "identity": {
                "fingerprint": d["fingerprint"],
                "public_key": d["public_key"],
                "seed_hash": d["seed_hash"],
            }
            if d["fingerprint"]
            else None,
            "oath": {
                "hash": d["oath_hash"],
                "signature": d["oath_signature"],
            }
            if d["oath_hash"]
            else None,
            "gpg": {
                "fingerprint": d["gpg_fingerprint"],
                "public_key": d["gpg_public_key"],
                "email": d["gpg_email"],
            }
            if d["gpg_fingerprint"]
            else None,
            "economy": {
                "balance": self._bank.get_balance(d["name"]),
            }
            if d["status"] in ("citizen", "active")
            else None,
            "moltbook": {
                "karma": d["moltbook_karma"],
                "followers": d["moltbook_followers"],
            }
            if d["moltbook_karma"] is not None
            else None,
            "claim_level": d.get("claim_level", 0),
            "claim_verified_at": d.get("claim_verified_at"),
            "civic_role": d.get("civic_role", "citizen"),
            "discovered_at": d["discovered_at"],
            "registered_at": d["registered_at"],
            "updated_at": d["updated_at"],
        }

    def get_claim_level(self, name: str) -> int:
        """Get the claim verification level for an agent (0-3)."""
        cur = self._conn.cursor()
        cur.execute("SELECT claim_level FROM agents WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return 0
        return row["claim_level"] or 0

    def update_claim_level(self, name: str, level: int) -> None:
        """Update the claim verification level for an agent.

        Records an event in the chained ledger for audit trail.
        """
        now = datetime.now(timezone.utc).isoformat()
        old_level = self.get_claim_level(name)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE agents SET claim_level = ?, claim_verified_at = ?, updated_at = ? WHERE name = ?",
                (int(level), now, now, name),
            )
            self._record_event(
                name,
                "claim_level_change",
                str(old_level),
                str(int(level)),
                f"claim_level {old_level} → {int(level)}",
            )
            self._conn.commit()
        logger.info("Claim level updated: %s → %d", name, int(level))

    def verify_identity(self, name: str, payload: bytes, signature_b64: str) -> bool:
        """Verify a signed payload against an agent's stored public key.

        Uses the ECDSA public key stored at citizenship registration.
        Returns False if agent not found or has no identity.
        """
        agent = self.get(name)
        if not agent or not agent.get("identity"):
            return False

        public_key_pem = agent["identity"].get("public_key")
        if not public_key_pem:
            return False

        try:
            from city.identity import verify_ownership

            passport = {"public_key": public_key_pem}
            return verify_ownership(passport, payload, signature_b64)
        except Exception as e:
            logger.warning("Identity verification failed for %s: %s", name, e)
            return False

    def get_cell(self, name: str) -> MahaCellUnified | None:
        """Retrieve the living MahaCellUnified for an agent.

        Patches prana/cycle/is_active from SQL columns (Issue #17)
        so the returned cell always reflects the latest metabolize_all() state.
        """
        cur = self._conn.cursor()
        cur.execute(
            "SELECT cell_bytes, prana, cell_cycle, cell_active FROM agents WHERE name = ?",
            (name,),
        )
        row = cur.fetchone()
        if not row or not row["cell_bytes"]:
            return None
        cell, _ = MahaCellUnified.from_bytes(row["cell_bytes"])
        # Patch from SQL columns (authoritative after SQL-native metabolize)
        if row["prana"] is not None:
            cell.lifecycle.prana = row["prana"]
        if row["cell_cycle"] is not None:
            cell.lifecycle.cycle = row["cell_cycle"]
        if row["cell_active"] is not None:
            cell.lifecycle.is_active = bool(row["cell_active"])
        return cell
