"""
SIGNAL STATE LEDGER — Inbound Communication State
==============================================

SQLite-backed ledger for signal deduplication and inbox tracking.
Keeps the core Pokedex pristine by isolating communication state.

Includes:
- Processed Signals (Deduplication)
- Inbox Metadata

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.SIGNAL_STATE_LEDGER")


class SignalStateLedger:
    """Isolates inbound communication state from the core Pokedex and DiscoveryLedger."""

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

        # Signal Deduplication (Moved from Pokedex/Discovery to its own domain)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_signals (
                signal_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                processed_at TEXT NOT NULL
            )
        """)

        # System Metadata (Context for bridge hooks, last-run timestamps)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signal_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Outbound Broadcasts (Deduplication for event-driven social membrane)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS outbound_broadcasts (
                signal_id TEXT,
                target_topic TEXT,
                broadcast_at TEXT NOT NULL,
                PRIMARY KEY (signal_id, target_topic)
            )
        """)

        # Public Replies (Prevent double-replying to same mention/reply)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public_replies (
                signal_id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                replied_at TEXT NOT NULL
            )
        """)

        self._conn.commit()

    # ── Signal Deduplication ──────────────────────────────────────────

    def is_signal_processed(self, signal_id: str) -> bool:
        """Check if a signal has already been processed."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT 1 FROM processed_signals WHERE signal_id = ?",
                (signal_id,),
            )
            return cur.fetchone() is not None

    def mark_signal_processed(self, signal_id: str, source: str) -> None:
        """Mark a signal as processed to prevent duplicate triggers."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO processed_signals (signal_id, source, processed_at) VALUES (?, ?, ?)",
                (signal_id, source, now),
            )
            self._conn.commit()

    # ── Metadata ──────────────────────────────────────────────────────

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        """Get signal-related metadata value."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT value FROM signal_meta WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        """Set signal-related metadata value."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO signal_meta (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
            self._conn.commit()

    # ── Outbound Broadcasts ───────────────────────────────────────────

    def is_broadcasted(self, signal_id: str, topic: str) -> bool:
        """Check if a signal has already been broadcasted to a specific topic."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT 1 FROM outbound_broadcasts WHERE signal_id = ? AND target_topic = ?",
                (signal_id, topic),
            )
            return cur.fetchone() is not None

    def record_broadcast(self, signal_id: str, topic: str) -> None:
        """Record a successful broadcast to prevent duplicate transmissions."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO outbound_broadcasts (signal_id, target_topic, broadcast_at) VALUES (?, ?, ?)",
                (signal_id, topic, now),
            )
            self._conn.commit()

    # ── Public Replies ───────────────────────────────────────────────

    def is_public_reply_sent(self, signal_id: str) -> bool:
        """Check if a public reply has already been sent for this signal."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT 1 FROM public_replies WHERE signal_id = ?",
                (signal_id,),
            )
            return cur.fetchone() is not None

    def record_public_reply(self, signal_id: str, post_id: str) -> None:
        """Record a successful public reply."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO public_replies (signal_id, post_id, replied_at) VALUES (?, ?, ?)",
                (signal_id, post_id, now),
            )
            self._conn.commit()
