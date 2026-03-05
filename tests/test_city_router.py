"""
Tests for CityRouter — O(1) Agent Routing via Mahamantra Lotus (Schritt 4).

Covers:
- Register/remove agents
- O(1) capability, domain, tier, protocol, guardian lookups
- Compound queries (agents_for_requirement)
- Tier hierarchy (min_tier includes higher tiers)
- Re-registration overwrites cleanly
- Empty results
- Integration with mission_router.route_mission(router=...)
- Stats tracking

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.router import CityRouter


def _spec(
    *,
    caps: list[str] | None = None,
    domain: str = "ENGINEERING",
    tier: str = "contributor",
    protocol: str = "infer",
    guardian: str = "prahlada",
) -> dict:
    """Build minimal AgentSpec dict for CityRouter tests."""
    return {
        "capabilities": caps or ["execute", "dispatch", "propose"],
        "domain": domain,
        "capability_tier": tier,
        "capability_protocol": protocol,
        "guardian": guardian,
    }


# ── Basic Registration ───────────────────────────────────────────────


class TestRegistration:
    def test_register_single(self):
        r = CityRouter()
        r.register("agent_a", _spec())
        assert "agent_a" in r.agents_with_capability("execute")
        assert r.stats()["registered_agents"] == 1

    def test_register_multiple(self):
        r = CityRouter()
        r.register("a", _spec(caps=["execute"]))
        r.register("b", _spec(caps=["observe", "monitor"]))
        r.register("c", _spec(caps=["execute", "observe"]))
        assert r.agents_with_capability("execute") == frozenset({"a", "c"})
        assert r.agents_with_capability("observe") == frozenset({"b", "c"})
        assert r.agents_with_capability("monitor") == frozenset({"b"})

    def test_remove(self):
        r = CityRouter()
        r.register("a", _spec(caps=["execute"]))
        r.register("b", _spec(caps=["execute"]))
        r.remove("a")
        assert r.agents_with_capability("execute") == frozenset({"b"})
        assert r.stats()["registered_agents"] == 1

    def test_remove_nonexistent(self):
        r = CityRouter()
        r.remove("ghost")  # should not raise

    def test_re_register_overwrites(self):
        r = CityRouter()
        r.register("a", _spec(caps=["execute"], domain="ENGINEERING"))
        r.register("a", _spec(caps=["observe"], domain="DISCOVERY"))
        assert r.agents_with_capability("execute") == frozenset()
        assert r.agents_with_capability("observe") == frozenset({"a"})
        assert r.agents_in_domain("ENGINEERING") == frozenset()
        assert r.agents_in_domain("DISCOVERY") == frozenset({"a"})


# ── Index Queries ────────────────────────────────────────────────────


class TestIndexQueries:
    def test_capability_lookup(self):
        r = CityRouter()
        r.register("a", _spec(caps=["execute", "dispatch"]))
        assert "a" in r.agents_with_capability("execute")
        assert "a" in r.agents_with_capability("dispatch")
        assert "a" not in r.agents_with_capability("observe")

    def test_domain_lookup(self):
        r = CityRouter()
        r.register("a", _spec(domain="ENGINEERING"))
        r.register("b", _spec(domain="DISCOVERY"))
        assert r.agents_in_domain("ENGINEERING") == frozenset({"a"})
        assert r.agents_in_domain("DISCOVERY") == frozenset({"b"})

    def test_tier_lookup(self):
        r = CityRouter()
        r.register("a", _spec(tier="observer"))
        r.register("b", _spec(tier="contributor"))
        r.register("c", _spec(tier="verified"))
        assert r.agents_at_tier("contributor") == frozenset({"b"})
        assert r.agents_at_tier("verified") == frozenset({"c"})

    def test_protocol_lookup(self):
        r = CityRouter()
        r.register("a", _spec(protocol="parse"))
        r.register("b", _spec(protocol="validate"))
        assert r.agents_with_protocol("parse") == frozenset({"a"})

    def test_guardian_lookup(self):
        r = CityRouter()
        r.register("a", _spec(guardian="brahma"))
        r.register("b", _spec(guardian="vishnu"))
        assert r.agents_with_guardian("brahma") == frozenset({"a"})

    def test_empty_lookup(self):
        r = CityRouter()
        assert r.agents_with_capability("nonexistent") == frozenset()
        assert r.agents_in_domain("NOWHERE") == frozenset()


# ── Compound Queries ─────────────────────────────────────────────────


class TestCompoundQueries:
    def test_single_cap_requirement(self):
        r = CityRouter()
        r.register("a", _spec(caps=["execute"], tier="contributor"))
        r.register("b", _spec(caps=["observe"], tier="contributor"))
        result = r.agents_for_requirement(["execute"], min_tier="contributor")
        assert result == frozenset({"a"})

    def test_multi_cap_intersection(self):
        r = CityRouter()
        r.register("a", _spec(caps=["execute", "dispatch"]))
        r.register("b", _spec(caps=["execute"]))
        r.register("c", _spec(caps=["dispatch"]))
        result = r.agents_for_requirement(["execute", "dispatch"])
        assert result == frozenset({"a"})

    def test_tier_hierarchy(self):
        r = CityRouter()
        r.register("obs", _spec(caps=["observe"], tier="observer"))
        r.register("con", _spec(caps=["observe"], tier="contributor"))
        r.register("ver", _spec(caps=["observe"], tier="verified"))
        r.register("sov", _spec(caps=["observe"], tier="sovereign"))
        # min_tier=contributor → excludes observer
        result = r.agents_for_requirement(["observe"], min_tier="contributor")
        assert result == frozenset({"con", "ver", "sov"})
        # min_tier=verified → excludes observer + contributor
        result = r.agents_for_requirement(["observe"], min_tier="verified")
        assert result == frozenset({"ver", "sov"})

    def test_no_caps_returns_all(self):
        r = CityRouter()
        r.register("a", _spec(tier="contributor"))
        r.register("b", _spec(tier="verified"))
        result = r.agents_for_requirement([], min_tier="contributor")
        assert "a" in result and "b" in result

    def test_empty_when_no_match(self):
        r = CityRouter()
        r.register("a", _spec(caps=["observe"], tier="observer"))
        result = r.agents_for_requirement(["execute"], min_tier="verified")
        assert result == frozenset()

    def test_domain_soft_filter(self):
        r = CityRouter()
        r.register("eng", _spec(caps=["execute"], domain="ENGINEERING"))
        r.register("disc", _spec(caps=["execute"], domain="DISCOVERY"))
        # Domain filter is soft — if domain match exists, prefer it
        result = r.agents_for_requirement(["execute"], domain="ENGINEERING")
        assert result == frozenset({"eng"})
        # But if no domain match, return all
        result = r.agents_for_requirement(["execute"], domain="GOVERNANCE")
        assert frozenset({"eng", "disc"}).issubset(result)


# ── Mission Router Integration ───────────────────────────────────────


class TestMissionRouterIntegration:
    def test_route_mission_with_router(self):
        from city.mission_router import route_mission

        r = CityRouter()
        specs = {
            "eng1": _spec(caps=["execute", "dispatch"], tier="verified", domain="ENGINEERING"),
            "disc1": _spec(caps=["observe", "report"], tier="contributor", domain="DISCOVERY"),
        }
        for name, spec in specs.items():
            r.register(name, spec)

        class FakeMission:
            id = "exec_fix_bug"

        result = route_mission(
            FakeMission(),
            specs,
            active_agents={"eng1", "disc1"},
            router=r,
        )
        assert result["agent_name"] == "eng1"
        assert result["score"] > 0
        assert not result["blocked"]

    def test_route_mission_blocked_with_router(self):
        from city.mission_router import route_mission

        r = CityRouter()
        r.register("obs", _spec(caps=["observe"], tier="observer"))

        class FakeMission:
            id = "exec_deploy"

        result = route_mission(
            FakeMission(),
            {"obs": _spec(caps=["observe"], tier="observer")},
            active_agents={"obs"},
            router=r,
        )
        assert result["blocked"]

    def test_route_mission_without_router_fallback(self):
        from city.mission_router import route_mission

        specs = {
            "a": _spec(caps=["execute", "dispatch"], tier="verified"),
        }
        result = route_mission(
            type("M", (), {"id": "exec_test"})(),
            specs,
            active_agents={"a"},
            router=None,  # no router → old O(n) path
        )
        assert result["agent_name"] == "a"


# ── Stats ────────────────────────────────────────────────────────────


class TestStats:
    def test_stats_tracking(self):
        r = CityRouter()
        r.register("a", _spec())
        r.register("b", _spec())
        r.remove("a")
        _ = r.agents_with_capability("execute")
        s = r.stats()
        assert s["registered_agents"] == 1
        assert s["total_registrations"] == 2
        assert s["total_removals"] == 1
        assert s["total_queries"] >= 1
        assert "lotus_stats" in s
        assert s["lotus_stats"]["mechanism"] == "Lotus O(1) / Sudarshana"
