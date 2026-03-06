from city.access import AccessClass
from city.claims import ClaimLevel
from city.gateway import CityGateway
from city.membrane import (
    AUTHORITY_MAP,
    IngressSurface,
    build_ingress_envelope,
    enqueue_ingress,
)


def test_membrane_authority_map_is_explicit():
    rule = AUTHORITY_MAP[IngressSurface.GITHUB_DISCUSSION]
    assert rule.source_class == "external"
    assert rule.access_class is AccessClass.OBSERVER
    assert rule.claim_floor == ClaimLevel.DISCOVERED


def test_ingress_envelope_maps_to_city_intent():
    envelope = build_ingress_envelope(
        IngressSurface.MOLTBOOK_DM,
        {"source": "dm", "text": "hello", "from_agent": "alice"},
    )
    intent = envelope.to_city_intent()
    assert intent.signal == "ingress:moltbook_dm"
    assert intent.context["membrane"]["source_class"] == "agent"


def test_enqueue_ingress_stamps_membrane_on_fallback_queue():
    class DummyCtx:
        city_nadi = None
        gateway_queue = []

    ctx = DummyCtx()
    enqueue_ingress(
        ctx,
        IngressSurface.GITHUB_DISCUSSION,
        {
            "source": "discussion",
            "text": "ping",
            "discussion_number": 42,
            "comment_id": "c_1",
        },
    )

    item = ctx.gateway_queue[0]
    assert item["comment_id"] == "c_1"
    assert item["membrane"]["surface"] == "github_discussion"
    assert item["membrane"]["intent_signal"] == "ingress:github_discussion"


def test_gateway_process_prefers_membrane_source_class():
    gateway = CityGateway()
    result = gateway.process(
        "hello",
        source="dm",
        membrane={
            "surface": "moltbook_dm",
            "source_class": "agent",
            "access_class": "observer",
            "claim_floor": 0,
            "auth_route": "platform_dm",
        },
    )
    assert result["source_class"] == "agent"
    assert result["membrane_surface"] == "moltbook_dm"