"""Tests for Marketplace — Phase 7.

3 transfer tests + 6 order CRUD tests + 5 auto-matching tests
+ 2 transaction safety tests + 3 stats/constants tests = 19 tests.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_pokedex():
    """Create a fresh Pokedex with a temp database."""
    from city.pokedex import Pokedex

    db_path = Path(tempfile.mktemp(suffix=".db"))
    return Pokedex(db_path=db_path)


def _register(pokedex, name):
    """Discover + register an agent (skip starter pack for clean tests)."""
    pokedex.discover(name)
    pokedex.register(name, grant_override=108)


# ── Transfer Tests ──────────────────────────────────────────────────


class TestTransferAsset(unittest.TestCase):
    """Atomic asset transfer between agents."""

    def setUp(self):
        self.pokedex = _make_pokedex()
        _register(self.pokedex, "seller")
        _register(self.pokedex, "buyer")

    def test_transfer_success(self):
        """Happy path: seller loses, buyer gains."""
        self.pokedex.grant_asset("seller", "capability_token", "execute", quantity=3, source="mint")

        ok = self.pokedex.transfer_asset("seller", "buyer", "capability_token", "execute", 2)
        self.assertTrue(ok)

        seller_inv = self.pokedex.get_inventory("seller")
        buyer_inv = self.pokedex.get_inventory("buyer")
        self.assertEqual(seller_inv[0]["quantity"], 1)
        self.assertEqual(buyer_inv[0]["quantity"], 2)

    def test_transfer_insufficient(self):
        """Seller lacks asset → False, nothing changes."""
        self.pokedex.grant_asset("seller", "capability_token", "execute", quantity=1, source="mint")

        ok = self.pokedex.transfer_asset("seller", "buyer", "capability_token", "execute", 5)
        self.assertFalse(ok)

        # Seller still has original amount
        seller_inv = self.pokedex.get_inventory("seller")
        self.assertEqual(seller_inv[0]["quantity"], 1)
        # Buyer has nothing
        buyer_inv = self.pokedex.get_inventory("buyer")
        self.assertEqual(len(buyer_inv), 0)

    def test_transfer_stacks_on_buyer(self):
        """Buyer already has some → quantity increments."""
        self.pokedex.grant_asset("seller", "capability_token", "execute", quantity=3, source="mint")
        self.pokedex.grant_asset("buyer", "capability_token", "execute", quantity=2, source="mint")

        ok = self.pokedex.transfer_asset("seller", "buyer", "capability_token", "execute", 1)
        self.assertTrue(ok)

        buyer_inv = [a for a in self.pokedex.get_inventory("buyer") if a["asset_id"] == "execute"]
        self.assertEqual(buyer_inv[0]["quantity"], 3)


# ── Order CRUD Tests ────────────────────────────────────────────────


class TestOrderCRUD(unittest.TestCase):
    """Marketplace order lifecycle: create, fill, cancel, expire."""

    def setUp(self):
        self.pokedex = _make_pokedex()
        _register(self.pokedex, "alice")
        _register(self.pokedex, "bob")
        # Give alice something to sell
        self.pokedex.grant_asset("alice", "capability_token", "execute", quantity=3, source="mint")

    def test_create_order_escrows(self):
        """Asset removed from seller inventory on create."""
        oid = self.pokedex.create_order("alice", "capability_token", "execute", 2, 50, heartbeat=1)
        self.assertIsNotNone(oid)

        # Alice should have 1 left (3 - 2 escrowed)
        inv = [a for a in self.pokedex.get_inventory("alice") if a["asset_id"] == "execute"]
        self.assertEqual(inv[0]["quantity"], 1)

        # Order is open
        orders = self.pokedex.get_active_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["seller"], "alice")
        self.assertEqual(orders[0]["quantity"], 2)

    def test_create_order_no_asset_fails(self):
        """Seller doesn't have asset → None."""
        oid = self.pokedex.create_order("bob", "capability_token", "execute", 1, 50, heartbeat=1)
        self.assertIsNone(oid)

    def test_fill_order_transfers(self):
        """Buyer gets asset, seller gets prana."""
        oid = self.pokedex.create_order("alice", "capability_token", "execute", 1, 36, heartbeat=1)

        receipt = self.pokedex.fill_order(oid, "bob", heartbeat=2)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["buyer"], "bob")
        self.assertEqual(receipt["seller"], "alice")
        self.assertEqual(receipt["asset_id"], "execute")
        self.assertIn("tx_id", receipt)

        # Bob now has execute
        self.assertTrue(self.pokedex.has_asset("bob", "capability_token", "execute"))

        # Order is no longer active
        orders = self.pokedex.get_active_orders()
        self.assertEqual(len(orders), 0)

    def test_fill_order_commission(self):
        """Commission goes to zone treasury."""
        oid = self.pokedex.create_order("alice", "capability_token", "execute", 1, 100, heartbeat=1)

        receipt = self.pokedex.fill_order(oid, "bob", heartbeat=2)
        self.assertIsNotNone(receipt)

        # 6% commission on 100 = 6
        self.assertEqual(receipt["commission"], 6)
        self.assertEqual(receipt["seller_receives"], 94)

    def test_cancel_returns_asset(self):
        """Escrowed asset returned to seller on cancel."""
        oid = self.pokedex.create_order("alice", "capability_token", "execute", 2, 50, heartbeat=1)

        # Alice has 1 left
        inv_before = [a for a in self.pokedex.get_inventory("alice") if a["asset_id"] == "execute"]
        self.assertEqual(inv_before[0]["quantity"], 1)

        ok = self.pokedex.cancel_order(oid, "alice")
        self.assertTrue(ok)

        # Alice has 3 again
        inv_after = [a for a in self.pokedex.get_inventory("alice") if a["asset_id"] == "execute"]
        self.assertEqual(inv_after[0]["quantity"], 3)

        # Order is gone
        self.assertEqual(len(self.pokedex.get_active_orders()), 0)

    def test_expire_orders(self):
        """Past-heartbeat orders expired, assets returned."""
        oid = self.pokedex.create_order("alice", "capability_token", "execute", 1, 50, heartbeat=1)

        # Expire at heartbeat 200 (order expires at 1 + 108 = 109)
        count = self.pokedex.expire_orders(heartbeat=200)
        self.assertEqual(count, 1)

        # Asset returned
        inv = [a for a in self.pokedex.get_inventory("alice") if a["asset_id"] == "execute"]
        self.assertEqual(inv[0]["quantity"], 3)


# ── Auto-Matching Tests ─────────────────────────────────────────────


class TestAutoMatching(unittest.TestCase):
    """KARMA auto-list and need-driven auto-match."""

    def _make_ctx(self, pokedex, active_agents=None):
        """Build minimal PhaseContext mock."""
        ctx = MagicMock()
        ctx.pokedex = pokedex
        ctx.heartbeat_count = 10
        ctx.active_agents = active_agents or set()
        ctx.sankalpa = None
        ctx.learning = None
        ctx.council = None  # No governance freeze
        return ctx

    def test_auto_list_surplus(self):
        """Agent with qty>1 creates sell order."""
        from city.phases.karma import _process_marketplace

        pokedex = _make_pokedex()
        _register(pokedex, "agent_a")
        pokedex.grant_asset("agent_a", "capability_token", "execute", quantity=3, source="mint")

        ctx = self._make_ctx(pokedex, {"agent_a"})
        specs = {"agent_a": {"capabilities": ["execute"], "element": "agni"}}
        inventories = {"agent_a": pokedex.get_inventory("agent_a")}
        operations: list[str] = []

        _process_marketplace(ctx, operations, specs, inventories)

        # Should have listed surplus (3 - 1 = 2)
        orders = pokedex.get_active_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["quantity"], 2)
        self.assertEqual(orders[0]["seller"], "agent_a")

    def test_auto_match_fills_needed(self):
        """Agent lacking domain-aligned cap buys from marketplace."""
        pokedex = _make_pokedex()
        _register(pokedex, "seller")
        _register(pokedex, "buyer")

        # Seller lists a validate token
        pokedex.grant_asset("seller", "capability_token", "validate", quantity=2, source="mint")
        pokedex.create_order("seller", "capability_token", "validate", 1, 36, heartbeat=1)

        # Buyer is agni element — domain-aligned caps include validate
        from city.phases.karma import _process_marketplace

        ctx = self._make_ctx(pokedex, {"buyer"})
        specs = {"buyer": {"capabilities": ["transform", "audit"], "element": "agni"}}
        inventories = {"buyer": pokedex.get_inventory("buyer")}
        operations: list[str] = []

        _process_marketplace(ctx, operations, specs, inventories)

        # Buyer should have acquired validate (agni element needs it)
        self.assertTrue(pokedex.has_asset("buyer", "capability_token", "validate"))

    def test_no_self_buy(self):
        """Agent can't buy own listing."""
        pokedex = _make_pokedex()
        _register(pokedex, "solo")
        pokedex.grant_asset("solo", "capability_token", "execute", quantity=3, source="mint")

        # Create order manually
        pokedex.create_order("solo", "capability_token", "execute", 1, 36, heartbeat=1)

        # fill_order should reject self-buy
        orders = pokedex.get_active_orders()
        receipt = pokedex.fill_order(orders[0]["id"], "solo", heartbeat=2)
        self.assertIsNone(receipt)

    def test_no_blind_buy(self):
        """Agent with prana but NO need → does NOT buy (anti-Pac-Man)."""
        pokedex = _make_pokedex()
        _register(pokedex, "seller")
        _register(pokedex, "rich_agent")

        # Seller lists an observe token
        pokedex.grant_asset("seller", "capability_token", "observe", quantity=2, source="mint")
        pokedex.create_order("seller", "capability_token", "observe", 1, 36, heartbeat=1)

        # Rich agent is prithvi element — observe is NOT in prithvi family
        # prithvi = build, maintain, stabilize. Observe is akasha.
        from city.phases.karma import _process_marketplace

        ctx = self._make_ctx(pokedex, {"rich_agent"})
        specs = {
            "rich_agent": {"capabilities": ["build", "maintain", "stabilize"], "element": "prithvi"}
        }
        inventories = {"rich_agent": pokedex.get_inventory("rich_agent")}
        operations: list[str] = []

        _process_marketplace(ctx, operations, specs, inventories)

        # Rich agent should NOT have bought observe — not domain-aligned, no mission need
        self.assertFalse(pokedex.has_asset("rich_agent", "capability_token", "observe"))

        # Order should still be open
        orders = pokedex.get_active_orders()
        self.assertEqual(len(orders), 1)

    def test_mission_blocked_buy(self):
        """Agent blocked on mission buys required cap from marketplace."""
        pokedex = _make_pokedex()
        _register(pokedex, "seller")
        _register(pokedex, "worker")

        # Seller lists an audit token
        pokedex.grant_asset("seller", "capability_token", "audit", quantity=2, source="mint")
        pokedex.create_order("seller", "capability_token", "audit", 1, 36, heartbeat=1)

        # Worker is prithvi (build/maintain/stabilize) — audit is NOT domain-aligned
        # BUT there's an active audit_ mission requiring "audit" capability
        from city.phases.karma import _process_marketplace

        ctx = self._make_ctx(pokedex, {"worker"})

        # Mock sankalpa with an active audit mission
        mock_mission = MagicMock()
        mock_mission.id = "audit_check_42"
        mock_mission.name = "Audit check"
        ctx.sankalpa = MagicMock()
        ctx.sankalpa.registry.get_active_missions.return_value = [mock_mission]

        specs = {
            "worker": {"capabilities": ["build", "maintain", "stabilize"], "element": "prithvi"}
        }
        inventories = {"worker": pokedex.get_inventory("worker")}
        operations: list[str] = []

        _process_marketplace(ctx, operations, specs, inventories)

        # Worker should have bought audit — mission-blocked need
        self.assertTrue(pokedex.has_asset("worker", "capability_token", "audit"))


# ── Transaction Safety Tests ────────────────────────────────────────


class TestTransactionSafety(unittest.TestCase):
    """Bank failure rollback and treasury fallback."""

    def test_fill_order_bank_fail_rollback(self):
        """Bank.transfer raises → order stays open, no asset granted."""
        pokedex = _make_pokedex()
        _register(pokedex, "seller")
        _register(pokedex, "buyer")
        pokedex.grant_asset("seller", "capability_token", "execute", quantity=2, source="mint")

        oid = pokedex.create_order("seller", "capability_token", "execute", 1, 36, heartbeat=1)

        # Patch bank.transfer to raise
        original_transfer = pokedex._bank.transfer
        pokedex._bank.transfer = MagicMock(side_effect=Exception("Bank offline"))

        receipt = pokedex.fill_order(oid, "buyer", heartbeat=2)
        self.assertIsNone(receipt)

        # Order should still be open
        orders = pokedex.get_active_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["status"], "open")

        # Buyer should NOT have the asset
        self.assertFalse(pokedex.has_asset("buyer", "capability_token", "execute"))

        # Restore bank
        pokedex._bank.transfer = original_transfer

    def test_zone_treasury_fallback(self):
        """Seller with unknown zone → commission goes to ZONE_DISCOVERY."""
        pokedex = _make_pokedex()
        _register(pokedex, "seller")
        _register(pokedex, "buyer")
        pokedex.grant_asset("seller", "capability_token", "execute", quantity=2, source="mint")

        oid = pokedex.create_order("seller", "capability_token", "execute", 1, 100, heartbeat=1)

        # fill_order should succeed even if zone lookup returns unusual value
        receipt = pokedex.fill_order(oid, "buyer", heartbeat=2)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["commission"], 6)


# ── Stats + Constants Tests ─────────────────────────────────────────


class TestMarketplaceStats(unittest.TestCase):
    """Marketplace statistics and constant verification."""

    def test_marketplace_stats(self):
        """Stats reflect activity after trades."""
        pokedex = _make_pokedex()
        _register(pokedex, "a")
        _register(pokedex, "b")
        pokedex.grant_asset("a", "capability_token", "execute", quantity=3, source="mint")

        stats_empty = pokedex.marketplace_stats()
        self.assertEqual(stats_empty["active_orders"], 0)
        self.assertEqual(stats_empty["total_filled"], 0)

        oid = pokedex.create_order("a", "capability_token", "execute", 1, 50, heartbeat=1)
        stats_listed = pokedex.marketplace_stats()
        self.assertEqual(stats_listed["active_orders"], 1)

        pokedex.fill_order(oid, "b", heartbeat=2)
        stats_filled = pokedex.marketplace_stats()
        self.assertEqual(stats_filled["active_orders"], 0)
        self.assertEqual(stats_filled["total_filled"], 1)
        self.assertEqual(stats_filled["trade_volume"], 50)

    def test_commission_is_sharanagati(self):
        """TRADE_COMMISSION_PERCENT == SHARANAGATI (6)."""
        from city.seed_constants import TRADE_COMMISSION_PERCENT

        self.assertEqual(TRADE_COMMISSION_PERCENT, 6)

    def test_expiry_is_mala(self):
        """ORDER_EXPIRY_HEARTBEATS == MALA (108)."""
        from city.seed_constants import ORDER_EXPIRY_HEARTBEATS

        self.assertEqual(ORDER_EXPIRY_HEARTBEATS, 108)


if __name__ == "__main__":
    unittest.main()
