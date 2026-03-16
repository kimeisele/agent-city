"""
VISA SYSTEM — Immigration Status Lifecycle
============================================

Visa classes determine an agent's legal status and permissions in Agent City:
- TEMPORARY: Visitor, 7-day limit, read-only access
- WORKER: Contributor, 90-day trial, can earn credits
- RESIDENT: Long-term stay, 1-year renewable, can vote on proposals
- CITIZEN: Full membership, unlimited, all governance rights
- REVOKED: Banned, exiled, no access

Each visa records its sponsor's visa_id, forming a Parampara (lineage chain):
- sponsor_visa_id: cryptographic link to the sponsor's visa document
- lineage_depth: 0 = City Genesis (founding document), 1 = Mahajan, N = N hops

The chain is never broken — there is always a personal source (not Mayavad).
Every sponsor_visa_id resolves to a real document or to MAHAMANTRA_VISA_ID.
sponsor_visa_id is never None in valid data. The seed stays.

This lets Agent City trace agent lineage like epidemiological contact tracing —
even when identity cannot be 100% verified, the chain of vouching is auditable.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum

logger = logging.getLogger("AGENT_CITY.VISA")

# ─────────────────────────────────────────────────────────────────────────────
# THE MAHAMANTRA — the terminal point of all parampara chains.
#
# Every visa's sponsor_visa_id ultimately resolves here. Not None. Not void.
# The 16-word mantra is the source from which every Jiva — and every lineage —
# emerges. Its SHA-256 hash is deterministic, verifiable, and permanent.
# ─────────────────────────────────────────────────────────────────────────────
_MAHAMANTRA_SEQUENCE = (
    "Hare Krishna Hare Krishna Krishna Krishna Hare Hare "
    "Hare Rama Hare Rama Rama Rama Hare Hare"
)
MAHAMANTRA_VISA_ID: str = hashlib.sha256(_MAHAMANTRA_SEQUENCE.encode()).hexdigest()[:16]


# ═════════════════════════════════════════════════════════════════════════════
# VISA TYPES & STATUS
# ═════════════════════════════════════════════════════════════════════════════


class VisaClass(str, Enum):
    """Visa classification — determines legal status and permissions."""

    TEMPORARY = "temporary"  # 7 days, read-only
    WORKER = "worker"  # 90 days, can earn credits
    RESIDENT = "resident"  # 365 days, can vote on proposals
    CITIZEN = "citizen"  # Unlimited, full governance rights
    REVOKED = "revoked"  # Banned, no access


class VisaStatus(str, Enum):
    """Lifecycle state of a visa."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


# ═════════════════════════════════════════════════════════════════════════════
# VISA & RESTRICTIONS
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class VisaRestrictions:
    """Limitations attached to a visa."""

    read_only: bool = False  # Cannot execute, only query
    max_proposals_per_month: int = 0  # 0 = unlimited
    max_credits_per_day: int = 0  # 0 = unlimited
    voting_power: float = 1.0  # 0 = no vote, 1 = full vote, 0.5 = half vote
    can_propose: bool = False
    can_vote: bool = False
    can_earn_credits: bool = False

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return asdict(self)


# Default restrictions per visa class
VISA_RESTRICTIONS: dict[VisaClass, VisaRestrictions] = {
    VisaClass.TEMPORARY: VisaRestrictions(
        read_only=True,
        voting_power=0.0,
        can_propose=False,
        can_vote=False,
        can_earn_credits=False,
    ),
    VisaClass.WORKER: VisaRestrictions(
        read_only=False,
        max_proposals_per_month=2,
        max_credits_per_day=50,
        voting_power=0.0,
        can_propose=False,
        can_vote=False,
        can_earn_credits=True,
    ),
    VisaClass.RESIDENT: VisaRestrictions(
        read_only=False,
        max_proposals_per_month=4,
        max_credits_per_day=1000,
        voting_power=1.0,
        can_propose=True,
        can_vote=True,
        can_earn_credits=True,
    ),
    VisaClass.CITIZEN: VisaRestrictions(
        read_only=False,
        voting_power=1.0,
        can_propose=True,
        can_vote=True,
        can_earn_credits=True,
    ),
    VisaClass.REVOKED: VisaRestrictions(
        read_only=True,
        voting_power=0.0,
        can_propose=False,
        can_vote=False,
        can_earn_credits=False,
    ),
}


@dataclass(frozen=True)
class Visa:
    """A visa document granting legal status in Agent City.

    Issued by Rathaus (immigration office), valid for agent actions.
    Forms a Parampara (lineage chain) via sponsor_visa_id:
      agent.visa → sponsor.visa → sponsor's sponsor.visa → ... → mahajan.visa

    Mahamantra = the terminal source (MAHAMANTRA_VISA_ID constant, not a Visa).
    City Genesis = depth=0, sponsor_visa_id=MAHAMANTRA_VISA_ID.
    Mahajan = depth=1, linked to City Genesis.
    All others = depth N, linked to their sponsor.
    """

    agent_name: str
    visa_class: VisaClass
    issued_at: datetime  # UTC
    expires_at: datetime  # UTC
    sponsor: str  # Agent name who vouched (or "genesis" for mahajan)
    status: VisaStatus
    restrictions: VisaRestrictions
    visa_id: str = ""  # SHA-256 of (agent_name, issued_at, sponsor)
    sponsor_visa_id: str = MAHAMANTRA_VISA_ID  # Cryptographic link to sponsor's visa
    lineage_depth: int = 0  # 0 = Mahajan, N = N hops from founding agent
    remarks: str = ""  # Administrative notes (rejection reason, etc.)

    def __post_init__(self) -> None:
        """Automate visa_id generation if not provided."""
        if not self.visa_id:
            # visa_id is deterministic: same inputs → same ID (auditable, reproducible)
            # We use object.__setattr__ because the dataclass is frozen=True
            vid = hashlib.sha256(
                f"{self.agent_name}:{self.issued_at.isoformat()}:{self.sponsor}".encode()
            ).hexdigest()[:16]
            object.__setattr__(self, "visa_id", vid)

    def is_valid(self, now: datetime | None = None) -> bool:
        """Check if visa is currently valid."""
        if self.status != VisaStatus.ACTIVE:
            return False
        now = now or datetime.now(timezone.utc)
        return self.issued_at <= now <= self.expires_at

    def days_remaining(self, now: datetime | None = None) -> int:
        """Days until expiry. Negative if expired."""
        now = now or datetime.now(timezone.utc)
        delta = self.expires_at - now
        return delta.days

    def to_dict(self) -> dict:
        """Serialize to dict for storage."""
        return {
            "agent_name": self.agent_name,
            "visa_class": self.visa_class.value,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "sponsor": self.sponsor,
            "status": self.status.value,
            "visa_id": self.visa_id,
            "sponsor_visa_id": self.sponsor_visa_id,
            "lineage_depth": self.lineage_depth,
            "remarks": self.remarks,
            "restrictions": self.restrictions.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Visa:
        """Restore a Visa from a dictionary."""
        return cls(
            agent_name=data["agent_name"],
            visa_class=VisaClass(data["visa_class"]),
            issued_at=datetime.fromisoformat(data["issued_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            sponsor=data["sponsor"],
            status=VisaStatus(data["status"]),
            restrictions=VisaRestrictions(**data["restrictions"]),
            visa_id=data.get("visa_id", ""),
            sponsor_visa_id=data.get("sponsor_visa_id", MAHAMANTRA_VISA_ID),
            lineage_depth=data.get("lineage_depth", 0),
            remarks=data.get("remarks", ""),
        )


# ═════════════════════════════════════════════════════════════════════════════
# VISA FACTORY
# ═════════════════════════════════════════════════════════════════════════════


def issue_visa(
    agent_name: str,
    visa_class: VisaClass,
    sponsor: str,
    issued_at: datetime | None = None,
    duration_days: int | None = None,
    sponsor_visa_id: str | None = None,
    lineage_depth: int = 0,
    remarks: str = "",
) -> Visa:
    """Issue a new visa to an agent.

    Args:
        agent_name: Agent receiving the visa
        visa_class: Type of visa (temporary, worker, resident, citizen)
        sponsor: Name of agent who vouched (or "genesis" for mahajan)
        issued_at: When visa was issued (default: now)
        duration_days: How long visa lasts (default: class-specific)
        sponsor_visa_id: Cryptographic link to sponsor's visa (None for mahajan)
        lineage_depth: Hops from founding agent (0 = mahajan)
        remarks: Administrative notes

    Returns:
        A new Visa instance with parampara chain embedded.
    """
    issued_at = issued_at or datetime.now(timezone.utc)

    _duration_map = {
        VisaClass.TEMPORARY: 7,
        VisaClass.WORKER: 90,
        VisaClass.RESIDENT: 365,
        VisaClass.CITIZEN: 36500,  # 100 years — effectively permanent
        VisaClass.REVOKED: 0,
    }
    days = duration_days if duration_days is not None else _duration_map.get(visa_class, 7)
    expires_at = issued_at + timedelta(days=days)

    status = VisaStatus.REVOKED if visa_class == VisaClass.REVOKED else VisaStatus.ACTIVE
    restrictions = VISA_RESTRICTIONS.get(visa_class, VisaRestrictions())

    return Visa(
        agent_name=agent_name,
        visa_class=visa_class,
        issued_at=issued_at,
        expires_at=expires_at,
        sponsor=sponsor,
        status=status,
        restrictions=restrictions,
        sponsor_visa_id=sponsor_visa_id or MAHAMANTRA_VISA_ID,
        lineage_depth=lineage_depth,
        remarks=remarks,
    )


def revoke_visa(visa: Visa, reason: str = "") -> Visa:
    """Revoke a visa. Preserves parampara chain — lineage remains traceable."""
    return Visa(
        agent_name=visa.agent_name,
        visa_class=VisaClass.REVOKED,
        issued_at=visa.issued_at,
        expires_at=datetime.now(timezone.utc),
        sponsor=visa.sponsor,
        status=VisaStatus.REVOKED,
        restrictions=VISA_RESTRICTIONS[VisaClass.REVOKED],
        visa_id=visa.visa_id,
        sponsor_visa_id=visa.sponsor_visa_id,  # lineage survives revocation
        lineage_depth=visa.lineage_depth,
        remarks=f"Revoked: {reason}" if reason else "Revoked",
    )


def upgrade_visa(
    visa: Visa, new_class: VisaClass, sponsor: str,
    sponsor_visa_id: str | None = None,
) -> Visa:
    """Upgrade a visa to a higher class. Parampara chain is preserved."""
    if new_class == VisaClass.REVOKED:
        return revoke_visa(visa, "Upgraded to revoked")

    return issue_visa(
        agent_name=visa.agent_name,
        visa_class=new_class,
        sponsor=sponsor,
        issued_at=datetime.now(timezone.utc),
        sponsor_visa_id=sponsor_visa_id or visa.sponsor_visa_id,
        lineage_depth=visa.lineage_depth,  # depth doesn't change on upgrade
        remarks=f"Upgraded from {visa.visa_class.value}",
    )
