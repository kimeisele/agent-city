"""
8G: System Treasury — Prana Economics Tests
=============================================

Tests for:
- SYSTEM_TREASURY CivicBank account initialization
- Pokedex.get_prana() balance lookup
- Pokedex.debit_prana() with treasury credit
- Claim tax enforcement (TRINITY=3 prana gate + debit)
- Brain billing (NAVA=9 prana debit after comprehension)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import pytest

from city.pokedex import SYSTEM_TREASURY, Pokedex
from city.seed_constants import TRINITY, NAVA


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def pdx(tmp_dir):
    """Pokedex with temp DB for treasury tests."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    return Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)


@pytest.fixture
def agent(pdx):
    """Register a standard agent with default genesis prana."""
    pdx.register("TestAgent")
    return "TestAgent"


# ── SystemTreasury Initialization ────────────────────────────────────────


class TestSystemTreasury:
    def test_treasury_account_exists(self, pdx):
        """SYSTEM_TREASURY is initialized in CivicBank on Pokedex creation."""
        balance = pdx._bank.get_balance(SYSTEM_TREASURY)
        assert balance >= 1  # genesis seed

    def test_treasury_constant(self):
        """SYSTEM_TREASURY is a well-known constant."""
        assert SYSTEM_TREASURY == "SYSTEM_TREASURY"


# ── get_prana ────────────────────────────────────────────────────────────


class TestGetPrana:
    def test_get_prana_active_agent(self, pdx, agent):
        """Active agent returns positive prana."""
        prana = pdx.get_prana(agent)
        assert prana > 0

    def test_get_prana_frozen_agent(self, pdx, agent):
        """Frozen agent returns 0."""
        pdx.freeze(agent, "test")
        assert pdx.get_prana(agent) == 0

    def test_get_prana_nonexistent_raises(self, pdx):
        """Nonexistent agent raises KeyError."""
        with pytest.raises(KeyError):
            pdx.get_prana("ghost")


# ── debit_prana ──────────────────────────────────────────────────────────


class TestDebitPrana:
    def test_debit_success(self, pdx, agent):
        """Debit reduces agent's prana and returns True."""
        before = pdx.get_prana(agent)
        result = pdx.debit_prana(agent, 10, reason="test")
        assert result is True
        assert pdx.get_prana(agent) == before - 10

    def test_debit_insufficient_returns_false(self, pdx, agent):
        """Debit fails gracefully when agent can't afford it."""
        prana = pdx.get_prana(agent)
        result = pdx.debit_prana(agent, prana + 1, reason="test")
        assert result is False
        assert pdx.get_prana(agent) == prana  # unchanged

    def test_debit_zero_is_noop(self, pdx, agent):
        """Zero debit succeeds without touching balance."""
        before = pdx.get_prana(agent)
        result = pdx.debit_prana(agent, 0, reason="test")
        assert result is True
        assert pdx.get_prana(agent) == before

    def test_debit_frozen_agent_fails(self, pdx, agent):
        """Frozen agents cannot be debited."""
        pdx.freeze(agent, "test")
        result = pdx.debit_prana(agent, 1, reason="test")
        assert result is False

    def test_debit_nonexistent_agent_fails(self, pdx):
        """Nonexistent agent debit returns False (no crash)."""
        result = pdx.debit_prana("ghost", 1, reason="test")
        assert result is False

    def test_debit_credits_treasury(self, pdx, agent):
        """Debit prana credits the SystemTreasury in CivicBank."""
        treasury_before = pdx._bank.get_balance(SYSTEM_TREASURY)
        pdx.debit_prana(agent, 10, reason="test")
        treasury_after = pdx._bank.get_balance(SYSTEM_TREASURY)
        assert treasury_after == treasury_before + 10

    def test_debit_records_event(self, pdx, agent):
        """Debit creates a prana_debit event in the ledger."""
        pdx.debit_prana(agent, 5, reason="claim_tax")
        cur = pdx._conn.cursor()
        cur.execute(
            "SELECT details FROM events WHERE agent_name = ? AND event_type = 'prana_debit'",
            (agent,),
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert "claim_tax" in rows[0]["details"]


# ── Claim Tax (8G-2 integration) ────────────────────────────────────────


class TestClaimTax:
    def test_claim_cost_is_trinity(self):
        """Claim tax is TRINITY (3) — same as one metabolic cycle."""
        assert TRINITY == 3

    def test_claim_drains_prana(self, pdx, agent):
        """Simulated claim tax: agent pays TRINITY prana."""
        before = pdx.get_prana(agent)
        pdx.debit_prana(agent, TRINITY, reason="claim_tax")
        assert pdx.get_prana(agent) == before - TRINITY

    def test_broke_agent_cannot_claim(self, pdx, agent):
        """Agent with prana < TRINITY cannot afford a claim."""
        # Drain almost all prana
        prana = pdx.get_prana(agent)
        pdx.debit_prana(agent, prana - 1, reason="drain")
        assert pdx.get_prana(agent) == 1
        assert pdx.get_prana(agent) < TRINITY
        # Claim should fail
        result = pdx.debit_prana(agent, TRINITY, reason="claim_tax")
        assert result is False


# ── Brain Billing (8G-3 integration) ────────────────────────────────────


class TestBrainBilling:
    def test_brain_cost_is_nava(self):
        """Brain call cost is NAVA (9) — from brain_cell.py."""
        from city.brain_cell import BRAIN_CALL_COST
        assert BRAIN_CALL_COST == NAVA
        assert NAVA == 9

    def test_brain_billing_debits_agent(self, pdx, agent):
        """Brain comprehension costs NAVA prana from the routed agent."""
        from city.brain_cell import BRAIN_CALL_COST
        before = pdx.get_prana(agent)
        pdx.debit_prana(agent, BRAIN_CALL_COST, reason="brain_comprehension")
        assert pdx.get_prana(agent) == before - BRAIN_CALL_COST

    def test_full_cycle_cost(self, pdx, agent):
        """Full claim+brain cycle costs TRINITY + NAVA = 12 prana."""
        from city.brain_cell import BRAIN_CALL_COST
        before = pdx.get_prana(agent)
        pdx.debit_prana(agent, TRINITY, reason="claim_tax")
        pdx.debit_prana(agent, BRAIN_CALL_COST, reason="brain_comprehension")
        assert pdx.get_prana(agent) == before - (TRINITY + BRAIN_CALL_COST)
        assert TRINITY + BRAIN_CALL_COST == 12
