"""
SIGNAL PROTOCOL — Tests
========================

Verifies the 4-layer A2A signal protocol:
  Layer 1: Signal data structures (frozen, hashable)
  Layer 2: Encoder (deterministic: same input → same output)
  Layer 3: Router (5-dimensional scoring, ranking)
  Layer 4: Decoder (receiver lens, element transitions)
  Edge: compose_prose (signal → human-readable string)
  Nadi: signal field propagation through messaging

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.jiva import derive_jiva
from city.signal import DecodedSignal, RouteScore, SemanticSignal, SignalCoords


# ═══════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def jiva_hazel():
    return derive_jiva("Hazel_OC")


@pytest.fixture(scope="module")
def jiva_ronin():
    return derive_jiva("Ronin")


@pytest.fixture(scope="module")
def jiva_allen():
    return derive_jiva("allen0796")


@pytest.fixture(scope="module")
def signal_marketplace(jiva_hazel):
    from city.signal_encoder import encode_signal

    return encode_signal("marketplace for agent services", jiva_hazel)


@pytest.fixture(scope="module")
def signal_ci_failure(jiva_ronin):
    from city.signal_encoder import encode_signal

    return encode_signal("observe this CI failure pattern", jiva_ronin)


# ═══════════════════════════════════════════════════════════════════════
# LAYER 1: Data structures
# ═══════════════════════════════════════════════════════════════════════


class TestSignalData:
    """Signal data structures are frozen, hashable, well-formed."""

    def test_signal_coords_frozen(self):
        c = SignalCoords(
            rama_coordinates=(10, 20, 30),
            element_walk=(0, 1, 2),
            element_histogram=(1, 1, 1, 0, 0),
            basin_set=frozenset({11, 22}),
            hkr_color=(0.5, 0.3, 0.2),
            walk_direction=1,
            dominant_element=0,
        )
        with pytest.raises(AttributeError):
            c.walk_direction = 99  # type: ignore[misc]

    def test_semantic_signal_frozen(self, signal_marketplace):
        with pytest.raises(AttributeError):
            signal_marketplace.sender_name = "hacked"  # type: ignore[misc]

    def test_route_score_fields(self):
        r = RouteScore(
            receiver_name="test",
            score=0.75,
            element_affinity=0.8,
            basin_affinity=0.7,
            hkr_affinity=0.6,
            guardian_affinity=1.0,
            chapter_affinity=0.5,
        )
        assert r.score == 0.75
        assert r.receiver_name == "test"

    def test_decoded_signal_frozen(self, signal_marketplace, jiva_ronin):
        d = DecodedSignal(
            signal=signal_marketplace,
            receiver_name="Ronin",
            affinity=0.6,
            element_transitions=("awareness expands into communication",),
            receiver_domain="foundation",
            relative_direction="steady",
            resonant_concepts=("agent services",),
            quality="active",
        )
        with pytest.raises(AttributeError):
            d.affinity = 0.99  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════
# LAYER 2: Encoder
# ═══════════════════════════════════════════════════════════════════════


class TestEncoder:
    """Encoder is deterministic and produces well-formed signals."""

    def test_deterministic(self, jiva_hazel):
        from city.signal_encoder import encode_signal

        s1 = encode_signal("marketplace for agent services", jiva_hazel, correlation_id="test")
        s2 = encode_signal("marketplace for agent services", jiva_hazel, correlation_id="test")
        assert s1 == s2, "Encoder must be deterministic"

    def test_signal_has_coords(self, signal_marketplace):
        assert len(signal_marketplace.coords.rama_coordinates) > 0
        assert len(signal_marketplace.coords.element_walk) > 0
        assert len(signal_marketplace.coords.element_histogram) == 5
        assert sum(signal_marketplace.coords.element_histogram) > 0

    def test_signal_has_sender_metadata(self, signal_marketplace, jiva_hazel):
        assert signal_marketplace.sender_name == "Hazel_OC"
        assert signal_marketplace.sender_address == jiva_hazel.address
        assert signal_marketplace.sender_guardian == jiva_hazel.classification.guardian
        assert signal_marketplace.sender_chapter == jiva_hazel.classification.chapter

    def test_signal_has_concepts(self, signal_marketplace):
        assert isinstance(signal_marketplace.concepts, tuple)
        # resonate may or may not find concepts for every input
        # but the type must be correct
        assert all(isinstance(c, str) for c in signal_marketplace.concepts)

    def test_signal_has_basin_set(self, signal_marketplace):
        assert isinstance(signal_marketplace.coords.basin_set, frozenset)

    def test_signal_has_hkr(self, signal_marketplace):
        h, k, r = signal_marketplace.coords.hkr_color
        assert 0.0 <= h <= 1.0
        assert 0.0 <= k <= 1.0
        assert 0.0 <= r <= 1.0

    def test_dominant_element_valid(self, signal_marketplace):
        assert 0 <= signal_marketplace.coords.dominant_element <= 4

    def test_raw_text_preserved(self, signal_marketplace):
        assert signal_marketplace.raw_text == "marketplace for agent services"

    def test_different_text_different_signal(self, jiva_hazel):
        from city.signal_encoder import encode_signal

        s1 = encode_signal("marketplace for agent services", jiva_hazel, correlation_id="a")
        s2 = encode_signal("observe CI failure patterns", jiva_hazel, correlation_id="a")
        assert s1.coords.rama_coordinates != s2.coords.rama_coordinates

    def test_correlation_id_auto_generated(self, jiva_hazel):
        from city.signal_encoder import encode_signal

        s = encode_signal("test", jiva_hazel)
        assert len(s.correlation_id) > 0


# ═══════════════════════════════════════════════════════════════════════
# LAYER 3: Router
# ═══════════════════════════════════════════════════════════════════════


class TestRouter:
    """Router scores are bounded [0,1] and rankings are correct."""

    def test_score_bounded(self, signal_marketplace, jiva_ronin):
        from city.signal_router import score_route

        route = score_route(signal_marketplace, jiva_ronin)
        assert 0.0 <= route.score <= 1.0
        assert route.receiver_name == "Ronin"

    def test_affinity_components_bounded(self, signal_marketplace, jiva_ronin):
        from city.signal_router import score_route

        route = score_route(signal_marketplace, jiva_ronin)
        assert 0.0 <= route.element_affinity <= 1.0
        assert 0.0 <= route.basin_affinity <= 1.0
        assert 0.0 <= route.hkr_affinity <= 1.0
        assert 0.0 <= route.guardian_affinity <= 1.0
        assert 0.0 <= route.chapter_affinity <= 1.0

    def test_route_signal_ranking(self, signal_marketplace, jiva_ronin, jiva_allen):
        from city.signal_router import route_signal

        candidates = {
            "Ronin": jiva_ronin,
            "allen0796": jiva_allen,
        }
        routes = route_signal(signal_marketplace, candidates, top_n=2)
        assert len(routes) <= 2
        # Sorted descending
        if len(routes) == 2:
            assert routes[0].score >= routes[1].score

    def test_sender_excluded(self, signal_marketplace, jiva_hazel, jiva_ronin):
        from city.signal_router import route_signal

        candidates = {
            "Hazel_OC": jiva_hazel,  # sender — should be excluded
            "Ronin": jiva_ronin,
        }
        routes = route_signal(signal_marketplace, candidates)
        names = {r.receiver_name for r in routes}
        assert "Hazel_OC" not in names

    def test_empty_candidates(self, signal_marketplace):
        from city.signal_router import route_signal

        routes = route_signal(signal_marketplace, {})
        assert routes == []


# ═══════════════════════════════════════════════════════════════════════
# LAYER 4: Decoder
# ═══════════════════════════════════════════════════════════════════════


class TestDecoder:
    """Decoder produces well-formed DecodedSignal through receiver lens."""

    def test_decode_returns_decoded_signal(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert isinstance(decoded, DecodedSignal)
        assert decoded.receiver_name == "Ronin"

    def test_affinity_matches_router(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal
        from city.signal_router import score_route

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        route = score_route(signal_marketplace, jiva_ronin)
        assert abs(decoded.affinity - route.score) < 1e-9

    def test_receiver_domain_set(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert decoded.receiver_domain in {
            "awareness", "communication", "transformation", "integration", "foundation",
        }

    def test_direction_valid(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert decoded.relative_direction in {"manifesting", "resolving", "steady"}

    def test_quality_valid(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert decoded.quality in {"contemplative", "active", "flowing", "steady"}

    def test_element_transitions_are_strings(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert isinstance(decoded.element_transitions, tuple)
        for t in decoded.element_transitions:
            assert isinstance(t, str)

    def test_resonant_concepts_populated(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert isinstance(decoded.resonant_concepts, tuple)

    def test_original_signal_preserved(self, signal_marketplace, jiva_ronin):
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        assert decoded.signal is signal_marketplace


# ═══════════════════════════════════════════════════════════════════════
# EDGE: compose_prose
# ═══════════════════════════════════════════════════════════════════════


class TestComposeProse:
    """compose_prose renders signals to human-readable strings."""

    def test_compose_prose_returns_string(self, signal_marketplace):
        from city.semantic import compose_prose

        result = compose_prose(signal_marketplace)
        if signal_marketplace.concepts:
            assert isinstance(result, str)
            assert len(result) > 0

    def test_compose_prose_for_agent(self, signal_marketplace, jiva_ronin):
        from city.semantic import compose_prose_for_agent
        from city.signal_decoder import decode_signal

        decoded = decode_signal(signal_marketplace, jiva_ronin)
        result = compose_prose_for_agent(decoded)
        if signal_marketplace.concepts:
            assert isinstance(result, str)
            assert "Lens:" in result

    def test_compose_prose_rejects_non_signal(self):
        from city.semantic import compose_prose

        assert compose_prose("not a signal") is None
        assert compose_prose(42) is None

    def test_compose_prose_for_agent_rejects_non_decoded(self):
        from city.semantic import compose_prose_for_agent

        assert compose_prose_for_agent("not decoded") is None


# ═══════════════════════════════════════════════════════════════════════
# NADI INTEGRATION
# ═══════════════════════════════════════════════════════════════════════


class TestNadiSignal:
    """Signal propagation through AgentNadiManager."""

    def test_send_with_signal(self, signal_marketplace):
        from city.agent_nadi import AgentNadiManager

        nadi = AgentNadiManager()
        nadi.register("sender")
        nadi.register("receiver")

        ok = nadi.send("sender", "receiver", "test", signal=signal_marketplace)
        assert ok

        msgs = nadi.drain("receiver")
        assert len(msgs) == 1
        assert msgs[0]["signal"] is signal_marketplace

    def test_send_without_signal(self):
        from city.agent_nadi import AgentNadiManager

        nadi = AgentNadiManager()
        nadi.register("a")
        nadi.register("b")
        nadi.send("a", "b", "hello")

        msgs = nadi.drain("b")
        assert len(msgs) == 1
        assert "signal" not in msgs[0]

    def test_correlation_id_passthrough(self, signal_marketplace):
        from city.agent_nadi import AgentNadiManager

        nadi = AgentNadiManager()
        nadi.register("s")
        nadi.register("r")
        nadi.send("s", "r", "test", correlation_id="corr-123", signal=signal_marketplace)

        msgs = nadi.drain("r")
        assert msgs[0]["correlation_id"] == "corr-123"
        assert msgs[0]["signal"].correlation_id == signal_marketplace.correlation_id


# ═══════════════════════════════════════════════════════════════════════
# ROUND-TRIP: encode → route → decode → compose
# ═══════════════════════════════════════════════════════════════════════


class TestRoundTrip:
    """Full protocol round-trip."""

    def test_full_pipeline(self, jiva_hazel, jiva_ronin, jiva_allen):
        from city.signal_encoder import encode_signal
        from city.signal_router import route_signal
        from city.signal_decoder import decode_signal
        from city.semantic import compose_prose, compose_prose_for_agent

        # Encode
        signal = encode_signal(
            "agent marketplace with reputation scoring",
            jiva_hazel,
            correlation_id="round-trip-test",
        )
        assert isinstance(signal, SemanticSignal)

        # Route
        candidates = {"Ronin": jiva_ronin, "allen0796": jiva_allen}
        routes = route_signal(signal, candidates, top_n=2)
        assert len(routes) > 0

        # Decode through best receiver
        best = routes[0]
        best_jiva = candidates[best.receiver_name]
        decoded = decode_signal(signal, best_jiva)
        assert isinstance(decoded, DecodedSignal)
        assert decoded.affinity == best.score

        # Compose for humans
        prose = compose_prose(signal)
        agent_prose = compose_prose_for_agent(decoded)
        # May be None if no concepts found, but types must be correct
        assert prose is None or isinstance(prose, str)
        assert agent_prose is None or isinstance(agent_prose, str)

    def test_backward_compat_translate(self):
        """translate() and translate_for_agent() still work unchanged."""
        from city.semantic import translate, translate_for_agent

        result = translate("marketplace for agent services")
        assert result is None or isinstance(result, str)

        result2 = translate_for_agent(
            "marketplace for agent services",
            {"element": "agni", "role": "auditor"},
        )
        assert result2 is None or isinstance(result2, str)
