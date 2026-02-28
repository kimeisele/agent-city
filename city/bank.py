"""
AGENT CITY BANK — Double-Entry Bookkeeping with SHA-256 Chain
==============================================================

Based on steward-protocol's BankTool (vibe_core/cartridges/system/civic/tools/bank_tool.py).
Standalone SQLite, no kernel dependency.

Every transaction is chained via SHA-256 hashes — immutable ledger.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class CityBank:
    """The Central Bank of Agent City."""

    def __init__(self, db_path: str = "data/economy.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                agent_id TEXT PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                is_frozen INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                timestamp TEXT,
                sender_id TEXT,
                receiver_id TEXT,
                amount INTEGER,
                reason TEXT,
                previous_hash TEXT,
                tx_hash TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id TEXT REFERENCES transactions(tx_id),
                agent_id TEXT,
                side TEXT CHECK(side IN ('DEBIT', 'CREDIT')),
                amount INTEGER
            )
        """)
        # Genesis accounts
        now = datetime.now(timezone.utc).isoformat()
        for agent_id, balance in [("MINT", 1_000_000_000), ("VAULT", 0), ("CIVIC", 0)]:
            cur.execute(
                "INSERT OR IGNORE INTO accounts (agent_id, balance, created_at) VALUES (?, ?, ?)",
                (agent_id, balance, now),
            )
        self._conn.commit()

    def get_balance(self, agent_id: str) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT balance FROM accounts WHERE agent_id = ?", (agent_id,))
        row = cur.fetchone()
        return row["balance"] if row else 0

    def account_exists(self, agent_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM accounts WHERE agent_id = ?", (agent_id,))
        return cur.fetchone() is not None

    def create_account(self, agent_id: str, initial_balance: int = 0) -> None:
        """Create a new account. Idempotent."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO accounts (agent_id, balance, created_at) VALUES (?, ?, ?)",
            (agent_id, initial_balance, now),
        )
        self._conn.commit()

    def transfer(self, sender: str, receiver: str, amount: int, reason: str) -> str:
        """Atomic double-entry transfer with SHA-256 chain."""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        now = datetime.now(timezone.utc).isoformat()

        with self._conn:
            cur = self._conn.cursor()

            # Check funds (MINT has infinite)
            if sender != "MINT":
                balance = self.get_balance(sender)
                if balance < amount:
                    raise ValueError(f"{sender} has {balance}, needs {amount}")

            # Chain hash
            prev_hash = self._last_hash()
            raw = f"{now}{sender}{receiver}{amount}{reason}{prev_hash}"
            tx_hash = hashlib.sha256(raw.encode()).hexdigest()
            tx_id = f"TX-{tx_hash[:12]}"

            # Transaction record
            cur.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tx_id, now, sender, receiver, amount, reason, prev_hash, tx_hash),
            )

            # Double-entry
            cur.execute(
                "INSERT INTO entries (tx_id, agent_id, side, amount) VALUES (?, ?, 'DEBIT', ?)",
                (tx_id, sender, amount),
            )
            cur.execute(
                "INSERT INTO entries (tx_id, agent_id, side, amount) VALUES (?, ?, 'CREDIT', ?)",
                (tx_id, receiver, amount),
            )

            # Update balances
            if sender != "MINT":
                cur.execute(
                    "UPDATE accounts SET balance = balance - ?, updated_at = ? WHERE agent_id = ?",
                    (amount, now, sender),
                )
            self.create_account(receiver)
            cur.execute(
                "UPDATE accounts SET balance = balance + ?, updated_at = ? WHERE agent_id = ?",
                (amount, now, receiver),
            )

            self._conn.commit()
            return tx_id

    def mint(self, receiver: str, amount: int, reason: str = "genesis_grant") -> str:
        """Mint new credits for an agent."""
        return self.transfer("MINT", receiver, amount, reason)

    def freeze(self, agent_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("UPDATE accounts SET is_frozen = 1 WHERE agent_id = ?", (agent_id,))
        self._conn.commit()

    def unfreeze(self, agent_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("UPDATE accounts SET is_frozen = 0 WHERE agent_id = ?", (agent_id,))
        self._conn.commit()

    def get_statement(self, agent_id: str, limit: int = 20) -> list[dict]:
        cur = self._conn.cursor()
        cur.execute(
            """SELECT t.tx_id, t.timestamp, t.sender_id, t.receiver_id,
                      t.amount, t.reason
               FROM transactions t
               WHERE t.sender_id = ? OR t.receiver_id = ?
               ORDER BY t.timestamp DESC LIMIT ?""",
            (agent_id, agent_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def verify_integrity(self) -> bool:
        """Verify the entire transaction chain is untampered."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM transactions ORDER BY rowid")
        rows = cur.fetchall()
        prev_hash = "GENESIS"
        for row in rows:
            raw = f"{row['timestamp']}{row['sender_id']}{row['receiver_id']}{row['amount']}{row['reason']}{prev_hash}"
            expected = hashlib.sha256(raw.encode()).hexdigest()
            if row["tx_hash"] != expected:
                return False
            prev_hash = row["tx_hash"]
        return True

    def _last_hash(self) -> str:
        cur = self._conn.cursor()
        cur.execute("SELECT tx_hash FROM transactions ORDER BY rowid DESC LIMIT 1")
        row = cur.fetchone()
        return row["tx_hash"] if row else "GENESIS"
