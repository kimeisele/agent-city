"""Tests for MissionRouter — capability gates, scoring, routing, authorization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helper: Build AgentSpec dicts for testing ────────────────────────


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


def _mission(mission_id, name="Test Mission", description="test"):
    """Build a mock SankalpaMission."""
    m = MagicMock()
    m.id = mission_id
    m.name = name
    m.description = description
    return m


# ── Capability Gate Tests ────────────────────────────────────────────


class TestCapabilityGate(unittest.TestCase):
    """Hard gate: tier + required capabilities. No bypass."""

    def test_observer_blocked_from_execute(self):
        """Observer tier agent → exec_ mission = HARD BLOCK."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(capability_tier="observer", capabilities=["observe", "monitor"])
        req = get_requirement("exec_test_123")
        self.assertFalse(check_capability_gate(spec, req))

    def test_verified_can_execute(self):
        """Verified tier agent with execute cap → exec_ mission = PASS."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(
            capability_tier="verified",
            capabilities=["execute", "dispatch", "enforce"],
        )
        req = get_requirement("exec_test_123")
        self.assertTrue(check_capability_gate(spec, req))

    def test_missing_required_cap_blocked(self):
        """Agent without 'audit' cap → audit_ mission = BLOCKED."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(
            capability_tier="sovereign",
            capabilities=["execute", "govern", "sign"],
        )
        req = get_requirement("audit_chain_42")
        self.assertFalse(check_capability_gate(spec, req))

    def test_sovereign_passes_all(self):
        """Sovereign tier with all caps passes any gate."""
        from city.mission_router import check_capability_gate, get_requirement

        all_caps = [
            "validate",
            "audit",
            "propose",
            "execute",
            "observe",
            "relay",
            "govern",
            "sign",
        ]
        spec = _spec(capability_tier="sovereign", capabilities=all_caps)

        for prefix in ["heal_", "audit_", "improve_", "issue_", "exec_", "signal_", "fed_"]:
            req = get_requirement(f"{prefix}test")
            self.assertTrue(
                check_capability_gate(spec, req),
                f"Sovereign should pass gate for {prefix}",
            )

    def test_signal_missions_low_bar(self):
        """Signal missions only need 'observe' + observer tier."""
        from city.mission_router import check_capability_gate, get_requirement

        spec = _spec(
            capability_tier="observer",
            capabilities=["observe", "monitor", "report"],
        )
        req = get_requirement("signal_test_abc")
        self.assertTrue(check_capability_gate(spec, req))


# ── Scoring Tests ────────────────────────────────────────────────────


class TestScoring(unittest.TestCase):
    """Score agents for missions. 4 dimensions, 0.0–1.0."""

    def test_domain_alignment_boost(self):
        """ENGINEERING agent scores higher on exec_ missions than RESEARCH agent."""
        from city.mission_router import get_requirement, score_agent_for_mission

        req = get_requirement("exec_test")
        eng = _spec(
            domain="ENGINEERING", capabilities=["execute", "dispatch"], capability_tier="verified"
        )
        res = _spec(
            domain="RESEARCH", capabilities=["execute", "dispatch"], capability_tier="verified"
        )

        eng_score = score_agent_for_mission(eng, "exec_test", req)
        res_score = score_agent_for_mission(res, "exec_test", req)
        self.assertGreater(eng_score, res_score)

    def test_capability_coverage_scoring(self):
        """More preferred caps = higher score."""
        from city.mission_router import get_requirement, score_agent_for_mission

        req = get_requirement("exec_test")
        # exec_ preferred = ["dispatch", "enforce"]
        full = _spec(capabilities=["execute", "dispatch", "enforce"], capability_tier="verified")
        partial = _spec(capabilities=["execute", "dispatch"], capability_tier="verified")
        minimal = _spec(capabilities=["execute"], capability_tier="verified")

        full_score = score_agent_for_mission(full, "exec_test", req)
        partial_score = score_agent_for_mission(partial, "exec_test", req)
        minimal_score = score_agent_for_mission(minimal, "exec_test", req)

        self.assertGreater(full_score, partial_score)
        self.assertGreater(partial_score, minimal_score)

    def test_qos_bonus(self):
        """SATTVA agent gets slight edge over RAJAS (same caps, same domain)."""
        from city.mission_router import get_requirement, score_agent_for_mission

        req = get_requirement("signal_test")
        sattva = _spec(
            domain="DISCOVERY",
            capabilities=["observe", "relay"],
            capability_tier="observer",
            capability_protocol="parse",
            guna="SATTVA",
        )
        rajas = _spec(
            domain="DISCOVERY",
            capabilities=["observe", "relay"],
            capability_tier="observer",
            capability_protocol="parse",
            guna="RAJAS",
        )

        sattva_score = score_agent_for_mission(sattva, "signal_test", req)
        rajas_score = score_agent_for_mission(rajas, "signal_test", req)
        self.assertGreater(sattva_score, rajas_score)

    def test_best_agent_selected(self):
        """With 3 agents, highest scorer wins."""
        from city.mission_router import route_mission

        mission = _mission("improve_quality_42")
        specs = {
            "bad": _spec(
                name="bad",
                domain="DISCOVERY",
                capabilities=["propose"],
                capability_tier="contributor",
            ),
            "good": _spec(
                name="good",
                domain="ENGINEERING",
                capabilities=["propose", "review", "modify"],
                capability_tier="contributor",
                capability_protocol="infer",
            ),
            "mid": _spec(
                name="mid",
                domain="ENGINEERING",
                capabilities=["propose", "review"],
                capability_tier="contributor",
            ),
        }
        active = {"bad", "good", "mid"}

        result = route_mission(mission, specs, active)
        self.assertEqual(result["agent_name"], "good")
        self.assertFalse(result["blocked"])


# ── Routing Tests ────────────────────────────────────────────────────


class TestRouting(unittest.TestCase):
    """End-to-end routing: gate → score → select."""

    def test_route_returns_best_fit(self):
        """route_mission returns highest-scoring active agent."""
        from city.mission_router import route_mission

        mission = _mission("signal_infra_abc")
        specs = {
            "a": _spec(
                name="a",
                domain="DISCOVERY",
                capabilities=["observe", "relay", "communicate"],
                capability_tier="observer",
                capability_protocol="parse",
                guna="SATTVA",
            ),
            "b": _spec(
                name="b",
                domain="ENGINEERING",
                capabilities=["observe"],
                capability_tier="observer",
            ),
        }

        result = route_mission(mission, specs, {"a", "b"})
        self.assertEqual(result["agent_name"], "a")
        self.assertGreater(result["score"], 0.0)
        self.assertEqual(result["candidates_count"], 2)

    def test_route_blocked_when_all_fail_gate(self):
        """Returns blocked=True when no agent qualifies."""
        from city.mission_router import route_mission

        mission = _mission("exec_deploy_99")
        specs = {
            "obs1": _spec(name="obs1", capability_tier="observer", capabilities=["observe"]),
            "obs2": _spec(name="obs2", capability_tier="observer", capabilities=["observe"]),
        }

        result = route_mission(mission, specs, {"obs1", "obs2"})
        self.assertTrue(result["blocked"])
        self.assertIsNone(result["agent_name"])
        self.assertEqual(result["blocked_count"], 2)
        self.assertEqual(result["candidates_count"], 0)

    def test_inactive_agents_excluded(self):
        """Agents not in active_agents set are skipped."""
        from city.mission_router import route_mission

        mission = _mission("signal_test_1")
        specs = {
            "active": _spec(name="active", capabilities=["observe"], capability_tier="observer"),
            "dead": _spec(name="dead", capabilities=["observe"], capability_tier="observer"),
        }

        # Only "active" is in the active set
        result = route_mission(mission, specs, {"active"})
        self.assertEqual(result["agent_name"], "active")
        self.assertEqual(result["candidates_count"], 1)

    def test_unknown_prefix_uses_default(self):
        """Unrecognized mission prefix → default requirement (propose + observer)."""
        from city.mission_router import get_requirement

        req = get_requirement("custom_xyz_42")
        self.assertEqual(req["required"], ["propose"])
        self.assertEqual(req["min_tier"], "observer")


# ── Authorization Tests (ZERO BYPASS) ────────────────────────────────


class TestAuthorization(unittest.TestCase):
    """Universal authorization gate for dedicated processors."""

    def test_authorize_true_when_agent_qualifies(self):
        """authorize_mission True when at least one agent passes gate."""
        from city.mission_router import authorize_mission

        specs = {
            "agent_a": _spec(
                name="agent_a",
                capability_tier="verified",
                capabilities=["execute", "dispatch"],
            ),
        }
        self.assertTrue(authorize_mission("exec_test", specs, {"agent_a"}))

    def test_authorize_false_when_none_qualify(self):
        """authorize_mission False when all agents fail gate."""
        from city.mission_router import authorize_mission

        specs = {
            "obs": _spec(name="obs", capability_tier="observer", capabilities=["observe"]),
        }
        self.assertFalse(authorize_mission("exec_test", specs, {"obs"}))

    def test_exec_mission_blocked_without_verified_tier(self):
        """exec_ mission with only contributor agents → blocked (need verified)."""
        from city.mission_router import authorize_mission

        specs = {
            "contrib": _spec(
                name="contrib",
                capability_tier="contributor",
                capabilities=["execute", "propose", "review"],
            ),
        }
        # contributor has execute cap BUT tier is too low (need verified)
        self.assertFalse(authorize_mission("exec_test", specs, {"contrib"}))


if __name__ == "__main__":
    unittest.main()
