"""Tests for Inventory & Semantic Asset System — Phase 5.

5 inventory table tests + 4 dynamic gate tests + 3 integration tests.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_pokedex():
    """Create a fresh Pokedex with a temp database."""
    from city.pokedex import Pokedex

    db_path = Path(tempfile.mktemp(suffix=".db"))
    return Pokedex(db_path=db_path)


def _spec(
    name="alice",
    domain="ENGINEERING",
    capabilities=None,
    capability_tier="observer",
    capability_protocol="route",
    guna="RAJAS",
    guardian="prahlada",
):
    """Build a minimal AgentSpec dict for routing tests."""
    from city.guardian_spec import GUNA_QOS

    if capabilities is None:
        capabilities = ["observe", "monitor", "report"]
    return {
        "name": name,
        "domain": domain,
        "capabilities": capabilities,
        "capability_tier": capability_tier,
        "capability_protocol": capability_protocol,
        "guna": guna,
        "guardian": guardian,
        "qos": dict(GUNA_QOS.get(guna, GUNA_QOS["RAJAS"])),
    }


# ── Inventory Table Tests ────────────────────────────────────────────


class TestInventoryTable(unittest.TestCase):
    """CRUD operations on agent_inventory table."""

    def setUp(self):
        self.pokedex = _make_pokedex()
        self.pokedex.discover("test_agent")
        self.pokedex.register("test_agent", grant_override=108)  # skip starter pack

    def test_grant_asset(self):
        """grant_asset creates row, get_inventory returns it."""
        row_id = self.pokedex.grant_asset(
            "test_agent", "capability_token", "execute", source="mint"
        )
        self.assertIsNotNone(row_id)

        inv = self.pokedex.get_inventory("test_agent")
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["asset_type"], "capability_token")
        self.assertEqual(inv[0]["asset_id"], "execute")
        self.assertEqual(inv[0]["quantity"], 1)
        self.assertEqual(inv[0]["source"], "mint")

    def test_grant_stacks(self):
        """Granting same asset_type+asset_id increments quantity."""
        self.pokedex.grant_asset("test_agent", "word_token", "dharma", quantity=3, source="reward")
        self.pokedex.grant_asset("test_agent", "word_token", "dharma", quantity=2, source="reward")

        inv = self.pokedex.get_inventory("test_agent")
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["quantity"], 5)

    def test_consume_asset(self):
        """consume decrements, returns False if insufficient."""
        self.pokedex.grant_asset(
            "test_agent", "concept_token", "governance", quantity=3, source="mint"
        )

        # Consume 2
        result = self.pokedex.consume_asset("test_agent", "concept_token", "governance", quantity=2)
        self.assertTrue(result)
        inv = self.pokedex.get_inventory("test_agent")
        self.assertEqual(inv[0]["quantity"], 1)

        # Try to consume 5 (only 1 left)
        result = self.pokedex.consume_asset("test_agent", "concept_token", "governance", quantity=5)
        self.assertFalse(result)

        # Consume last 1 → row deleted
        result = self.pokedex.consume_asset("test_agent", "concept_token", "governance", quantity=1)
        self.assertTrue(result)
        inv = self.pokedex.get_inventory("test_agent")
        self.assertEqual(len(inv), 0)

    def test_expired_assets_excluded(self):
        """get_inventory excludes expired assets."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        self.pokedex.grant_asset(
            "test_agent", "capability_token", "old", source="lease", expires_at=past
        )
        self.pokedex.grant_asset(
            "test_agent", "capability_token", "fresh", source="lease", expires_at=future
        )
        self.pokedex.grant_asset("test_agent", "capability_token", "permanent", source="mint")

        inv = self.pokedex.get_inventory("test_agent")
        asset_ids = {a["asset_id"] for a in inv}
        self.assertIn("fresh", asset_ids)
        self.assertIn("permanent", asset_ids)
        self.assertNotIn("old", asset_ids)

    def test_has_asset(self):
        """has_asset returns True/False correctly."""
        self.assertFalse(self.pokedex.has_asset("test_agent", "capability_token", "execute"))

        self.pokedex.grant_asset("test_agent", "capability_token", "execute", source="mint")
        self.assertTrue(self.pokedex.has_asset("test_agent", "capability_token", "execute"))
        self.assertFalse(self.pokedex.has_asset("test_agent", "capability_token", "audit"))


# ── Dynamic Gate Tests ───────────────────────────────────────────────


class TestDynamicGate(unittest.TestCase):
    """check_capability_gate with inventory fallback."""

    def test_gate_passes_with_capability_token(self):
        """Agent missing static cap but has capability_token → PASS."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(
            capability_tier="verified",
            capabilities=["observe"],
        )
        req = get_requirement("exec_test")
        inventory = [{"asset_type": "capability_token", "asset_id": "execute"}]

        self.assertFalse(check_capability_gate(spec, req))
        self.assertTrue(check_capability_gate(spec, req, inventory=inventory))

    def test_tier_never_bypassed(self):
        """Observer with execute token but min_tier=verified → BLOCKED."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(
            capability_tier="observer",
            capabilities=["observe"],
        )
        req = get_requirement("exec_test")  # min_tier = verified
        inventory = [{"asset_type": "capability_token", "asset_id": "execute"}]

        # Has the cap via token but tier is too low — MUST be blocked
        self.assertFalse(check_capability_gate(spec, req, inventory=inventory))

    def test_gate_without_inventory(self):
        """Backward compat: no inventory param → static only."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(
            capability_tier="verified",
            capabilities=["execute", "dispatch"],
        )
        req = get_requirement("exec_test")

        # Works without inventory param (backward compatible)
        self.assertTrue(check_capability_gate(spec, req))

    def test_expired_token_doesnt_help(self):
        """Expired capability_token filtered by Pokedex, not in inventory list."""
        from city.mission_router import check_capability_gate, get_requirement

        pokedex = _make_pokedex()
        pokedex.discover("agent_x")
        pokedex.register("agent_x", grant_override=108)  # skip starter pack

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        pokedex.grant_asset(
            "agent_x", "capability_token", "execute", source="lease", expires_at=past
        )

        spec = _spec(capability_tier="verified", capabilities=["observe"])
        req = get_requirement("exec_test")

        # get_inventory filters expired → empty list → gate fails
        inv = pokedex.get_inventory("agent_x")
        self.assertEqual(len(inv), 0)
        self.assertFalse(check_capability_gate(spec, req, inventory=inv))


# ── Integration Tests ────────────────────────────────────────────────


class TestIntegration(unittest.TestCase):
    """End-to-end: inventory + routing."""

    def test_route_with_inventory(self):
        """Agent with low static caps but capability_token gets routed."""
        from city.mission_router import route_mission

        mission = MagicMock()
        mission.id = "exec_deploy_99"

        specs = {
            "weak": _spec(
                name="weak",
                capability_tier="verified",
                capabilities=["observe"],
            ),
        }
        inventories = {
            "weak": [{"asset_type": "capability_token", "asset_id": "execute"}],
        }

        # Without inventory → blocked
        result = route_mission(mission, specs, {"weak"})
        self.assertTrue(result["blocked"])

        # With inventory → routed
        result = route_mission(mission, specs, {"weak"}, inventories=inventories)
        self.assertFalse(result["blocked"])
        self.assertEqual(result["agent_name"], "weak")

    def test_inventory_in_agent_dict(self):
        """_row_to_dict includes inventory.asset_count for citizens."""
        pokedex = _make_pokedex()
        pokedex.discover("inv_test")
        pokedex.register("inv_test", grant_override=108)  # skip starter pack

        agent = pokedex.get("inv_test")
        self.assertIsNotNone(agent["inventory"])
        self.assertEqual(agent["inventory"]["asset_count"], 0)

        pokedex.grant_asset("inv_test", "word_token", "karma", source="reward")
        pokedex.grant_asset("inv_test", "concept_token", "dharma", source="mint")

        agent = pokedex.get("inv_test")
        self.assertEqual(agent["inventory"]["asset_count"], 2)

    def test_consume_on_use(self):
        """Asset consumed after mission dispatch (marketplace hook)."""
        pokedex = _make_pokedex()
        pokedex.discover("consumer")
        pokedex.register("consumer", grant_override=108)  # skip starter pack

        pokedex.grant_asset("consumer", "capability_token", "execute", quantity=1, source="trade")
        self.assertTrue(pokedex.has_asset("consumer", "capability_token", "execute"))

        # Simulate consumption after mission dispatch
        consumed = pokedex.consume_asset("consumer", "capability_token", "execute")
        self.assertTrue(consumed)

        # Now gone — gate would fail
        self.assertFalse(pokedex.has_asset("consumer", "capability_token", "execute"))


if __name__ == "__main__":
    unittest.main()
