"""Tests for GuardianSpec, CartridgeFactory, and CityBuilder."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── GuardianSpec Tests ───────────────────────────────────────────────


class TestGuardianSpec(unittest.TestCase):
    """Test the 16-guardian truth table and AgentSpec builder."""

    def test_guardian_table_complete(self):
        """GUARDIAN_TABLE has exactly 16 entries."""
        from city.guardian_spec import GUARDIAN_TABLE

        self.assertEqual(len(GUARDIAN_TABLE), 16)

    def test_quarter_heads(self):
        """Positions 0, 4, 8, 12 are quarter heads (Avataras)."""
        from city.guardian_spec import GUARDIAN_TABLE

        heads = {name: g for name, g in GUARDIAN_TABLE.items() if g["is_head"]}
        self.assertEqual(len(heads), 4)
        head_positions = {g["position"] for g in heads.values()}
        self.assertEqual(head_positions, {0, 4, 8, 12})

    def test_guna_distribution(self):
        """4 SATTVA + 9 RAJAS + 3 TAMAS = 16."""
        from city.guardian_spec import GUARDIAN_TABLE

        guna_counts: dict[str, int] = {}
        for g in GUARDIAN_TABLE.values():
            guna_counts[g["guna"]] = guna_counts.get(g["guna"], 0) + 1
        self.assertEqual(guna_counts["SATTVA"], 4)
        self.assertEqual(guna_counts["RAJAS"], 9)
        self.assertEqual(guna_counts["TAMAS"], 3)
        self.assertEqual(sum(guna_counts.values()), 16)

    def test_all_protocols_present(self):
        """All 5 capability protocols appear in the table."""
        from city.guardian_spec import GUARDIAN_TABLE

        protocols = {g["protocol"] for g in GUARDIAN_TABLE.values()}
        self.assertEqual(protocols, {"parse", "validate", "infer", "route", "enforce"})

    def test_qos_values(self):
        """SATTVA allows parallel, TAMAS requires confirmation."""
        from city.guardian_spec import GUNA_QOS

        self.assertTrue(GUNA_QOS["SATTVA"]["parallel"])
        self.assertFalse(GUNA_QOS["SATTVA"]["confirmation_required"])
        self.assertFalse(GUNA_QOS["RAJAS"]["parallel"])
        self.assertTrue(GUNA_QOS["TAMAS"]["confirmation_required"])
        self.assertEqual(GUNA_QOS["TAMAS"]["latency_multiplier"], 3.0)

    def test_claim_tiers(self):
        """4 tiers, sovereign has the most capabilities."""
        from city.guardian_spec import CLAIM_TIER, TIER_CAPABILITIES

        self.assertEqual(len(CLAIM_TIER), 4)
        self.assertEqual(CLAIM_TIER[0], "observer")
        self.assertEqual(CLAIM_TIER[3], "sovereign")
        self.assertEqual(len(TIER_CAPABILITIES["observer"]), 0)
        self.assertGreater(len(TIER_CAPABILITIES["sovereign"]), len(TIER_CAPABILITIES["verified"]))

    def test_build_agent_spec(self):
        """build_agent_spec returns valid AgentSpec from Pokedex dict."""
        from city.guardian_spec import build_agent_spec

        data = _agent_data("alice", quarter="dharma", guardian="kapila", element="jala", guna="SATTVA")
        spec = build_agent_spec("alice", data)

        self.assertEqual(spec["name"], "alice")
        self.assertEqual(spec["domain"], "GOVERNANCE")
        self.assertEqual(spec["guardian"], "kapila")
        self.assertEqual(spec["opcode"], "TYPE_CHECK")
        self.assertEqual(spec["role"], "Analysis, classification")
        self.assertEqual(spec["capability_protocol"], "infer")
        self.assertEqual(spec["guna"], "SATTVA")
        self.assertTrue(spec["qos"]["parallel"])
        self.assertEqual(spec["style"], "contemplative")
        self.assertEqual(spec["capability_tier"], "observer")

    def test_merged_capabilities(self):
        """Capabilities merge element + guardian + tier (deduplicated)."""
        from city.guardian_spec import build_agent_spec

        data = _agent_data(
            "bob", quarter="karma", guardian="bhishma", element="agni", guna="RAJAS"
        )
        data["claim_level"] = 2  # verified tier
        spec = build_agent_spec("bob", data)

        # Element: transform, audit, validate
        self.assertIn("transform", spec["capabilities"])
        self.assertIn("audit", spec["capabilities"])
        # Guardian (bhishma): sign, ledger, attest
        self.assertIn("sign", spec["capabilities"])
        self.assertIn("ledger", spec["capabilities"])
        # Tier (verified): propose, review, execute, modify
        self.assertIn("propose", spec["capabilities"])
        self.assertIn("execute", spec["capabilities"])
        # No duplicates
        self.assertEqual(len(spec["capabilities"]), len(set(spec["capabilities"])))


# ── CartridgeFactory Tests ───────────────────────────────────────────


class TestCartridgeFactory(unittest.TestCase):
    """Test CartridgeFactory Jiva → cartridge generation."""

    def _make_factory(self, agents=None):
        """Build a CartridgeFactory with mocked Pokedex."""
        from city.cartridge_factory import CartridgeFactory

        pokedex = MagicMock()
        agents = agents or {}
        pokedex.get.side_effect = lambda name: agents.get(name)
        factory = CartridgeFactory(_pokedex=pokedex)
        return factory, pokedex

    def test_generate_from_jiva(self):
        """generate() creates agent with correct domain/capabilities/guardian."""
        data = _agent_data("alice", quarter="dharma", guardian="manu", element="jala")
        factory, _ = self._make_factory({"alice": data})

        agent = factory.generate("alice")

        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "alice")
        self.assertEqual(agent.domain, "GOVERNANCE")
        self.assertEqual(agent.guardian, "manu")
        self.assertEqual(agent.role, "Law, governance, validation")
        self.assertIn("connect", agent.capabilities)  # element
        self.assertIn("legislate", agent.capabilities)  # guardian

    def test_element_capabilities(self):
        """Each Pancha Mahabhuta element maps to correct capability set."""
        from city.guardian_spec import ELEMENT_CAPABILITIES

        self.assertIn("observe", ELEMENT_CAPABILITIES["akasha"])
        self.assertIn("communicate", ELEMENT_CAPABILITIES["vayu"])
        self.assertIn("transform", ELEMENT_CAPABILITIES["agni"])
        self.assertIn("connect", ELEMENT_CAPABILITIES["jala"])
        self.assertIn("build", ELEMENT_CAPABILITIES["prithvi"])
        self.assertEqual(len(ELEMENT_CAPABILITIES), 5)

    def test_quarter_domain(self):
        """Each quarter maps to correct domain."""
        from city.guardian_spec import QUARTER_TO_DOMAIN

        self.assertEqual(QUARTER_TO_DOMAIN["genesis"], "DISCOVERY")
        self.assertEqual(QUARTER_TO_DOMAIN["dharma"], "GOVERNANCE")
        self.assertEqual(QUARTER_TO_DOMAIN["karma"], "ENGINEERING")
        self.assertEqual(QUARTER_TO_DOMAIN["moksha"], "RESEARCH")

    def test_generated_process(self):
        """Generated agent's process() returns enriched result.

        When buddhi is available, returns cognitive action (status=cognized).
        When not, returns full spec echo (status=processed, backward compat).
        """
        data = _agent_data("bob", quarter="moksha", guardian="shuka", element="akasha", guna="SATTVA")
        factory, _ = self._make_factory({"bob": data})

        agent = factory.generate("bob")
        result = agent.process("analyze this")

        # Common fields (both paths)
        self.assertEqual(result["agent"], "bob")
        self.assertEqual(result["domain"], "RESEARCH")
        self.assertEqual(result["input"], "analyze this")
        self.assertIn(result["status"], ("processed", "cognized"))

        if result["status"] == "cognized":
            # Cognitive path: buddhi available
            self.assertIn("function", result)
            self.assertIn("composed", result)
            self.assertIn("prana", result)
            self.assertEqual(result["capability_protocol"], "enforce")
        else:
            # Fallback path: no buddhi
            self.assertEqual(result["guna"], "SATTVA")
            self.assertEqual(result["guardian"], "shuka")
            self.assertEqual(result["role"], "Vision, observation, logging")
            self.assertEqual(result["capability_protocol"], "enforce")
            self.assertIn("parallel", result["qos"])

    def test_caching(self):
        """generate() returns cached instance on second call."""
        data = _agent_data("carol")
        factory, _ = self._make_factory({"carol": data})

        agent1 = factory.generate("carol")
        agent2 = factory.generate("carol")

        self.assertIs(agent1, agent2)

    def test_unknown_agent_returns_none(self):
        """generate() returns None for unknown agent."""
        factory, _ = self._make_factory({})
        result = factory.generate("nobody")
        self.assertIsNone(result)

    def test_get_spec(self):
        """get_spec() returns the AgentSpec dict."""
        data = _agent_data("dave", guardian="yamaraja")
        factory, _ = self._make_factory({"dave": data})
        factory.generate("dave")

        spec = factory.get_spec("dave")

        self.assertIsNotNone(spec)
        self.assertEqual(spec["guardian"], "yamaraja")
        self.assertEqual(spec["opcode"], "AUDIT_SEAL")
        self.assertIn("audit", spec["capabilities"])

    def test_stats(self):
        """Stats reflect generated cartridges including guardians."""
        factory, _ = self._make_factory(
            {
                "a": _agent_data("a", quarter="genesis", guardian="brahma"),
                "b": _agent_data("b", quarter="karma", guardian="parashurama"),
            }
        )
        factory.generate("a")
        factory.generate("b")

        stats = factory.stats()
        self.assertEqual(stats["generated"], 2)
        self.assertIn("DISCOVERY", stats["domains"])
        self.assertIn("ENGINEERING", stats["domains"])
        self.assertIn("brahma", stats["guardians"])
        self.assertIn("parashurama", stats["guardians"])


# ── CityBuilder Tests ────────────────────────────────────────────────


class TestCityBuilder(unittest.TestCase):
    """Test CityBuilder physical city materialization."""

    def _make_builder(self, agents=None, cells=None):
        """Build a CityBuilder with mocked Pokedex and temp directory."""
        from city.city_builder import CityBuilder

        pokedex = MagicMock()
        agents = agents or {}
        cells = cells or {}
        pokedex.get.side_effect = lambda name: agents.get(name)
        pokedex.get_cell.side_effect = lambda name: cells.get(name)
        pokedex.list_citizens.return_value = [{"name": n} for n in agents]

        tmpdir = Path(tempfile.mkdtemp())
        base_path = tmpdir / "agents"
        builder = CityBuilder(_base_path=base_path, _pokedex=pokedex)
        return builder, pokedex, base_path

    def _mock_cell(self, prana=13700, is_alive=True, age=0):
        cell = MagicMock()
        cell.prana = prana
        cell.is_alive = is_alive
        cell.age = age
        return cell

    def test_materialize(self):
        """CityBuilder creates correct directory layout."""
        data = _agent_data("alice")
        cell = self._mock_cell()
        builder, _, base = self._make_builder({"alice": data}, {"alice": cell})

        result = builder.materialize("alice")

        self.assertIsNotNone(result)
        self.assertTrue((base / "alice").is_dir())
        self.assertTrue((base / "alice" / "manifest.json").exists())
        self.assertTrue((base / "alice" / "identity.json").exists())
        self.assertTrue((base / "alice" / "jiva.json").exists())
        self.assertTrue((base / "alice" / "cell.json").exists())

    def test_manifest_enriched(self):
        """manifest.json contains full AgentSpec fields."""
        data = _agent_data("bob", guardian="kapila", element="akasha", guna="SATTVA")
        cell = self._mock_cell()
        builder, _, base = self._make_builder({"bob": data}, {"bob": cell})

        builder.materialize("bob")

        manifest = json.loads((base / "bob" / "manifest.json").read_text())
        self.assertEqual(manifest["name"], "bob")
        self.assertEqual(manifest["domain"], "ENGINEERING")
        self.assertEqual(manifest["guardian"], "kapila")
        self.assertEqual(manifest["opcode"], "TYPE_CHECK")
        self.assertEqual(manifest["role"], "Analysis, classification")
        self.assertTrue(manifest["qos"]["parallel"])
        self.assertEqual(manifest["capability_tier"], "observer")
        # Merged capabilities: element (observe, monitor, report) + guardian (analyze, classify, typecheck)
        self.assertIn("observe", manifest["capabilities"])
        self.assertIn("analyze", manifest["capabilities"])

    def test_manifest_rewritten_on_rematerialize(self):
        """manifest.json is rewritten on re-materialize (not skipped)."""
        data = _agent_data("carol")
        cell = self._mock_cell()
        builder, _, base = self._make_builder({"carol": data}, {"carol": cell})

        builder.materialize("carol")
        first = json.loads((base / "carol" / "manifest.json").read_text())

        # Re-materialize — should update
        builder.materialize("carol")
        second = json.loads((base / "carol" / "manifest.json").read_text())

        # Both should have full spec (created_at will differ)
        self.assertEqual(first["guardian"], second["guardian"])
        self.assertIn("capabilities", second)

    def test_cell_json_updated(self):
        """cell.json reflects current prana state."""
        data = _agent_data("dave")
        cell = self._mock_cell(prana=5000, age=10)
        builder, _, base = self._make_builder({"dave": data}, {"dave": cell})

        builder.materialize("dave")

        cell_data = json.loads((base / "dave" / "cell.json").read_text())
        self.assertEqual(cell_data["prana"], 5000)
        self.assertTrue(cell_data["is_alive"])
        self.assertEqual(cell_data["age"], 10)

    def test_census(self):
        """census() counts physical agent directories."""
        data_a = _agent_data("a")
        data_b = _agent_data("b")
        cell = self._mock_cell()
        builder, _, _ = self._make_builder(
            {"a": data_a, "b": data_b},
            {"a": cell, "b": cell},
        )

        builder.materialize("a")
        builder.materialize("b")

        census = builder.census()
        self.assertEqual(census["total"], 2)
        self.assertIn("a", census["agents"])
        self.assertIn("b", census["agents"])


# ── CartridgeLoader Dynamic Fallback ─────────────────────────────────


class TestCartridgeLoaderFallback(unittest.TestCase):
    def test_loader_dynamic_fallback(self):
        """CityCartridgeLoader.get() falls through to factory."""
        from city.cartridge_loader import CityCartridgeLoader

        factory = MagicMock()
        mock_agent = MagicMock()
        mock_agent.agent_id = "alice"
        factory.get.return_value = mock_agent
        factory.list_generated.return_value = ["alice"]

        loader = CityCartridgeLoader()
        loader._initialized = True
        loader.set_factory(factory)

        result = loader.get("alice")

        self.assertEqual(result.agent_id, "alice")
        factory.get.assert_called_once_with("alice")


# ── Shared Test Helpers ──────────────────────────────────────────────


def _agent_data(
    name,
    quarter="karma",
    guardian="prahlada",
    element="agni",
    guna="RAJAS",
):
    """Build a Pokedex agent dict with all fields for testing."""
    return {
        "name": name,
        "address": 12345,
        "status": "citizen",
        "classification": {
            "quarter": quarter,
            "guardian": guardian,
            "guna": guna,
            "position": 7,
            "holy_name": "KRISHNA",
            "trinity_function": "maintenance",
            "chapter": 3,
            "chapter_significance": "Karma Yoga",
        },
        "vibration": {
            "seed": 42,
            "element": element,
            "shruti": True,
            "frequency": 440,
        },
        "zone": "engineering",
        "identity": {
            "fingerprint": "abc123",
            "public_key": "PEM_KEY",
            "seed_hash": "hash456",
        },
        "oath": {"hash": "oath_hash", "signature": "oath_sig"},
        "claim_level": 0,
    }


if __name__ == "__main__":
    unittest.main()
