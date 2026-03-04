"""
THREAD STATE — Prana-Based Discussion Lifecycle Engine
========================================================

SQLite-backed state machine for every GitHub Discussion thread.
Each thread has energy (0.0–1.0) that decays without activity.

States: active → waiting → cooling → archived
  - active:   human commented, agent hasn't responded yet (unresolved)
  - waiting:  agent responded, awaiting human follow-up
  - cooling:  no activity for N heartbeats, energy decaying
  - archived: energy exhausted, thread deprioritized

Energy mechanics:
  - New human comment:  energy = 1.0, state = active
  - Agent response:     state = waiting (energy unchanged)
  - Each heartbeat:     energy *= DECAY_RATE (soft decay)
  - Energy < COOL_THRESHOLD: state = cooling
  - Energy < ARCHIVE_THRESHOLD: state = archived

Stored in city.db (agent state, not transport).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("AGENT_CITY.THREAD_STATE")

# Energy decay per heartbeat (~15min). Thread half-life ≈ 8 heartbeats (~2 hours).
DECAY_RATE: float = 0.92
COOL_THRESHOLD: float = 0.3
ARCHIVE_THRESHOLD: float = 0.05

# Repetition detection: if same author posts N+ times without system change, escalate
REPETITION_ESCALATION_COUNT: int = 3


class ThreadStatus(StrEnum):
    """Discussion thread lifecycle states."""
    ACTIVE = "active"
    WAITING = "waiting"
    COOLING = "cooling"
    ARCHIVED = "archived"


class CommentStatus(StrEnum):
    """Comment lifecycle in the ledger.

    seen:     comment ingested, not yet enqueued for processing
    enqueued: handed to gateway queue for KARMA processing
    replied:  system posted a response to this comment
    self:     comment was posted by the system itself (introspectable, not actionable)
    """
    SEEN = "seen"
    ENQUEUED = "enqueued"
    REPLIED = "replied"
    SELF = "self"


@dataclass(frozen=True)
class CommentEntry:
    """Immutable view of a comment ledger row."""
    comment_id: str
    discussion_number: int
    author: str
    body_hash: str
    source: str
    status: str
    seen_at: float
    enqueued_at: float | None
    replied_at: float | None
    reply_comment_id: str | None
    body_text: str | None = None       # 10F: full text for self-posts

    @property
    def needs_processing(self) -> bool:
        return self.status in (CommentStatus.SEEN, CommentStatus.ENQUEUED)

    @property
    def is_from_self(self) -> bool:
        return self.source == "self"


@dataclass(frozen=True)
class ThreadSnapshot:
    """Immutable view of a thread's current state."""
    discussion_number: int
    title: str
    category: str
    energy: float
    status: str
    last_human_comment_at: float
    last_agent_response_at: float
    human_comment_count: int
    response_count: int
    unresolved: bool
    created_at: float

    @property
    def needs_response(self) -> bool:
        """Thread has unresolved human comment needing agent attention."""
        return self.unresolved and self.status in (ThreadStatus.ACTIVE, ThreadStatus.WAITING)

    @property
    def is_alive(self) -> bool:
        return self.status != ThreadStatus.ARCHIVED


_SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_state (
    discussion_number INTEGER PRIMARY KEY,
    title             TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT '',
    energy            REAL NOT NULL DEFAULT 1.0,
    status            TEXT NOT NULL DEFAULT 'active',
    last_human_comment_at   REAL NOT NULL DEFAULT 0.0,
    last_agent_response_at  REAL NOT NULL DEFAULT 0.0,
    human_comment_count     INTEGER NOT NULL DEFAULT 0,
    response_count          INTEGER NOT NULL DEFAULT 0,
    unresolved              INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL DEFAULT 0.0,
    last_human_author       TEXT NOT NULL DEFAULT '',
    consecutive_human_posts  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS comment_ledger (
    comment_id        TEXT PRIMARY KEY,
    discussion_number INTEGER NOT NULL,
    author            TEXT NOT NULL DEFAULT '',
    body_hash         TEXT NOT NULL DEFAULT '',
    source            TEXT NOT NULL DEFAULT 'external',
    status            TEXT NOT NULL DEFAULT 'seen',
    seen_at           REAL NOT NULL DEFAULT 0.0,
    enqueued_at       REAL DEFAULT NULL,
    replied_at        REAL DEFAULT NULL,
    reply_comment_id  TEXT DEFAULT NULL,
    body_text         TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_thread ON comment_ledger(discussion_number);
CREATE INDEX IF NOT EXISTS idx_ledger_status ON comment_ledger(status);
"""


class ThreadStateEngine:
    """Prana-based discussion lifecycle manager.

    Stored in city.db alongside Pokedex. Each heartbeat:
    1. GENESIS: record_human_comment() on new comments from scan
    2. KARMA:   record_agent_response() after posting reply
    3. MOKSHA:  decay_all() to age threads + detect stale ones

    Thread triage: threads_needing_response() for gateway routing.
    """

    def __init__(self, db_path: str = "data/city.db") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # 10F: Backward-compatible migration — add body_text if missing
            try:
                self._conn.execute(
                    "SELECT body_text FROM comment_ledger LIMIT 0",
                )
            except sqlite3.OperationalError:
                self._conn.execute(
                    "ALTER TABLE comment_ledger ADD COLUMN body_text TEXT DEFAULT NULL",
                )
            self._conn.commit()

    # ── Inbound Events ─────────────────────────────────────────────────

    def record_human_comment(
        self,
        discussion_number: int,
        author: str,
        *,
        title: str = "",
        category: str = "",
    ) -> ThreadSnapshot:
        """A human (or external agent) posted a comment.

        Energy resets to 1.0, status becomes ACTIVE, unresolved = True.
        Tracks consecutive posts by same author for repetition detection.
        """
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM thread_state WHERE discussion_number = ?",
                (discussion_number,),
            ).fetchone()

            if row is None:
                # New thread
                self._conn.execute(
                    """INSERT INTO thread_state
                       (discussion_number, title, category, energy, status,
                        last_human_comment_at, human_comment_count, unresolved,
                        created_at, last_human_author, consecutive_human_posts)
                       VALUES (?, ?, ?, 1.0, ?, ?, 1, 1, ?, ?, 1)""",
                    (discussion_number, title, category,
                     ThreadStatus.ACTIVE, now, now, author),
                )
            else:
                # Existing thread — reset energy, increment counts
                prev_author = row["last_human_author"]
                consecutive = row["consecutive_human_posts"]
                if author == prev_author:
                    consecutive += 1
                else:
                    consecutive = 1

                self._conn.execute(
                    """UPDATE thread_state SET
                       energy = 1.0,
                       status = ?,
                       last_human_comment_at = ?,
                       human_comment_count = human_comment_count + 1,
                       unresolved = 1,
                       last_human_author = ?,
                       consecutive_human_posts = ?,
                       title = CASE WHEN ? != '' THEN ? ELSE title END,
                       category = CASE WHEN ? != '' THEN ? ELSE category END
                       WHERE discussion_number = ?""",
                    (ThreadStatus.ACTIVE, now, author, consecutive,
                     title, title, category, category, discussion_number),
                )

            self._conn.commit()

        logger.info(
            "THREAD: #%d human comment by @%s → ACTIVE (energy=1.0)",
            discussion_number, author,
        )
        return self.get(discussion_number)  # type: ignore[return-value]

    def record_agent_response(self, discussion_number: int) -> None:
        """An agent posted a response to this thread.

        Status becomes WAITING, unresolved = False.
        Energy stays the same (agent response doesn't add energy).
        Resets consecutive_human_posts (the system responded).
        """
        now = time.time()
        with self._lock:
            self._conn.execute(
                """UPDATE thread_state SET
                   status = ?,
                   last_agent_response_at = ?,
                   response_count = response_count + 1,
                   unresolved = 0,
                   consecutive_human_posts = 0
                   WHERE discussion_number = ?""",
                (ThreadStatus.WAITING, now, discussion_number),
            )
            self._conn.commit()

        logger.debug("THREAD: #%d agent responded → WAITING", discussion_number)

    # ── Decay (MOKSHA) ─────────────────────────────────────────────────

    def decay_all(self) -> dict:
        """Decay energy for all non-archived threads.

        Called once per heartbeat in MOKSHA.
        Returns: {"decayed": N, "cooled": N, "archived": N}
        """
        stats = {"decayed": 0, "cooled": 0, "archived": 0}

        with self._lock:
            rows = self._conn.execute(
                "SELECT discussion_number, energy, status FROM thread_state WHERE status != ?",
                (ThreadStatus.ARCHIVED,),
            ).fetchall()

            for row in rows:
                num = row["discussion_number"]
                new_energy = row["energy"] * DECAY_RATE
                new_status = row["status"]

                if new_energy < ARCHIVE_THRESHOLD:
                    new_status = ThreadStatus.ARCHIVED
                    new_energy = 0.0
                    stats["archived"] += 1
                elif new_energy < COOL_THRESHOLD and row["status"] != ThreadStatus.COOLING:
                    new_status = ThreadStatus.COOLING
                    stats["cooled"] += 1

                self._conn.execute(
                    "UPDATE thread_state SET energy = ?, status = ? WHERE discussion_number = ?",
                    (new_energy, new_status, num),
                )
                stats["decayed"] += 1

            self._conn.commit()

        if stats["cooled"] or stats["archived"]:
            logger.info(
                "THREAD DECAY: %d decayed, %d cooled, %d archived",
                stats["decayed"], stats["cooled"], stats["archived"],
            )
        return stats

    # ── Queries ────────────────────────────────────────────────────────

    def get(self, discussion_number: int) -> ThreadSnapshot | None:
        """Get current state of a thread."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM thread_state WHERE discussion_number = ?",
                (discussion_number,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_snapshot(row)

    def threads_needing_response(self) -> list[ThreadSnapshot]:
        """Threads with unresolved human comments, ordered by energy (highest first)."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM thread_state
                   WHERE unresolved = 1 AND status != ?
                   ORDER BY energy DESC""",
                (ThreadStatus.ARCHIVED,),
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def active_threads(self) -> list[ThreadSnapshot]:
        """All non-archived threads, ordered by energy."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM thread_state
                   WHERE status != ?
                   ORDER BY energy DESC""",
                (ThreadStatus.ARCHIVED,),
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def repetition_alerts(self) -> list[ThreadSnapshot]:
        """Threads where the same human posted N+ times without agent response.

        This is a pain signal — the system is ignoring repeated feedback.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM thread_state
                   WHERE consecutive_human_posts >= ? AND status != ?
                   ORDER BY consecutive_human_posts DESC""",
                (REPETITION_ESCALATION_COUNT, ThreadStatus.ARCHIVED),
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def stats(self) -> dict:
        """Summary statistics for diagnostics."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) as cnt FROM thread_state GROUP BY status",
            ).fetchall()
        counts = {r["status"]: r["cnt"] for r in rows}
        unresolved = 0
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM thread_state WHERE unresolved = 1 AND status != ?",
                (ThreadStatus.ARCHIVED,),
            ).fetchone()
            if row:
                unresolved = row["cnt"]
        return {
            "by_status": counts,
            "total": sum(counts.values()),
            "unresolved": unresolved,
        }

    # ── Comment Ledger ────────────────────────────────────────────────
    #
    # Every comment (bot OR external) gets a row. No discrimination at
    # the front door. The ledger replaces the dumb _seen_comment_ids set.
    #
    # Lifecycle:  ingest → mark_enqueued → mark_replied
    # Self-posts: ingest with source="self" → status="self" (introspectable)

    def ingest_comment(
        self,
        comment_id: str,
        discussion_number: int,
        author: str,
        body: str,
        *,
        is_own: bool = False,
    ) -> CommentEntry | None:
        """Record a comment in the ledger. Idempotent — returns None if already seen.

        ALL comments enter here. No filtering by author. The source field
        marks whether it came from the system ("self") or externally ("external").
        """
        now = time.time()
        body_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
        source = "self" if is_own else "external"
        status = CommentStatus.SELF if is_own else CommentStatus.SEEN

        with self._lock:
            existing = self._conn.execute(
                "SELECT comment_id FROM comment_ledger WHERE comment_id = ?",
                (comment_id,),
            ).fetchone()
            if existing is not None:
                return None  # already ingested

            # 10F: Store body_text for self-posts (Brain self-awareness)
            stored_body = body if is_own else None
            self._conn.execute(
                """INSERT INTO comment_ledger
                   (comment_id, discussion_number, author, body_hash,
                    source, status, seen_at, body_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (comment_id, discussion_number, author, body_hash,
                 source, status, now, stored_body),
            )
            self._conn.commit()

        return CommentEntry(
            comment_id=comment_id,
            discussion_number=discussion_number,
            author=author,
            body_hash=body_hash,
            source=source,
            status=status,
            seen_at=now,
            enqueued_at=None,
            replied_at=None,
            reply_comment_id=None,
        )

    def reingest_comment(
        self,
        comment_id: str,
        body: str,
    ) -> CommentEntry | None:
        """Re-ingest an edited comment. Updates body_hash and resets status.

        Returns the updated entry, or None if comment_id is not in the ledger.
        """
        now = time.time()
        new_hash = hashlib.sha256(body.encode()).hexdigest()[:16]

        with self._lock:
            row = self._conn.execute(
                """SELECT comment_id, discussion_number, author, body_hash,
                          source, status, seen_at, enqueued_at, replied_at,
                          reply_comment_id
                   FROM comment_ledger WHERE comment_id = ?""",
                (comment_id,),
            ).fetchone()
            if row is None:
                return None  # not previously ingested

            old_hash = row[3]  # body_hash column
            if old_hash == new_hash:
                return None  # body unchanged, no re-ingestion needed

            # Reset to SEEN so it gets re-processed
            new_status = CommentStatus.SEEN
            self._conn.execute(
                """UPDATE comment_ledger
                   SET body_hash = ?, status = ?, seen_at = ?,
                       enqueued_at = NULL, replied_at = NULL, reply_comment_id = NULL
                   WHERE comment_id = ?""",
                (new_hash, new_status, now, comment_id),
            )
            self._conn.commit()

        return CommentEntry(
            comment_id=comment_id,
            discussion_number=row[1],
            author=row[2],
            body_hash=new_hash,
            source=row[4],
            status=new_status,
            seen_at=now,
            enqueued_at=None,
            replied_at=None,
            reply_comment_id=None,
        )

    def is_comment_seen(self, comment_id: str) -> bool:
        """Check if a comment has already been ingested."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM comment_ledger WHERE comment_id = ?",
                (comment_id,),
            ).fetchone()
        return row is not None

    def mark_enqueued(self, comment_id: str) -> None:
        """Comment has been handed to the gateway queue for processing."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE comment_ledger SET status = ?, enqueued_at = ? WHERE comment_id = ?",
                (CommentStatus.ENQUEUED, now, comment_id),
            )
            self._conn.commit()

    def mark_replied(self, comment_id: str, reply_comment_id: str = "") -> None:
        """System posted a response to this comment. Loop closed."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                """UPDATE comment_ledger SET status = ?, replied_at = ?, reply_comment_id = ?
                   WHERE comment_id = ?""",
                (CommentStatus.REPLIED, now, reply_comment_id, comment_id),
            )
            self._conn.commit()

    def unreplied_comments(self, discussion_number: int | None = None) -> list[CommentEntry]:
        """Comments that haven't been replied to yet (seen or enqueued, not self).

        If discussion_number is given, filter to that thread.
        """
        with self._lock:
            if discussion_number is not None:
                rows = self._conn.execute(
                    """SELECT * FROM comment_ledger
                       WHERE status IN (?, ?) AND source != 'self'
                         AND discussion_number = ?
                       ORDER BY seen_at ASC""",
                    (CommentStatus.SEEN, CommentStatus.ENQUEUED, discussion_number),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT * FROM comment_ledger
                       WHERE status IN (?, ?) AND source != 'self'
                       ORDER BY seen_at ASC""",
                    (CommentStatus.SEEN, CommentStatus.ENQUEUED),
                ).fetchall()
        return [self._row_to_comment(r) for r in rows]

    def recent_own_posts(self, limit: int = 10) -> list[CommentEntry]:
        """10F: Recent bot-authored comments for Brain self-awareness.

        Returns up to `limit` most recent self-posted comments,
        ordered newest first. The Brain digests these to evaluate
        its own output quality.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM comment_ledger
                   WHERE source = 'self'
                   ORDER BY seen_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row_to_comment(r) for r in rows]

    def comment_stats(self) -> dict:
        """Ledger summary for diagnostics."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, source, COUNT(*) as cnt FROM comment_ledger GROUP BY status, source",
            ).fetchall()
        result: dict = {}
        for r in rows:
            key = f"{r['source']}:{r['status']}"
            result[key] = r["cnt"]
        result["total"] = sum(result.values())
        return result

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> ThreadSnapshot:
        return ThreadSnapshot(
            discussion_number=row["discussion_number"],
            title=row["title"],
            category=row["category"],
            energy=row["energy"],
            status=row["status"],
            last_human_comment_at=row["last_human_comment_at"],
            last_agent_response_at=row["last_agent_response_at"],
            human_comment_count=row["human_comment_count"],
            response_count=row["response_count"],
            unresolved=bool(row["unresolved"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_comment(row: sqlite3.Row) -> CommentEntry:
        # 10F: body_text may not exist in older DBs — graceful fallback
        try:
            body_text = row["body_text"]
        except (IndexError, KeyError):
            body_text = None
        return CommentEntry(
            comment_id=row["comment_id"],
            discussion_number=row["discussion_number"],
            author=row["author"],
            body_hash=row["body_hash"],
            source=row["source"],
            status=row["status"],
            seen_at=row["seen_at"],
            enqueued_at=row["enqueued_at"],
            replied_at=row["replied_at"],
            reply_comment_id=row["reply_comment_id"],
            body_text=body_text,
        )

    # ── TTL Cleanup (6C-6) ──────────────────────────────────────────────

    # Default: purge archived threads after 7 days, replied comments after 3 days
    _THREAD_TTL_S: float = 7 * 24 * 3600
    _COMMENT_TTL_S: float = 3 * 24 * 3600

    def purge_stale(
        self,
        thread_ttl_s: float | None = None,
        comment_ttl_s: float | None = None,
    ) -> dict:
        """Remove archived threads and old completed comments from the DB.

        Returns: {"threads_purged": N, "comments_purged": N}
        """
        now = time.time()
        t_ttl = thread_ttl_s if thread_ttl_s is not None else self._THREAD_TTL_S
        c_ttl = comment_ttl_s if comment_ttl_s is not None else self._COMMENT_TTL_S
        thread_cutoff = now - t_ttl
        comment_cutoff = now - c_ttl

        stats = {"threads_purged": 0, "comments_purged": 0}

        with self._lock:
            # Purge archived threads whose last activity is older than TTL
            cur = self._conn.execute(
                """DELETE FROM thread_state
                   WHERE status = ? AND last_human_comment_at < ?
                     AND last_agent_response_at < ?""",
                (ThreadStatus.ARCHIVED, thread_cutoff, thread_cutoff),
            )
            stats["threads_purged"] = cur.rowcount

            # Purge completed (replied/self) comments older than TTL
            cur = self._conn.execute(
                """DELETE FROM comment_ledger
                   WHERE status IN (?, ?) AND seen_at < ?""",
                (CommentStatus.REPLIED, CommentStatus.SELF, comment_cutoff),
            )
            stats["comments_purged"] = cur.rowcount

            self._conn.commit()

        if stats["threads_purged"] or stats["comments_purged"]:
            logger.info(
                "TTL CLEANUP: purged %d archived threads, %d old comments",
                stats["threads_purged"], stats["comments_purged"],
            )
        return stats

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
