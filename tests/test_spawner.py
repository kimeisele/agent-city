"""Tests for Agent Spawner lifecycle engine."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAgentSpawner(unittest.TestCase):
    """Test AgentSpawner lifecycle orchestration."""

    def _make_spawner(self, *, discovered=None, citizens=None, cartridge_names=None):
        """Build a spawner with mocked pokedex/network/loader."""
        from city.spawner import AgentSpawner

        pokedex = MagicMock()
        network = MagicMock()
        network._registered_agents = set()
        loader = MagicMock()

        # Configure pokedex.list_by_status("discovered")
        pokedex.list_by_status.return_value = discovered or []

        # Configure pokedex.list_citizens()
        pokedex.list_citizens.return_value = citizens or []

        # Configure pokedex.get() — return None for new agents
        pokedex.get.return_value = None

        # Configure pokedex.register() — no-op
        pokedex.register.return_value = {"status": "citizen"}

        # Configure pokedex.get_cell() — return alive cell
        mock_cell = MagicMock()
        mock_cell.is_alive = True
        mock_cell.prana = 13700
        pokedex.get_cell.return_value = mock_cell

        # Configure network.register_agent()
        network.register_agent.return_value = 12345

        # Configure loader
        loader.list_available.return_value = cartridge_names or []

        spawner = AgentSpawner(
            _pokedex=pokedex,
            _network=network,
            _cartridge_loader=loader,
        )
        return spawner, pokedex, network, loader

    def test_spawn_system_agents(self):
        """System agents created from cartridge names."""
        spawner, pokedex, network, _ = self._make_spawner(
            cartridge_names=["civic", "chronicle", "discoverer"]
        )

        result = spawner.spawn_system_agents()

        self.assertEqual(len(result), 3)
        self.assertIn("sys_civic", result)
        self.assertIn("sys_chronicle", result)
        self.assertIn("sys_discoverer", result)

        # Pokedex.register() called for each
        self.assertEqual(pokedex.register.call_count, 3)
        pokedex.register.assert_any_call("sys_civic")
        pokedex.register.assert_any_call("sys_chronicle")

        # Network registration called
        self.assertTrue(network.register_agent.call_count >= 3)

    def test_spawn_system_agents_idempotent(self):
        """Already-citizen system agents are not re-registered."""
        spawner, pokedex, network, _ = self._make_spawner(cartridge_names=["civic"])
        # Agent already exists as citizen
        pokedex.get.return_value = {"status": "citizen", "name": "sys_civic"}

        result = spawner.spawn_system_agents()

        # Should not spawn (already citizen)
        self.assertEqual(len(result), 0)
        pokedex.register.assert_not_called()

    def test_promote_discovered(self):
        """Discovered agents promoted to citizen."""
        discovered = [
            {"name": "alice", "status": "discovered"},
            {"name": "bob", "status": "discovered"},
        ]
        spawner, pokedex, network, _ = self._make_spawner(discovered=discovered)

        result = spawner.promote_eligible(heartbeat=5)

        self.assertEqual(len(result), 2)
        self.assertIn("alice", result)
        self.assertIn("bob", result)

        pokedex.register.assert_any_call("alice")
        pokedex.register.assert_any_call("bob")
        self.assertEqual(network.register_agent.call_count, 2)
        self.assertEqual(spawner._promoted_total, 2)

    def test_network_registration(self):
        """Promoted agents registered in CityNetwork."""
        discovered = [{"name": "carol", "status": "discovered"}]
        spawner, pokedex, network, _ = self._make_spawner(discovered=discovered)

        spawner.promote_eligible(heartbeat=10)

        network.register_agent.assert_called_once()
        call_args = network.register_agent.call_args
        self.assertEqual(call_args[0][0], "carol")  # name
        self.assertTrue(call_args[0][1].is_alive)  # cell.is_alive

    def test_mark_citizens_active(self):
        """Living citizens added to active_set."""
        citizens = [
            {"name": "alice"},
            {"name": "bob"},
            {"name": "carol"},
        ]
        spawner, pokedex, _, _ = self._make_spawner(citizens=citizens)

        active_set: set[str] = set()
        count = spawner.mark_citizens_active(active_set)

        self.assertEqual(count, 3)
        self.assertEqual(active_set, {"alice", "bob", "carol"})

    def test_dead_agents_not_marked_active(self):
        """Dead agents excluded from active_set."""
        citizens = [
            {"name": "alice"},
            {"name": "dead_bob"},
        ]
        spawner, pokedex, _, _ = self._make_spawner(citizens=citizens)

        # Make dead_bob's cell dead
        alive_cell = MagicMock()
        alive_cell.is_alive = True
        dead_cell = MagicMock()
        dead_cell.is_alive = False

        def get_cell_side_effect(name):
            if name == "dead_bob":
                return dead_cell
            return alive_cell

        pokedex.get_cell.side_effect = get_cell_side_effect

        active_set: set[str] = set()
        count = spawner.mark_citizens_active(active_set)

        self.assertEqual(count, 1)
        self.assertIn("alice", active_set)
        self.assertNotIn("dead_bob", active_set)

    def test_cartridge_binding(self):
        """System agents bound to matching cartridge."""
        spawner, _, _, _ = self._make_spawner(cartridge_names=["civic"])

        spawner.spawn_system_agents()

        self.assertEqual(spawner.get_cartridge("sys_civic"), "civic")
        self.assertIsNone(spawner.get_cartridge("unknown_agent"))

    def test_stats(self):
        """Stats report correct counts."""
        spawner, _, _, _ = self._make_spawner(cartridge_names=["civic", "chronicle"])

        spawner.spawn_system_agents()
        stats = spawner.stats()

        self.assertEqual(stats["system_agents"], 2)
        self.assertEqual(stats["cartridge_bindings"], 2)

    def test_materialize_existing_uses_internal_membrane_for_claim_migration(self):
        """Boot-time claim migration must carry explicit internal authority."""
        from city.membrane import internal_membrane_snapshot

        citizens = [{"name": "alice"}]
        spawner, pokedex, _, _ = self._make_spawner(citizens=citizens)
        pokedex.get_claim_level.return_value = 0

        count = spawner.materialize_existing()

        self.assertEqual(count, 1)
        pokedex.update_claim_level.assert_called_once_with(
            "alice",
            1,
            membrane=internal_membrane_snapshot(source_class="spawner"),
        )


if __name__ == "__main__":
    unittest.main()
