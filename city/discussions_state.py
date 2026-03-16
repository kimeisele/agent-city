from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS discussion_runtime_meta (
    singleton      INTEGER PRIMARY KEY CHECK(singleton = 1),
    last_report_hb INTEGER NOT NULL DEFAULT 0,
    last_post_at   REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS discussion_seen (
    discussion_number INTEGER PRIMARY KEY,
    first_seen_at     REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS discussion_comment_cursor (
    comment_id        TEXT PRIMARY KEY,
    discussion_number INTEGER NOT NULL,
    author            TEXT NOT NULL DEFAULT '',
    body_hash         TEXT NOT NULL,
    first_seen_at     REAL NOT NULL DEFAULT 0.0,
    last_seen_at      REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS discussion_post_dedup (
    content_hash      TEXT PRIMARY KEY,
    discussion_number INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'sent')),
    reserved_at       REAL NOT NULL DEFAULT 0.0,
    sent_at           REAL DEFAULT NULL,
    comment_id        TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS discussion_response_cursor (
    discussion_number INTEGER PRIMARY KEY,
    responded_at      REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS discussion_seed_thread (
    thread_key        TEXT PRIMARY KEY,
    discussion_number INTEGER NOT NULL UNIQUE
);
"""

_POST_RESERVATION_TTL_S = 900.0


class DiscussionsStateStore:
    """SQLite-backed cursor/dedup state for DiscussionsBridge."""

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO discussion_runtime_meta"
                " (singleton, last_report_hb, last_post_at)"
                " VALUES (1, 0, 0.0)"
            )
            self._conn.commit()
        self.purge_stale_post_reservations()

    def load_state(self) -> dict:
        with self._lock:
            meta = self._conn.execute(
                "SELECT last_report_hb, last_post_at"
                " FROM discussion_runtime_meta WHERE singleton = 1"
            ).fetchone()
            seen_discussions = {
                int(r["discussion_number"])
                for r in self._conn.execute("SELECT discussion_number FROM discussion_seen")
            }
            comment_rows = self._conn.execute(
                "SELECT comment_id, body_hash FROM discussion_comment_cursor"
            ).fetchall()
            responded = {
                int(r["discussion_number"]): float(r["responded_at"])
                for r in self._conn.execute(
                    "SELECT discussion_number, responded_at FROM discussion_response_cursor"
                )
            }
            seed_threads = {
                str(r["thread_key"]): int(r["discussion_number"])
                for r in self._conn.execute(
                    "SELECT thread_key, discussion_number FROM discussion_seed_thread"
                )
            }
            posted_hashes = {
                str(r["content_hash"])
                for r in self._conn.execute(
                    "SELECT content_hash FROM discussion_post_dedup WHERE status = 'sent'"
                )
            }
        return {
            "seen_discussion_numbers": seen_discussions,
            "seen_comment_hashes": {
                str(r["comment_id"]): str(r["body_hash"])
                for r in comment_rows
            },
            "seen_comment_ids": {str(r["comment_id"]) for r in comment_rows},
            "responded_discussions": responded,
            "seed_threads": seed_threads,
            "posted_hashes": posted_hashes,
            "last_report_hb": int(meta["last_report_hb"]) if meta else 0,
            "last_post_at": float(meta["last_post_at"]) if meta else 0.0,
        }

    def mark_discussion_seen(self, discussion_number: int, now: float | None = None) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO discussion_seen"
                " (discussion_number, first_seen_at) VALUES (?, ?)",
                (discussion_number, now or time.time()),
            )
            self._conn.commit()
        return cur.rowcount == 1

    def upsert_comment_cursor(
        self,
        comment_id: str,
        discussion_number: int,
        author: str,
        body_hash: str,
        now: float | None = None,
    ) -> str:
        ts = now or time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO discussion_comment_cursor
                   (comment_id, discussion_number, author, body_hash, first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (comment_id, discussion_number, author, body_hash, ts, ts),
            )
            if cur.rowcount == 1:
                self._conn.commit()
                return "new"
            row = self._conn.execute(
                "SELECT body_hash FROM discussion_comment_cursor WHERE comment_id = ?",
                (comment_id,),
            ).fetchone()
            if row is not None and row["body_hash"] != body_hash:
                self._conn.execute(
                    """UPDATE discussion_comment_cursor
                       SET discussion_number = ?, author = ?, body_hash = ?, last_seen_at = ?
                       WHERE comment_id = ?""",
                    (discussion_number, author, body_hash, ts, comment_id),
                )
                self._conn.commit()
                return "edited"
            self._conn.execute(
                """UPDATE discussion_comment_cursor
                   SET discussion_number = ?, author = ?, last_seen_at = ?
                   WHERE comment_id = ?""",
                (discussion_number, author, ts, comment_id),
            )
            self._conn.commit()
        return "seen"

    def reserve_post_hash(
        self, content_hash: str, discussion_number: int, now: float | None = None,
    ) -> bool:
        ts = now or time.time()
        with self._lock:
            self._conn.execute(
                "DELETE FROM discussion_post_dedup"
                " WHERE status = 'pending'"
                " AND content_hash = ? AND reserved_at < ?",
                (content_hash, ts - _POST_RESERVATION_TTL_S),
            )
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO discussion_post_dedup
                   (content_hash, discussion_number, status, reserved_at)
                   VALUES (?, ?, 'pending', ?)""",
                (content_hash, discussion_number, ts),
            )
            self._conn.commit()
        return cur.rowcount == 1

    def release_post_hash(self, content_hash: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM discussion_post_dedup WHERE content_hash = ? AND status = 'pending'",
                (content_hash,),
            )
            self._conn.commit()

    def confirm_post_hash(
        self, content_hash: str, comment_id: str, now: float | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE discussion_post_dedup
                   SET status = 'sent', comment_id = ?, sent_at = ?
                   WHERE content_hash = ?""",
                (comment_id, now or time.time(), content_hash),
            )
            self._conn.commit()

    def purge_stale_post_reservations(self, ttl_s: float = _POST_RESERVATION_TTL_S) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM discussion_post_dedup WHERE status = 'pending' AND reserved_at < ?",
                (time.time() - ttl_s,),
            )
            self._conn.commit()
        return cur.rowcount

    def upsert_responded_discussion(self, discussion_number: int, responded_at: float) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO discussion_response_cursor (discussion_number, responded_at)
                   VALUES (?, ?)
                   ON CONFLICT(discussion_number)
                   DO UPDATE SET responded_at = excluded.responded_at""",
                (discussion_number, responded_at),
            )
            self._conn.commit()

    def prune_responded_discussions(self, cutoff: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM discussion_response_cursor WHERE responded_at < ?",
                (cutoff,),
            )
            self._conn.commit()
        return cur.rowcount

    def upsert_seed_thread(self, thread_key: str, discussion_number: int) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO discussion_seed_thread (thread_key, discussion_number)
                   VALUES (?, ?)
                   ON CONFLICT(thread_key)
                   DO UPDATE SET discussion_number = excluded.discussion_number""",
                (thread_key, discussion_number),
            )
            self._conn.commit()

    def set_last_report_hb(self, heartbeat: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE discussion_runtime_meta SET last_report_hb = ? WHERE singleton = 1",
                (heartbeat,),
            )
            self._conn.commit()

    def set_last_post_at(self, timestamp: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE discussion_runtime_meta SET last_post_at = ? WHERE singleton = 1",
                (timestamp,),
            )
            self._conn.commit()