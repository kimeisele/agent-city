"""
MEMBRANE — Explicit authority cut for external ingress.

Normalizes transport-specific input at the edge before it touches
CityNadi / gateway_queue. This is the narrow cut where "outside"
becomes "inside".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from city.access import AccessClass
from city.claims import ClaimLevel


class IngressSurface(str, Enum):
    LOCAL = "local"
    GITHUB_DISCUSSION = "github_discussion"
    GITHUB_WEBHOOK = "github_webhook"
    MOLTBOOK_DM = "moltbook_dm"
    MOLTBOOK_MENTION = "moltbook_mention"
    MOLTBOOK_REPLY = "moltbook_reply"
    MOLTBOOK_FEED = "moltbook_feed"
    SUBMOLT_SIGNAL = "submolt_signal"
    FEDERATION = "federation"


class AuthRoute(str, Enum):
    LOCAL = "local"
    GITHUB_HANDLE = "github_handle"
    HMAC = "hmac"
    PLATFORM_DM = "platform_dm"
    PUBLIC_FEED = "public_feed"
    FEDERATION_NADI = "federation_nadi"


@dataclass(frozen=True)
class AuthorityDescriptor:
    source_class: str
    access_class: AccessClass
    claim_floor: ClaimLevel
    auth_route: AuthRoute


@dataclass(frozen=True)
class AuthorityRequirement:
    access_class: AccessClass = AccessClass.OBSERVER
    claim_level: ClaimLevel = ClaimLevel.DISCOVERED


@dataclass(frozen=True)
class ResolvedAuthority:
    source_class: str
    access_class: AccessClass
    claim_level: ClaimLevel
    auth_route: str


AUTHORITY_MAP: dict[IngressSurface, AuthorityDescriptor] = {
    IngressSurface.LOCAL: AuthorityDescriptor(
        "local",
        AccessClass.SOVEREIGN,
        ClaimLevel.CRYPTO_VERIFIED,
        AuthRoute.LOCAL,
    ),
    IngressSurface.GITHUB_DISCUSSION: AuthorityDescriptor(
        "external",
        AccessClass.OBSERVER,
        ClaimLevel.DISCOVERED,
        AuthRoute.GITHUB_HANDLE,
    ),
    IngressSurface.GITHUB_WEBHOOK: AuthorityDescriptor(
        "ci",
        AccessClass.OPERATOR,
        ClaimLevel.CRYPTO_VERIFIED,
        AuthRoute.HMAC,
    ),
    IngressSurface.MOLTBOOK_DM: AuthorityDescriptor(
        "agent",
        AccessClass.OBSERVER,
        ClaimLevel.DISCOVERED,
        AuthRoute.PLATFORM_DM,
    ),
    IngressSurface.MOLTBOOK_MENTION: AuthorityDescriptor(
        "external",
        AccessClass.OBSERVER,
        ClaimLevel.DISCOVERED,
        AuthRoute.PUBLIC_FEED,
    ),
    IngressSurface.MOLTBOOK_REPLY: AuthorityDescriptor(
        "external",
        AccessClass.OBSERVER,
        ClaimLevel.DISCOVERED,
        AuthRoute.PUBLIC_FEED,
    ),
    IngressSurface.MOLTBOOK_FEED: AuthorityDescriptor(
        "external",
        AccessClass.OBSERVER,
        ClaimLevel.DISCOVERED,
        AuthRoute.PUBLIC_FEED,
    ),
    IngressSurface.SUBMOLT_SIGNAL: AuthorityDescriptor(
        "external",
        AccessClass.OBSERVER,
        ClaimLevel.DISCOVERED,
        AuthRoute.PUBLIC_FEED,
    ),
    IngressSurface.FEDERATION: AuthorityDescriptor(
        "agent",
        AccessClass.STEWARD,
        ClaimLevel.CRYPTO_VERIFIED,
        AuthRoute.FEDERATION_NADI,
    ),
}


@dataclass(frozen=True)
class IngressEnvelope:
    surface: IngressSurface
    source: str
    text: str
    authority: AuthorityDescriptor
    metadata: dict[str, Any] = field(default_factory=dict)

    def membrane_snapshot(self) -> dict[str, Any]:
        return {
            "surface": self.surface.value,
            "intent_signal": f"ingress:{self.surface.value}",
            "source_class": self.authority.source_class,
            "access_class": self.authority.access_class.value,
            "claim_floor": int(self.authority.claim_floor),
            "auth_route": self.authority.auth_route.value,
        }

    def to_city_intent(self):
        from city.reactor import CityIntent

        priority = "high" if self.surface in {
            IngressSurface.LOCAL,
            IngressSurface.GITHUB_WEBHOOK,
            IngressSurface.MOLTBOOK_DM,
        } else "normal"
        return CityIntent(
            signal=f"ingress:{self.surface.value}",
            priority=priority,
            context={
                "source": self.source,
                "text": self.text,
                **self.metadata,
                "membrane": self.membrane_snapshot(),
            },
        )

    def to_queue_item(self) -> dict[str, Any]:
        item = {
            "source": self.source,
            "text": self.text,
            **self.metadata,
        }
        item["membrane"] = self.membrane_snapshot()
        return item


def _coerce_access_class(value: Any) -> AccessClass:
    if isinstance(value, AccessClass):
        return value
    try:
        return AccessClass(str(value))
    except ValueError:
        return AccessClass.OBSERVER


def _coerce_claim_level(value: Any) -> ClaimLevel:
    if isinstance(value, ClaimLevel):
        return value
    try:
        return ClaimLevel(int(value))
    except (TypeError, ValueError):
        return ClaimLevel.DISCOVERED


def requirement_for_auth_tier(auth_tier: Any) -> AuthorityRequirement:
    tier = str(getattr(auth_tier, "value", auth_tier) or "citizen").lower()
    if tier == "public":
        return AuthorityRequirement()
    if tier == "operator":
        return AuthorityRequirement(access_class=AccessClass.OPERATOR)
    return AuthorityRequirement(claim_level=ClaimLevel.SELF_CLAIMED)


def resolve_authority(
    ctx: Any,
    *,
    membrane: dict[str, Any] | None = None,
    author: str = "",
) -> ResolvedAuthority:
    membrane = membrane or {}
    access_class = _coerce_access_class(
        membrane.get("access_class", AccessClass.OBSERVER)
    )
    claim_level = _coerce_claim_level(
        membrane.get("claim_floor", ClaimLevel.DISCOVERED)
    )
    pokedex = getattr(ctx, "pokedex", None)

    if author and pokedex is not None:
        operator = pokedex.get_operator(author)
        if operator is not None:
            operator_access = _coerce_access_class(operator.get("access_class"))
            if operator_access.level > access_class.level:
                access_class = operator_access

        agent = pokedex.get(author)
        if agent is not None and agent.get("status") in {"citizen", "active"}:
            agent_claim = max(
                int(claim_level),
                int(ClaimLevel.SELF_CLAIMED),
                int(pokedex.get_claim_level(author)),
            )
            claim_level = ClaimLevel(agent_claim)

    return ResolvedAuthority(
        source_class=str(membrane.get("source_class", "external")),
        access_class=access_class,
        claim_level=claim_level,
        auth_route=str(membrane.get("auth_route", "legacy")),
    )


def authorize_ingress(
    ctx: Any,
    *,
    membrane: dict[str, Any] | None = None,
    author: str = "",
    requirement: AuthorityRequirement | None = None,
) -> tuple[bool, str]:
    requirement = requirement or AuthorityRequirement()
    authority = resolve_authority(ctx, membrane=membrane, author=author)

    if authority.access_class.level < requirement.access_class.level:
        return False, f"access<{requirement.access_class.value}"
    if int(authority.claim_level) < int(requirement.claim_level):
        return False, f"claim<{requirement.claim_level.name.lower()}"
    return True, "ok"


def internal_membrane_snapshot(
    *,
    source_class: str = "local",
    access_class: AccessClass = AccessClass.SOVEREIGN,
    claim_level: ClaimLevel = ClaimLevel.CRYPTO_VERIFIED,
    auth_route: AuthRoute | str = AuthRoute.LOCAL,
) -> dict[str, Any]:
    route = auth_route.value if isinstance(auth_route, AuthRoute) else str(auth_route)
    return {
        "surface": IngressSurface.LOCAL.value,
        "intent_signal": f"ingress:{IngressSurface.LOCAL.value}",
        "source_class": source_class,
        "access_class": access_class.value,
        "claim_floor": int(claim_level),
        "auth_route": route,
    }


def build_ingress_envelope(surface: IngressSurface, item: dict[str, Any]) -> IngressEnvelope:
    authority = AUTHORITY_MAP[surface]
    source = str(item.get("source") or surface.value)
    text = str(item.get("text", ""))
    metadata = {k: v for k, v in item.items() if k not in {"source", "text"}}
    return IngressEnvelope(
        surface=surface,
        source=source,
        text=text,
        authority=authority,
        metadata=metadata,
    )


def wrap_ingress_item(surface: IngressSurface, item: dict[str, Any]) -> dict[str, Any]:
    return build_ingress_envelope(surface, item).to_queue_item()


def queue_item(ctx: Any, item: dict[str, Any]) -> None:
    source = item.get("source", "unknown")
    text = item.get("text", "")
    city_nadi = getattr(ctx, "city_nadi", None) or getattr(ctx, "_city_nadi", None)
    gateway_queue = getattr(ctx, "gateway_queue", None)
    if gateway_queue is None:
        gateway_queue = getattr(ctx, "_gateway_queue", None)
    extra_payload = {
        k: v
        for k, v in item.items()
        if k not in {
            "source",
            "text",
            "conversation_id",
            "from_agent",
            "post_id",
            "code_signals",
            "discussion_number",
            "discussion_title",
            "direct_agent",
            "agent_name",
        }
    }
    if city_nadi is not None:
        city_nadi.enqueue(
            source=source,
            text=text,
            conversation_id=item.get("conversation_id", ""),
            from_agent=item.get("from_agent", ""),
            post_id=item.get("post_id", ""),
            code_signals=item.get("code_signals"),
            discussion_number=item.get("discussion_number", 0),
            discussion_title=item.get("discussion_title", ""),
            direct_agent=item.get("direct_agent", ""),
            agent_name=item.get("agent_name", ""),
            extra_payload=extra_payload,
        )
        return
    if gateway_queue is not None:
        gateway_queue.append(dict(item))


def enqueue_ingress(ctx: Any, surface: IngressSurface, item: dict[str, Any]) -> None:
    queue_item(ctx, wrap_ingress_item(surface, item))