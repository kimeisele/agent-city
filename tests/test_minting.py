"""Tests for Asset Minting — Phase 6.

3 starter pack tests + 3 MOKSHA reward tests + 2 constant tests.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_pokedex():
    """Create a fresh Pokedex with a temp database."""
    from city.pokedex import Pokedex

    db_path = Path(tempfile.mktemp(suffix=".db"))
    return Pokedex(db_path=db_path)


# ── Constant Tests ───────────────────────────────────────────────────


class TestMintingConstants(unittest.TestCase):
    """Minting constants derived from Mahamantra."""

    def test_minting_constants_derived(self):
        """STARTER_PACK_TOKENS == TRINITY (3), EARLY_CITIZEN_BONUS == NAVA (9)."""
        from city.seed_constants import (
            EARLY_CITIZEN_BONUS,
            MISSION_REWARD_TOKENS,
            STARTER_PACK_TOKENS,
        )

        self.assertEqual(STARTER_PACK_TOKENS, 3)
        self.assertEqual(MISSION_REWARD_TOKENS, 1)
        self.assertEqual(EARLY_CITIZEN_BONUS, 9)

    def test_early_threshold_is_mala(self):
        """EARLY_CITIZEN_THRESHOLD == MALA (108)."""
        from city.seed_constants import EARLY_CITIZEN_THRESHOLD

        self.assertEqual(EARLY_CITIZEN_THRESHOLD, 108)


# ── Starter Pack Tests ───────────────────────────────────────────────


class TestStarterPack(unittest.TestCase):
    """Starter assets granted at citizenship registration."""

    def test_starter_pack_on_register(self):
        """New citizen gets STARTER_PACK_TOKENS capability tokens."""
        pokedex = _make_pokedex()
        pokedex.discover("alice")
        pokedex.register("alice")

        inv = pokedex.get_inventory("alice")
        cap_tokens = [a for a in inv if a["asset_type"] == "capability_token"]

        # Should have exactly STARTER_PACK_TOKENS (3) capability tokens
        self.assertEqual(len(cap_tokens), 3)

        # All should be from starter_pack source
        for token in cap_tokens:
            self.assertEqual(token["source"], "starter_pack")
            self.assertEqual(token["quantity"], 1)

    def test_early_citizen_bonus(self):
        """First EARLY_CITIZEN_THRESHOLD citizens get bonus word_tokens."""
        pokedex = _make_pokedex()
        pokedex.discover("pioneer")
        pokedex.register("pioneer")

        inv = pokedex.get_inventory("pioneer")
        word_tokens = [a for a in inv if a["asset_type"] == "word_token"]

        # Should have early citizen bonus
        self.assertEqual(len(word_tokens), 1)
        self.assertEqual(word_tokens[0]["asset_id"], "early_citizen")
        self.assertEqual(word_tokens[0]["quantity"], 9)  # NAVA
        self.assertEqual(word_tokens[0]["source"], "genesis_bonus")

    def test_no_starter_for_worker_visa(self):
        """grant_override != None → no starter pack (Worker-Visa agents)."""
        from city.seed_constants import WORKER_VISA_STIPEND

        pokedex = _make_pokedex()
        pokedex.discover("temp_worker")
        pokedex.register("temp_worker", grant_override=WORKER_VISA_STIPEND)

        inv = pokedex.get_inventory("temp_worker")
        # Worker-Visa agents get NO starter pack
        self.assertEqual(len(inv), 0)


# ── MOKSHA Reward Tests ──────────────────────────────────────────────


class TestMokshaRewards(unittest.TestCase):
    """MOKSHA mints rewards for completed missions."""

    def _make_ctx_and_pokedex(self):
        """Create minimal PhaseContext with pokedex for testing."""
        from unittest.mock import MagicMock

        pokedex = _make_pokedex()
        pokedex.discover("agent_a")
        pokedex.register("agent_a")

        ctx = MagicMock()
        ctx.pokedex = pokedex
        return ctx, pokedex

    def test_reward_for_completed_mission(self):
        """Completed mission → capability_token minted for owner."""
        from city.hooks.moksha.mission_lifecycle import _mint_mission_rewards

        ctx, pokedex = self._make_ctx_and_pokedex()

        terminal = [
            {"id": "exec_deploy_42", "name": "Deploy", "status": "completed", "owner": "agent_a"},
        ]
        results = _mint_mission_rewards(ctx, terminal)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["agent"], "agent_a")
        self.assertEqual(results[0]["asset"], "execute")

        # Verify asset actually exists
        self.assertTrue(pokedex.has_asset("agent_a", "capability_token", "execute"))

    def test_no_reward_for_abandoned(self):
        """Abandoned mission → no minting."""
        from city.hooks.moksha.mission_lifecycle import _mint_mission_rewards

        ctx, pokedex = self._make_ctx_and_pokedex()

        # Count assets before
        inv_before = len(pokedex.get_inventory("agent_a"))

        terminal = [
            {"id": "heal_fix_99", "name": "Fix", "status": "abandoned", "owner": "agent_a"},
        ]
        results = _mint_mission_rewards(ctx, terminal)

        self.assertEqual(len(results), 0)
        # No new assets minted
        inv_after = len(pokedex.get_inventory("agent_a"))
        self.assertEqual(inv_before, inv_after)

    def test_reward_type_matches_prefix(self):
        """heal_ → validate, exec_ → execute, signal_ → observe."""
        from city.hooks.moksha.mission_lifecycle import _mint_mission_rewards

        ctx, pokedex = self._make_ctx_and_pokedex()

        terminal = [
            {"id": "heal_fix_1", "name": "Fix", "status": "completed", "owner": "agent_a"},
            {"id": "signal_alert_2", "name": "Alert", "status": "completed", "owner": "agent_a"},
            {"id": "audit_check_3", "name": "Audit", "status": "completed", "owner": "agent_a"},
        ]
        results = _mint_mission_rewards(ctx, terminal)

        self.assertEqual(len(results), 3)
        assets = {r["asset"] for r in results}
        self.assertEqual(assets, {"validate", "observe", "audit"})


if __name__ == "__main__":
    unittest.main()
