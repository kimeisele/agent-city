"""
PranaEngine — In-Memory Prana State for O(1) Hot Path.
========================================================

Stufe 2: Replaces per-agent SQL queries with contiguous memory arrays.
SQL is cold storage. Memory is the hot path.

Architecture:
  - boot(): SQL → memory (one SELECT)
  - get(name) → int: O(1) dict lookup (no SQL)
  - metabolize_batch(active_agents) → list[str]: O(n) memory-only, no SQL
  - flush(): dirty memory → SQL batch UPDATE (one statement per heartbeat)
  - shutdown(): flush + cleanup

The arrays use plain Python dict[str, int] for prana and cycle.
At current scale (<1000 agents), dict is faster than ctypes bytearray
due to name→index mapping overhead. Switch to bytearray at 10k+ agents.

Crash safety: SQL = truth. Memory = cache. Max loss = 1 heartbeat (3 prana).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger("AGENT_CITY.PRANA_ENGINE")


@dataclass
class PranaEngine:
    """In-memory prana state with SQL batch flush.

    Hot path: get(), metabolize_batch() — pure memory, no SQL.
    Cold path: boot(), flush(), shutdown() — SQL I/O.
    """

    # In-memory state
    _prana: dict[str, int] = field(default_factory=dict)
    _cycle: dict[str, int] = field(default_factory=dict)
    _class: dict[str, str] = field(default_factory=dict)
    _active_status: dict[str, bool] = field(default_factory=dict)  # is cell_active

    # Dirty tracking for flush
    _dirty: set[str] = field(default_factory=set)

    # Agent class configs (from city.yaml)
    _class_configs: dict[str, dict] = field(default_factory=dict)

    # Lock for thread safety
    _lock: Lock = field(default_factory=Lock)

    # Stats
    _metabolize_count: int = 0
    _flush_count: int = 0
    _booted: bool = False

    @property
    def booted(self) -> bool:
        """True if engine has been loaded from SQL."""
        return self._booted

    def boot(self, conn, agent_classes: dict | None = None) -> int:
        """Load all living agents from SQL into memory.

        Called once at startup. Returns number of agents loaded.
        """
        if agent_classes:
            self._class_configs = agent_classes

        with self._lock:
            cur = conn.cursor()
            cur.execute(
                "SELECT name, prana, cell_cycle, cell_active, prana_class "
                "FROM agents WHERE status IN ('citizen', 'active')"
            )
            rows = cur.fetchall()

            self._prana.clear()
            self._cycle.clear()
            self._class.clear()
            self._active_status.clear()
            self._dirty.clear()

            for row in rows:
                name = row["name"]
                self._prana[name] = row["prana"]
                self._cycle[name] = row["cell_cycle"]
                self._class[name] = row["prana_class"] or "standard"
                self._active_status[name] = bool(row["cell_active"])

            self._booted = True
            logger.info("PranaEngine: booted %d agents into memory", len(rows))
            return len(rows)

    def get(self, name: str) -> int:
        """O(1) prana lookup from memory. Returns 0 if not found."""
        return self._prana.get(name, 0)

    def get_cycle(self, name: str) -> int:
        """O(1) cycle lookup from memory. Returns 0 if not found."""
        return self._cycle.get(name, 0)

    def has(self, name: str) -> bool:
        """Check if agent is in the engine."""
        return name in self._prana

    def credit(self, name: str, amount: int) -> int:
        """Add prana to an agent. Returns new balance."""
        with self._lock:
            if name not in self._prana:
                return 0
            self._prana[name] += amount
            self._dirty.add(name)
            return self._prana[name]

    def debit(self, name: str, amount: int) -> bool:
        """Debit prana. Returns False if insufficient balance."""
        with self._lock:
            if name not in self._prana:
                return False
            if self._prana[name] < amount:
                return False
            self._prana[name] -= amount
            self._dirty.add(name)
            return True

    def register_agent(self, name: str, prana: int, cycle: int = 0,
                       prana_class: str = "standard") -> None:
        """Add a new agent to the engine (on spawn/promote)."""
        with self._lock:
            self._prana[name] = prana
            self._cycle[name] = cycle
            self._class[name] = prana_class
            self._active_status[name] = True

    def remove_agent(self, name: str) -> None:
        """Remove agent from engine (on freeze/archive/exile)."""
        with self._lock:
            self._prana.pop(name, None)
            self._cycle.pop(name, None)
            self._class.pop(name, None)
            self._active_status.pop(name, None)
            self._dirty.discard(name)

    def metabolize_batch(
        self,
        active_agents: set[str] | None = None,
        domain_costs: dict[str, int] | None = None,
    ) -> list[str]:
        """Run one metabolic cycle on all agents in memory.

        Pure memory operations — no SQL. Returns list of dormant agent names
        (prana exhausted or age exceeded).

        Steps:
          1. Deduct metabolic cost (domain-differentiated if domain_costs given)
          2. Increment cycle counter
          3. Detect dormant: prana <= 0 or age exceeded
          4. Mark ALL touched agents as dirty

        No free active bonus. Agents earn prana through work (KARMA phase rewards).
        Dharma differentiates: engineering costs more than research. Svadharma.
        """
        active_agents = active_agents or set()
        domain_costs = domain_costs or {}
        dormant: list[str] = []
        default_cost = self._class_configs.get("standard", {}).get("metabolic_cost", 3)
        default_max_age = self._class_configs.get("standard", {}).get("max_age", 432)

        with self._lock:
            for name in list(self._prana.keys()):
                pc = self._class.get(name, "standard")
                cls_cfg = self._class_configs.get(pc, {})
                base_cost = cls_cfg.get("metabolic_cost", default_cost)
                max_age = cls_cfg.get("max_age", default_max_age)

                # Domain-differentiated cost (Svadharma metabolism)
                cost = domain_costs.get(name, base_cost)

                # Deduct metabolic cost
                if cost > 0:
                    self._prana[name] -= cost

                # Increment cycle
                self._cycle[name] += 1

                # Mark dirty
                self._dirty.add(name)

                # Check dormancy
                if self._prana[name] <= 0:
                    dormant.append(name)
                elif max_age >= 0 and self._cycle[name] >= max_age:
                    dormant.append(name)

            self._metabolize_count += 1

        return dormant

    def flush(self, conn) -> int:
        """Batch flush dirty agents to SQL. Returns count flushed.

        Single SQL statement per flush using CASE-WHEN batch update.
        Called once per heartbeat after metabolize_batch().
        """
        with self._lock:
            dirty_names = list(self._dirty)
            if not dirty_names:
                return 0

            cur = conn.cursor()

            # Batch update using executemany (one roundtrip)
            cur.executemany(
                "UPDATE agents SET prana = ?, cell_cycle = ? WHERE name = ?",
                [(self._prana[n], self._cycle[n], n)
                 for n in dirty_names if n in self._prana],
            )
            conn.commit()

            flushed = len(dirty_names)
            self._dirty.clear()
            self._flush_count += 1

            logger.debug(
                "PranaEngine: flushed %d agents to SQL (flush #%d)",
                flushed, self._flush_count,
            )
            return flushed

    def shutdown(self, conn) -> None:
        """Flush all dirty state and cleanup."""
        self.flush(conn)
        logger.info("PranaEngine: shutdown complete")

    def stats(self) -> dict:
        """Engine statistics for reflection."""
        return {
            "agents_in_memory": len(self._prana),
            "dirty_count": len(self._dirty),
            "metabolize_cycles": self._metabolize_count,
            "flush_count": self._flush_count,
            "booted": self._booted,
        }
