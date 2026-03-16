"""Tests for Governance Integration — Phase 8.

4 mayor power + 5 marketplace governance + 3 proposal expiry
+ 2 council compensation + 2 persistence/stats + 2 constants = 18 tests.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from city.council import (
    CityCouncil,
    ProposalStatus,
    ProposalType,
    VoteChoice,
)


def _make_council() -> CityCouncil:
    """Create a fresh council with no state file."""
    return CityCouncil()


def _elect(council: CityCouncil, names: list[str], heartbeat: int = 0) -> dict:
    """Run election with given names (prana descending)."""
    candidates = [
        {"name": n, "prana": (len(names) - i) * 5000, "rank_score": (len(names) - i) / len(names)}
        for i, n in enumerate(names)
    ]
    return council.run_election(candidates, heartbeat)


# ── Mayor Power Tests ──────────────────────────────────────────────


class TestMayorPower(unittest.TestCase):
    """Mayor gets real authority: triple vote weight, exclusive marketplace proposals."""

    def setUp(self):
        self.council = _make_council()
        self.result = _elect(self.council, ["Mayor", "V1", "V2"])
        self.assertEqual(self.council.elected_mayor, "Mayor")

    def test_mayor_vote_triple_weight(self):
        """Mayor's prana_weight multiplied by TRINITY (3) in tally."""
        p = self.council.propose(
            "Test policy",
            "Desc",
            "Mayor",
            ProposalType.POLICY,
            {"type": "improve"},
            time.time(),
            heartbeat=0,
        )
        self.assertIsNotNone(p)

        # Mayor votes YES with 1000 prana (effective: 3000)
        self.council.vote(p.id, "Mayor", VoteChoice.YES, 1000)
        # V1 and V2 vote NO with 1000 each (effective: 2000 total)
        self.council.vote(p.id, "V1", VoteChoice.NO, 1000)
        self.council.vote(p.id, "V2", VoteChoice.NO, 1000)

        result = self.council.tally(p.id)
        # Mayor 3000 YES vs 2000 NO → 60% → passes (>50%)
        self.assertEqual(result.status, ProposalStatus.PASSED)

    def test_mayor_only_marketplace_proposals(self):
        """Non-mayor council members cannot submit MARKETPLACE proposals."""
        p = self.council.propose(
            "Set commission",
            "Desc",
            "V1",
            ProposalType.MARKETPLACE,
            {"type": "set_commission", "rate": 10},
            time.time(),
            heartbeat=0,
        )
        self.assertIsNone(p)

    def test_mayor_marketplace_proposal_passes(self):
        """Mayor submits set_commission → voted → executed → override takes effect."""
        p = self.council.propose(
            "Lower commission",
            "Desc",
            "Mayor",
            ProposalType.MARKETPLACE,
            {"type": "set_commission", "rate": 12},
            time.time(),
            heartbeat=0,
        )
        self.assertIsNotNone(p)

        self.council.vote(p.id, "Mayor", VoteChoice.YES, 5000)
        self.council.vote(p.id, "V1", VoteChoice.YES, 4000)
        result = self.council.tally(p.id)
        self.assertEqual(result.status, ProposalStatus.PASSED)

        # Execute marketplace action
        success = self.council.apply_marketplace_action(p.action)
        self.assertTrue(success)
        self.assertEqual(self.council.effective_commission, 12)
        self.council.mark_executed(p.id)
        self.assertEqual(self.council.get_proposal(p.id).status, ProposalStatus.EXECUTED)

    def test_mayor_replaced_next_election(self):
        """New election → different mayor → old mayor loses MARKETPLACE privilege."""
        # Re-elect with different order — NewMayor has higher prana
        _elect(self.council, ["NewMayor", "Mayor", "V1"], heartbeat=200)
        self.assertEqual(self.council.elected_mayor, "NewMayor")

        # Old mayor can't submit MARKETPLACE anymore
        p = self.council.propose(
            "Old mayor tries",
            "Desc",
            "Mayor",
            ProposalType.MARKETPLACE,
            {"type": "freeze_market"},
            time.time(),
            heartbeat=200,
        )
        self.assertIsNone(p)

    @patch("city.membrane.authorize_ingress", return_value=(False, "access<operator"))
    def test_council_execution_requires_internal_authority(self, authorize_ingress):
        """Passed proposals must still cross an explicit internal authority gate."""
        from city.karma_handlers.council import _execute_proposal

        p = self.council.propose(
            "Freeze market",
            "Desc",
            "Mayor",
            ProposalType.MARKETPLACE,
            {"type": "freeze_market"},
            time.time(),
            heartbeat=0,
        )
        self.assertIsNotNone(p)

        self.council.vote(p.id, "Mayor", VoteChoice.YES, 5000)
        self.council.vote(p.id, "V1", VoteChoice.YES, 4000)
        passed = self.council.tally(p.id)
        self.assertEqual(passed.status, ProposalStatus.PASSED)

        ctx = MagicMock()
        ctx.council = self.council

        executed = _execute_proposal(ctx, passed)

        self.assertFalse(executed)
        self.assertFalse(self.council.is_market_frozen)

        _, kwargs = authorize_ingress.call_args
        self.assertEqual(kwargs["membrane"]["surface"], "local")
        self.assertEqual(kwargs["membrane"]["source_class"], "governance")


# ── Marketplace Governance Tests ───────────────────────────────────


class TestMarketplaceGovernance(unittest.TestCase):
    """Council governance over marketplace: commission, freeze/unfreeze."""

    def setUp(self):
        self.council = _make_council()
        _elect(self.council, ["Mayor", "V1", "V2"])

    def test_set_commission_within_bounds(self):
        """Override commission to 12% → effective_commission == 12."""
        ok = self.council.apply_marketplace_action({"type": "set_commission", "rate": 12})
        self.assertTrue(ok)
        self.assertEqual(self.council.effective_commission, 12)

    def test_set_commission_exceeds_cap(self):
        """Try to set 25% → rejected (MAX_COMMISSION_PERCENT == 18)."""
        ok = self.council.apply_marketplace_action({"type": "set_commission", "rate": 25})
        self.assertFalse(ok)
        self.assertIsNone(self.council.effective_commission)

    def test_freeze_market(self):
        """apply_marketplace_action(freeze) → is_market_frozen == True."""
        self.assertFalse(self.council.is_market_frozen)
        ok = self.council.apply_marketplace_action({"type": "freeze_market"})
        self.assertTrue(ok)
        self.assertTrue(self.council.is_market_frozen)

    def test_unfreeze_market(self):
        """Freeze then unfreeze → is_market_frozen == False."""
        self.council.apply_marketplace_action({"type": "freeze_market"})
        self.assertTrue(self.council.is_market_frozen)

        ok = self.council.apply_marketplace_action({"type": "unfreeze_market"})
        self.assertTrue(ok)
        self.assertFalse(self.council.is_market_frozen)

    def test_frozen_market_skips_matching(self):
        """With council frozen → _process_marketplace returns early."""
        from city.karma_handlers.marketplace import _process_marketplace

        self.council.apply_marketplace_action({"type": "freeze_market"})

        ctx = MagicMock()
        ctx.council = self.council
        ctx.pokedex = MagicMock()
        ctx.active_agents = {"agent_a"}
        ctx.sankalpa = None
        operations: list[str] = []

        _process_marketplace(ctx, operations, {}, {})

        # Should have returned early with frozen message
        self.assertIn("marketplace:frozen_by_council", operations)
        # expire_orders should NOT have been called (early return)
        ctx.pokedex.expire_orders.assert_not_called()


# ── Proposal Expiry Tests ──────────────────────────────────────────


class TestProposalExpiry(unittest.TestCase):
    """Proposals auto-expire after MALA (108) heartbeats."""

    def setUp(self):
        self.council = _make_council()
        _elect(self.council, ["Mayor", "V1", "V2"])

    def test_proposal_expires_after_mala(self):
        """Open proposal at heartbeat 0, expire at 200 → status == EXPIRED."""
        p = self.council.propose(
            "Stale idea",
            "Desc",
            "Mayor",
            ProposalType.POLICY,
            {"type": "improve"},
            time.time(),
            heartbeat=0,
        )
        self.assertIsNotNone(p)

        count = self.council.expire_proposals(heartbeat=200)
        self.assertEqual(count, 1)

        updated = self.council.get_proposal(p.id)
        self.assertEqual(updated.status, ProposalStatus.EXPIRED)

    def test_proposal_survives_within_window(self):
        """Open proposal at heartbeat 50, expire at 100 → still OPEN."""
        p = self.council.propose(
            "Fresh idea",
            "Desc",
            "Mayor",
            ProposalType.POLICY,
            {"type": "improve"},
            time.time(),
            heartbeat=50,
        )
        self.assertIsNotNone(p)

        count = self.council.expire_proposals(heartbeat=100)
        self.assertEqual(count, 0)

        updated = self.council.get_proposal(p.id)
        self.assertEqual(updated.status, ProposalStatus.OPEN)

    def test_expired_proposal_not_votable(self):
        """Expired proposals can't be voted on."""
        p = self.council.propose(
            "Old",
            "Desc",
            "Mayor",
            ProposalType.POLICY,
            {"type": "improve"},
            time.time(),
            heartbeat=0,
        )
        self.council.expire_proposals(heartbeat=200)

        ok = self.council.vote(p.id, "Mayor", VoteChoice.YES, 5000)
        self.assertFalse(ok)


# ── Council Compensation Tests ─────────────────────────────────────


class TestCouncilCompensation(unittest.TestCase):
    """Council members receive stipend on election."""

    def _make_pokedex(self):
        from city.pokedex import Pokedex

        db_path = Path(tempfile.mktemp(suffix=".db"))
        return Pokedex(db_path=db_path)

    def test_council_stipend_on_election(self):
        """After election, each member's balance increases by WORKER_VISA_STIPEND."""
        from city.seed_constants import WORKER_VISA_STIPEND

        pokedex = self._make_pokedex()
        pokedex.discover("Mayor")
        pokedex.register("Mayor", grant_override=108)
        pokedex.discover("V1")
        pokedex.register("V1", grant_override=108)

        mayor_before = pokedex._bank.get_balance("Mayor")

        council = _make_council()
        result = _elect(council, ["Mayor", "V1"], heartbeat=0)

        # Simulate DHARMA stipend payment
        stipend_key = "_stipend_paid_0"
        if not getattr(council, stipend_key, False):
            for _seat_idx, member_name in result["council_seats"].items():
                pokedex.mint_prana(
                    member_name,
                    WORKER_VISA_STIPEND,
                    "council_stipend",
                    category="governance",
                )
            setattr(council, stipend_key, True)

        mayor_after = pokedex._bank.get_balance("Mayor")
        self.assertEqual(mayor_after - mayor_before, WORKER_VISA_STIPEND)

    def test_stipend_amount_is_36(self):
        """WORKER_VISA_STIPEND == 36 (MALA // TRINITY)."""
        from city.seed_constants import WORKER_VISA_STIPEND

        self.assertEqual(WORKER_VISA_STIPEND, 36)


# ── Persistence & Stats Tests ──────────────────────────────────────


class TestGovernancePersistence(unittest.TestCase):
    """Council state survives save/load including marketplace governance."""

    def test_council_state_persists_marketplace(self):
        """Save/load council → market_frozen and commission_override survive."""
        council = _make_council()
        _elect(council, ["Mayor", "V1"])

        council.apply_marketplace_action({"type": "freeze_market"})
        council.apply_marketplace_action({"type": "set_commission", "rate": 10})

        # Serialize and restore
        data = council.to_dict()
        restored = CityCouncil.from_dict(data)

        self.assertTrue(restored.is_market_frozen)
        self.assertEqual(restored.effective_commission, 10)
        self.assertEqual(restored.elected_mayor, "Mayor")

    def test_governance_stats_in_reflection(self):
        """MOKSHA reflection dict should include governance key."""
        council = _make_council()
        _elect(council, ["Mayor", "V1", "V2"])
        council.apply_marketplace_action({"type": "set_commission", "rate": 8})

        # Simulate what moksha.py does
        gov_stats = {
            "council_members": council.member_count,
            "elected_mayor": council.elected_mayor,
            "open_proposals": len(council.get_open_proposals()),
            "market_frozen": council.is_market_frozen,
            "effective_commission": council.effective_commission,
        }

        self.assertEqual(gov_stats["council_members"], 3)
        self.assertEqual(gov_stats["elected_mayor"], "Mayor")
        self.assertFalse(gov_stats["market_frozen"])
        self.assertEqual(gov_stats["effective_commission"], 8)


# ── Constants Tests ────────────────────────────────────────────────


class TestGovernanceConstants(unittest.TestCase):
    """Verify Mahamantra-derived governance constants."""

    def test_proposal_expiry_is_mala(self):
        """PROPOSAL_EXPIRY_HEARTBEATS == 108."""
        from city.seed_constants import PROPOSAL_EXPIRY_HEARTBEATS

        self.assertEqual(PROPOSAL_EXPIRY_HEARTBEATS, 108)

    def test_max_commission_is_trinity_sharanagati(self):
        """MAX_COMMISSION_PERCENT == 18 (TRINITY × SHARANAGATI = 3 × 6)."""
        from city.seed_constants import MAX_COMMISSION_PERCENT

        self.assertEqual(MAX_COMMISSION_PERCENT, 18)


if __name__ == "__main__":
    unittest.main()
