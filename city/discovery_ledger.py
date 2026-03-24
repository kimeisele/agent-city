"""
DISCOVERY LEDGER — Ephemeral and External State
==============================================

SQLite-backed ledger for scanning, scouting, and throttling.
Keeps the core Pokedex pristine by isolating non-civic state.

Includes:
- Discovered Repositories (Active Discovery)
- Propagation Throttling (Federation SOS)
- System Metadata (Hook state/cooldowns)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("AGENT_CITY.DISCOVERY_LEDGER")


class DiscoveryLedger:
    """Isolates discovery and scanning state from the core Pokedex."""

    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Schema discipline: ensure all required tables exist."""
        cur = self._conn.cursor()

        # Discovery: External Repositories (Scouted but not yet citizens)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS discovered_repos (
                full_name TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                description TEXT,
                stars INTEGER,
                language TEXT,
                discovered_at TEXT NOT NULL,
                processed_at TEXT,
                relevance_score REAL DEFAULT 0.0,
                semantic_fit_score REAL,
                semantic_analysis TEXT,
                evaluation_status TEXT,  -- FIT, REJECTED, NEEDS_HUMAN_REVIEW
                evaluation_reason TEXT
            )
        """)

        # Federation: Propagation Throttling (Persistent SOS control)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS propagation_throttle (
                gap_id TEXT PRIMARY KEY,
                last_propagated_at TEXT NOT NULL
            )
        """)

        # System Metadata (Context for discovery hooks, last-run timestamps)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        self._conn.commit()

    # ── Throttling ──────────────────────────────────────────────────

    def get_last_propagation_time(self, gap_id: str) -> float:
        """Get timestamp of last propagation for a gap."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT last_propagated_at FROM propagation_throttle WHERE gap_id = ?",
                (gap_id,),
            )
            row = cur.fetchone()
            if not row:
                return 0.0
            try:
                dt = datetime.fromisoformat(row[0])
                return dt.timestamp()
            except Exception:
                return 0.0

    def mark_propagated(self, gap_id: str) -> None:
        """Mark a gap as propagated NOW."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO propagation_throttle (gap_id, last_propagated_at) VALUES (?, ?)",
                (gap_id, now),
            )
            self._conn.commit()

    # ── Discovery ─────────────────────────────────────────────────────

    def add_discovered_repo(self, repo_data: dict) -> bool:
        """Add a discovered GitHub repository. Returns True if new."""
        full_name = repo_data["full_name"]
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM discovered_repos WHERE full_name = ?", (full_name,))
            if cur.fetchone():
                return False

            cur.execute(
                """
                INSERT INTO discovered_repos (
                    full_name, url, description, stars, language, discovered_at, relevance_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    full_name,
                    repo_data.get("html_url", ""),
                    repo_data.get("description", ""),
                    repo_data.get("stargazers_count", 0),
                    repo_data.get("language", ""),
                    now,
                    repo_data.get("relevance_score", 0.0),
                ),
            )
            self._conn.commit()
            return True

    def get_unprocessed_repos(self, limit: int = 10) -> list[dict]:
        """Get discovered repositories that haven't been processed yet."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT full_name, url, description, stars, language, relevance_score
                FROM discovered_repos
                WHERE processed_at IS NULL
                ORDER BY relevance_score DESC, stars DESC
                LIMIT ?
            """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def mark_repo_processed(self, full_name: str) -> None:
        """Mark a repository as processed."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE discovered_repos SET processed_at = ? WHERE full_name = ?",
                (now, full_name),
            )
            self._conn.commit()

    def get_unevaluated_repos(self, limit: int = 3) -> list[dict]:
        """Get discovered repositories that haven't been semantically evaluated yet."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT full_name, url, description, stars, language, relevance_score
                FROM discovered_repos
                WHERE evaluation_status IS NULL
                ORDER BY relevance_score DESC, stars DESC
                LIMIT ?
            """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def update_evaluation(self, full_name: str, status: str, reason: str) -> None:
        """Set evaluation status and reason for a repository."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE discovered_repos 
                SET evaluation_status = ?, evaluation_reason = ?, processed_at = ? 
                WHERE full_name = ?
                """,
                (status, reason, now, full_name),
            )
            self._conn.commit()

    # ── Metadata ──────────────────────────────────────────────────────

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        """Get system metadata value."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT value FROM system_meta WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        """Set system metadata value."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO system_meta (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
            self._conn.commit()

            self._conn.commit()
