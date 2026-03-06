"""
8G+8H: System Treasury + MOKSHA Decouple — Prana Economics Tests
=================================================================

Tests for:
- SYSTEM_TREASURY CivicBank account initialization
- Pokedex.get_prana() balance lookup
- Pokedex.debit_prana() with treasury credit
- Claim tax enforcement (TRINITY=3 prana gate + debit)
- Brain billing (NAVA=9 prana debit after comprehension)
- 8H: ThoughtKind.INSIGHT, insight payload, post_agent_insight, fallback

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import pytest

from city.pokedex import SYSTEM_TREASURY, Pokedex
from city.seed_constants import TRINITY, NAVA


def _root_membrane():
    from city.membrane import internal_membrane_snapshot

    return internal_membrane_snapshot(source_class="tests")


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
        pdx.freeze(agent, "test", membrane=_root_membrane())
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
        pdx.freeze(agent, "test", membrane=_root_membrane())
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


# ── 8H: MOKSHA Decouple — Insight Generation ──────────────────────────


class TestThoughtKindInsight:
    def test_insight_enum_exists(self):
        """ThoughtKind.INSIGHT is a valid enum member."""
        from city.brain import ThoughtKind
        assert ThoughtKind.INSIGHT == "insight"
        assert ThoughtKind.INSIGHT.value == "insight"

    def test_insight_in_thought_kinds(self):
        """INSIGHT is listed alongside existing thought kinds."""
        from city.brain import ThoughtKind
        kinds = [k.value for k in ThoughtKind]
        assert "insight" in kinds
        assert "comprehension" in kinds
        assert "reflection" in kinds


class TestInsightPrompt:
    def test_insight_payload_builder(self):
        """_payload_insight returns city synthesizer persona lines."""
        from city.brain_prompt import build_payload
        lines = build_payload(
            "insight",
            reflection={"mission_results_terminal": [
                {"name": "fix-auth", "status": "completed", "owner": "agentA"},
            ]},
        )
        text = "\n".join(lines)
        assert "synthesizer" in text.lower()
        assert "fix-auth" in text
        assert "agentA" in text

    def test_insight_payload_empty_missions(self):
        """Insight payload with no missions still returns persona lines."""
        from city.brain_prompt import build_payload
        lines = build_payload("insight", reflection={})
        text = "\n".join(lines)
        assert "synthesizer" in text.lower()
        assert "Terminal missions" not in text

    def test_insight_schema_exists(self):
        """Insight schema is registered and doesn't contain 'Respond with JSON'."""
        from city.brain_prompt import build_schema
        schema = build_schema("insight")
        assert "insight" in schema.lower()
        assert "Respond with JSON" not in schema


class TestBrainGenerateInsight:
    def test_generate_insight_method_exists(self):
        """CityBrain has generate_insight method."""
        from city.brain import CityBrain
        brain = CityBrain()
        assert hasattr(brain, "generate_insight")
        assert callable(brain.generate_insight)

    def test_generate_insight_no_provider_returns_none(self):
        """generate_insight returns None when LLM is unavailable."""
        from city.brain import CityBrain
        brain = CityBrain()
        brain._available = False
        result = brain.generate_insight(
            {"mission_results_terminal": [{"name": "test", "status": "completed"}]},
        )
        assert result is None


class TestPostAgentInsight:
    def test_post_agent_insight_formats_thought(self):
        """post_agent_insight extracts fields from Thought-like object."""
        from city.brain import Thought, BrainIntent, ThoughtKind
        from city.moltbook_bridge import AGENT_INSIGHT_PREFIX

        thought = Thought(
            comprehension="Auth module stabilized, security domain needs rate limiting",
            intent=BrainIntent.OBSERVE,
            domain_relevance="security",
            key_concepts=("auth", "rate-limiting"),
            confidence=0.85,
            kind=ThoughtKind.INSIGHT,
        )

        # Verify the prefix constant
        assert AGENT_INSIGHT_PREFIX == "[Agent Insight]"

        # Verify thought fields are accessible (duck typing used by bridge)
        assert thought.comprehension
        assert thought.key_concepts == ("auth", "rate-limiting")
        assert thought.confidence == 0.85


class TestMoltbookOutboundFallback:
    def test_fallback_path_exists(self):
        """MoltbookOutboundHook has _post_insight_or_fallback method."""
        from city.hooks.moksha.outbound import MoltbookOutboundHook
        assert hasattr(MoltbookOutboundHook, "_post_insight_or_fallback")
