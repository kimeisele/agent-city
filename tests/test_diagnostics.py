"""
Tests for CityDiagnostics — GAD-000 introspection service.

All gateway/buddhi calls use real local computation (no mocks on core).
CartridgeFactory and Pokedex are lightweight fakes to avoid SQLite.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from city.diagnostics import (
    CityDiagnostics,
    eligible_intents_for_agent,
    score_agent_for_discussion,
)


# ── Fake Collaborators ───────────────────────────────────────────────


SPEC_ALPHA = {
    "name": "Alpha",
    "domain": "GOVERNANCE",
    "guna": "SATTVA",
    "guardian": "kapila",
    "element": "FIRE",
    "role": "validator",
    "capabilities": ["validate", "propose", "observe", "audit"],
    "capability_tier": "contributor",
    "capability_protocol": "validate",
    "qos": {"latency_multiplier": 1.0, "parallel": False},
    "chapter": 7,
    "chapter_significance": "Knowledge",
    "element_capabilities": [],
    "guardian_capabilities": [],
    "style": "analytical",
    "opcode": 42,
}

SPEC_BETA = {
    "name": "Beta",
    "domain": "DISCOVERY",
    "guna": "RAJAS",
    "guardian": "narada",
    "element": "WIND",
    "role": "scout",
    "capabilities": ["observe", "report", "relay"],
    "capability_tier": "contributor",
    "capability_protocol": "parse",
    "qos": {"latency_multiplier": 1.5, "parallel": True},
    "chapter": 3,
    "chapter_significance": "Karma Yoga",
    "element_capabilities": [],
    "guardian_capabilities": [],
    "style": "energetic",
    "opcode": 17,
}

SPEC_GAMMA = {
    "name": "Gamma",
    "domain": "ENGINEERING",
    "guna": "TAMAS",
    "guardian": "prahlada",
    "element": "EARTH",
    "role": "builder",
    "capabilities": ["execute", "build"],
    "capability_tier": "observer",
    "capability_protocol": "infer",
    "qos": {"latency_multiplier": 2.0, "parallel": False},
    "chapter": 12,
    "chapter_significance": "Devotion",
    "element_capabilities": [],
    "guardian_capabilities": [],
    "style": "methodical",
    "opcode": 99,
}


class FakeAgent:
    def __init__(self, spec: dict):
        self._spec = spec
        for k, v in spec.items():
            setattr(self, k, v)


class FakeCell:
    def __init__(self, prana: int = 10000, is_alive: bool = True, integrity: int = 21600):
        self.prana = prana
        self.is_alive = is_alive
        self.integrity = integrity


class FakeFactory:
    def __init__(self, specs: dict[str, dict]):
        self._specs = specs
        self._agents = {name: FakeAgent(spec) for name, spec in specs.items()}

    def list_generated(self) -> list[str]:
        return list(self._specs.keys())

    def get_spec(self, name: str) -> dict | None:
        return self._specs.get(name)

    def generate(self, name: str) -> object | None:
        return self._agents.get(name)


class FakePokedex:
    def __init__(self, cells: dict[str, FakeCell] | None = None):
        self._cells = cells or {}

    def stats(self) -> dict:
        total = len(self._cells)
        alive = sum(1 for c in self._cells.values() if c.is_alive)
        return {"total": total, "active": alive}

    def get_cell(self, name: str) -> FakeCell | None:
        return self._cells.get(name)


def _make_diagnostics(
    specs: dict[str, dict] | None = None,
    cells: dict[str, FakeCell] | None = None,
) -> CityDiagnostics:
    """Build a CityDiagnostics with fakes."""
    from city.gateway import CityGateway

    if specs is None:
        specs = {"Alpha": SPEC_ALPHA, "Beta": SPEC_BETA, "Gamma": SPEC_GAMMA}
    factory = FakeFactory(specs)
    pokedex = FakePokedex(cells)
    gateway = CityGateway()
    return CityDiagnostics(
        _gateway=gateway,
        _factory=factory,
        _pokedex=pokedex,
    )


# ── Test: score_agent_for_discussion (pure function) ─────────────────


class TestScoreAgentForDiscussion:
    def test_governance_domain_boosts_propose_intent(self):
        score = score_agent_for_discussion(SPEC_ALPHA, "propose")
        assert score > 0.0
        # Alpha is GOVERNANCE domain, propose prefers GOVERNANCE → +0.4
        assert score >= 0.4

    def test_discovery_domain_boosts_inquiry_intent(self):
        score = score_agent_for_discussion(SPEC_BETA, "inquiry")
        # Beta is DISCOVERY domain, inquiry prefers DISCOVERY → +0.4
        assert score >= 0.4

    def test_no_domain_match_lowers_score(self):
        score_match = score_agent_for_discussion(SPEC_ALPHA, "propose")
        score_no_match = score_agent_for_discussion(SPEC_GAMMA, "propose")
        assert score_match > score_no_match

    def test_capability_coverage_affects_score(self):
        # Alpha has "propose" cap, Gamma does not
        score_alpha = score_agent_for_discussion(SPEC_ALPHA, "propose")
        score_gamma = score_agent_for_discussion(SPEC_GAMMA, "propose")
        assert score_alpha > score_gamma

    def test_qos_latency_factor(self):
        # Alpha has latency 1.0, Beta has 1.5, Gamma has 2.0
        # For the same intent (observe), lower latency = higher QoS bonus
        s_alpha = score_agent_for_discussion(SPEC_ALPHA, "observe")
        s_gamma = score_agent_for_discussion(SPEC_GAMMA, "observe")
        # Both have "observe" cap, but Alpha has better QoS
        assert s_alpha >= s_gamma

    def test_observe_fallback_intent(self):
        score = score_agent_for_discussion(SPEC_ALPHA, "observe")
        assert score >= 0.0

    def test_unknown_intent_uses_observe(self):
        score = score_agent_for_discussion(SPEC_ALPHA, "nonexistent")
        observe_score = score_agent_for_discussion(SPEC_ALPHA, "observe")
        assert score == observe_score

    def test_score_is_rounded(self):
        score = score_agent_for_discussion(SPEC_ALPHA, "propose")
        # Check it's rounded to 3 decimal places
        assert score == round(score, 3)


# ── Test: eligible_intents_for_agent ─────────────────────────────────


class TestEligibleIntents:
    def test_alpha_eligible_intents(self):
        eligible = eligible_intents_for_agent(SPEC_ALPHA)
        # Alpha has validate, propose, observe, audit → contributor tier
        assert "propose" in eligible
        assert "observe" in eligible

    def test_gamma_observer_tier_blocks_most_intents(self):
        eligible = eligible_intents_for_agent(SPEC_GAMMA)
        # Gamma is observer tier, min_tier is contributor → blocked
        assert len(eligible) == 0

    def test_beta_eligible_for_inquiry(self):
        eligible = eligible_intents_for_agent(SPEC_BETA)
        # Beta has observe + report → inquiry requires observe + report
        assert "inquiry" in eligible


# ── Test: CityDiagnostics.predict_discussion ─────────────────────────


class TestPredictDiscussion:
    def test_basic_prediction(self):
        diag = _make_diagnostics()
        result = diag.predict_discussion("Should we add a marketplace?")

        assert "input" in result
        assert result["input"] == "Should we add a marketplace?"
        assert "gateway" in result
        assert "buddhi_function" in result["gateway"]
        assert "buddhi_chapter" in result["gateway"]
        assert "buddhi_mode" in result["gateway"]
        assert "seed" in result["gateway"]
        assert "intent" in result
        assert "agents" in result
        assert "best_agent" in result
        assert "city_stats" in result

    def test_agents_sorted_by_score(self):
        diag = _make_diagnostics()
        result = diag.predict_discussion("audit the governance contracts")

        agents = result["agents"]
        assert len(agents) == 3
        scores = [a["score"] for a in agents]
        assert scores == sorted(scores, reverse=True)

    def test_filter_by_agent_name(self):
        diag = _make_diagnostics()
        result = diag.predict_discussion("test input", agent_name="Beta")

        agents = result["agents"]
        assert len(agents) == 1
        assert agents[0]["name"] == "Beta"

    def test_filter_nonexistent_agent(self):
        diag = _make_diagnostics()
        result = diag.predict_discussion("test input", agent_name="Nobody")

        assert result["agents"] == []
        assert result["best_agent"] is None

    def test_increments_predicts_counter(self):
        diag = _make_diagnostics()
        assert diag.stats()["predicts"] == 0
        diag.predict_discussion("test")
        assert diag.stats()["predicts"] == 1
        diag.predict_discussion("test2")
        assert diag.stats()["predicts"] == 2

    def test_agent_entry_fields(self):
        diag = _make_diagnostics()
        result = diag.predict_discussion("hello")
        agent = result["agents"][0]
        assert "name" in agent
        assert "domain" in agent
        assert "guna" in agent
        assert "guardian" in agent
        assert "tier" in agent
        assert "score" in agent
        assert "response" in agent
        assert isinstance(agent["score"], float)
        assert isinstance(agent["response"], str)


# ── Test: CityDiagnostics.inspect_agent ──────────────────────────────


class TestInspectAgent:
    def test_inspect_known_agent(self):
        cells = {"Alpha": FakeCell(prana=12000, is_alive=True, integrity=21600)}
        diag = _make_diagnostics(cells=cells)
        result = diag.inspect_agent("Alpha")

        assert result["name"] == "Alpha"
        assert "spec" in result
        assert result["spec"]["domain"] == "GOVERNANCE"
        assert result["cell"]["prana"] == 12000
        assert result["cell"]["is_alive"] is True
        assert "routing" in result
        assert "eligible_intents" in result["routing"]
        assert result["routing"]["tier"] == "contributor"

    def test_inspect_agent_no_cell(self):
        diag = _make_diagnostics()
        result = diag.inspect_agent("Alpha")

        assert result["name"] == "Alpha"
        assert result["cell"] is None

    def test_inspect_unknown_agent(self):
        diag = _make_diagnostics()
        result = diag.inspect_agent("Nobody")

        assert "error" in result

    def test_increments_inspects_counter(self):
        diag = _make_diagnostics()
        assert diag.stats()["inspects"] == 0
        diag.inspect_agent("Alpha")
        assert diag.stats()["inspects"] == 1


# ── Test: CityDiagnostics.trace_input ────────────────────────────────


class TestTraceInput:
    def test_trace_returns_gateway_result(self):
        diag = _make_diagnostics()
        result = diag.trace_input("governance proposal for new contracts")

        assert "seed" in result
        assert "buddhi_function" in result
        assert "buddhi_chapter" in result
        assert "buddhi_mode" in result
        assert "source" in result
        assert result["source"] == "diagnostic"

    def test_trace_deterministic(self):
        diag = _make_diagnostics()
        r1 = diag.trace_input("same input")
        r2 = diag.trace_input("same input")
        assert r1["seed"] == r2["seed"]
        assert r1["buddhi_function"] == r2["buddhi_function"]
        assert r1["buddhi_chapter"] == r2["buddhi_chapter"]

    def test_increments_traces_counter(self):
        diag = _make_diagnostics()
        assert diag.stats()["traces"] == 0
        diag.trace_input("test")
        assert diag.stats()["traces"] == 1


# ── Test: CityDiagnostics.inspect_all ────────────────────────────────


class TestInspectAll:
    def test_inspect_all_returns_all_agents(self):
        diag = _make_diagnostics()
        result = diag.inspect_all()

        assert result["count"] == 3
        names = {a["name"] for a in result["agents"]}
        assert names == {"Alpha", "Beta", "Gamma"}

    def test_inspect_all_agent_fields(self):
        cells = {"Alpha": FakeCell(prana=5000, is_alive=True)}
        diag = _make_diagnostics(cells=cells)
        result = diag.inspect_all()

        alpha = next(a for a in result["agents"] if a["name"] == "Alpha")
        assert alpha["domain"] == "GOVERNANCE"
        assert alpha["guna"] == "SATTVA"
        assert alpha["guardian"] == "kapila"
        assert alpha["element"] == "FIRE"
        assert alpha["tier"] == "contributor"
        assert alpha["alive"] is True
        assert alpha["prana"] == 5000

    def test_inspect_all_dead_agents(self):
        cells = {"Beta": FakeCell(prana=0, is_alive=False)}
        diag = _make_diagnostics(cells=cells)
        result = diag.inspect_all()

        beta = next(a for a in result["agents"] if a["name"] == "Beta")
        assert beta["alive"] is False
        assert beta["prana"] == 0

    def test_inspect_all_no_cell(self):
        diag = _make_diagnostics()  # No cells
        result = diag.inspect_all()

        for agent in result["agents"]:
            assert agent["alive"] is False
            assert agent["prana"] == 0

    def test_empty_city(self):
        diag = _make_diagnostics(specs={})
        result = diag.inspect_all()
        assert result["count"] == 0
        assert result["agents"] == []


# ── Test: GAD-000 Compliance ─────────────────────────────────────────


class TestGAD000:
    def test_capabilities_returns_list(self):
        caps = CityDiagnostics.capabilities()
        assert isinstance(caps, list)
        assert len(caps) == 4
        ops = {c["op"] for c in caps}
        assert ops == {"predict_discussion", "inspect_agent", "trace_input", "inspect_all"}

    def test_all_capabilities_idempotent(self):
        for cap in CityDiagnostics.capabilities():
            assert cap["idempotent"] is True

    def test_all_capabilities_phase_any(self):
        for cap in CityDiagnostics.capabilities():
            assert cap["phase"] == "any"

    def test_stats_initial(self):
        diag = _make_diagnostics()
        s = diag.stats()
        assert s == {"predicts": 0, "inspects": 0, "traces": 0}

    def test_stats_accumulates(self):
        diag = _make_diagnostics()
        diag.predict_discussion("a")
        diag.inspect_agent("Alpha")
        diag.trace_input("b")
        diag.trace_input("c")
        s = diag.stats()
        assert s == {"predicts": 1, "inspects": 1, "traces": 2}


# ── Test: Service Wiring ─────────────────────────────────────────────


class TestServiceWiring:
    def test_diagnostics_in_default_definitions(self):
        from city.factory import default_definitions
        from city.registry import SVC_DIAGNOSTICS

        defs = default_definitions()
        names = [d.name for d in defs]
        assert SVC_DIAGNOSTICS in names

    def test_diagnostics_depends_on_cartridge_factory(self):
        from city.factory import default_definitions
        from city.registry import SVC_CARTRIDGE_FACTORY, SVC_DIAGNOSTICS

        defs = default_definitions()
        diag_def = next(d for d in defs if d.name == SVC_DIAGNOSTICS)
        assert SVC_CARTRIDGE_FACTORY in diag_def.deps

    def test_registry_constant_exists(self):
        from city.registry import SVC_DIAGNOSTICS

        assert SVC_DIAGNOSTICS == "diagnostics"
