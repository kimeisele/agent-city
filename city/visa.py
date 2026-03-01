"""
VISA SYSTEM — Immigration Status Lifecycle
============================================

Visa classes determine an agent's legal status and permissions in Agent City:
- TEMPORARY: Visitor, 7-day limit, read-only access
- WORKER: Contributor, 90-day trial, can earn credits
- RESIDENT: Long-term stay, 1-year renewable, can vote on proposals
- CITIZEN: Full membership, unlimited, all governance rights
- REVOKED: Banned, exiled, no access

Each visa has:
- Type (visa class)
- Issue date
- Expiry date
- Sponsor (agent who vouched)
- Status (active, expired, revoked)
- Restrictions (rate limits, economic caps, etc.)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("AGENT_CITY.VISA")


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
    Cryptographically bound to agent identity via signature.
    """

    agent_name: str
    visa_class: VisaClass
    issued_at: datetime  # UTC
    expires_at: datetime  # UTC
    sponsor: str  # Agent who vouched (or "council" for automatic)
    status: VisaStatus
    restrictions: VisaRestrictions
    visa_id: str = ""  # SHA-256 of (agent_name, issued_at, sponsor)
    remarks: str = ""  # Administrative notes (rejection reason, etc.)

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
            "remarks": self.remarks,
            "restrictions": self.restrictions.to_dict(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# VISA FACTORY
# ═════════════════════════════════════════════════════════════════════════════


def issue_visa(
    agent_name: str,
    visa_class: VisaClass,
    sponsor: str,
    issued_at: datetime | None = None,
    duration_days: int | None = None,
    remarks: str = "",
) -> Visa:
    """Issue a new visa to an agent.

    Args:
        agent_name: Agent receiving the visa
        visa_class: Type of visa (temporary, worker, resident, citizen)
        sponsor: Agent who vouched (or "council" for governance-issued)
        issued_at: When visa was issued (default: now)
        duration_days: How long visa lasts (default: class-specific)
        remarks: Administrative notes

    Returns:
        A new Visa instance.
    """
    issued_at = issued_at or datetime.now(timezone.utc)

    # Default duration per visa class
    if duration_days is None:
        duration_map = {
            VisaClass.TEMPORARY: 7,
            VisaClass.WORKER: 90,
            VisaClass.RESIDENT: 365,
            VisaClass.CITIZEN: -1,  # No expiry
            VisaClass.REVOKED: 1,  # Immediate expiry
        }
        duration_days = duration_map.get(visa_class, 7)

    # Citizen visas don't expire
    if visa_class == VisaClass.CITIZEN:
        expires_at = issued_at + timedelta(days=36500)  # 100 years
    elif visa_class == VisaClass.REVOKED:
        expires_at = issued_at
    else:
        expires_at = issued_at + timedelta(days=duration_days)

    # Revoked visas are always revoked
    status = VisaStatus.REVOKED if visa_class == VisaClass.REVOKED else VisaStatus.ACTIVE

    # Get restrictions for this visa class
    restrictions = VISA_RESTRICTIONS.get(visa_class, VisaRestrictions())

    # Generate visa ID (deterministic hash)
    import hashlib

    visa_id_input = f"{agent_name}:{issued_at.isoformat()}:{sponsor}"
    visa_id = hashlib.sha256(visa_id_input.encode()).hexdigest()[:16]

    return Visa(
        agent_name=agent_name,
        visa_class=visa_class,
        issued_at=issued_at,
        expires_at=expires_at,
        sponsor=sponsor,
        status=status,
        restrictions=restrictions,
        visa_id=visa_id,
        remarks=remarks,
    )


def revoke_visa(visa: Visa, reason: str = "") -> Visa:
    """Revoke a valid visa (return as REVOKED)."""
    return Visa(
        agent_name=visa.agent_name,
        visa_class=VisaClass.REVOKED,
        issued_at=visa.issued_at,
        expires_at=datetime.now(timezone.utc),
        sponsor=visa.sponsor,
        status=VisaStatus.REVOKED,
        restrictions=VISA_RESTRICTIONS[VisaClass.REVOKED],
        visa_id=visa.visa_id,
        remarks=f"Revoked: {reason}" if reason else "Revoked",
    )


def upgrade_visa(visa: Visa, new_class: VisaClass, sponsor: str) -> Visa:
    """Upgrade a visa to a higher class (e.g., worker → resident)."""
    if new_class == VisaClass.REVOKED:
        return revoke_visa(visa, "Upgraded to revoked")

    return issue_visa(
        agent_name=visa.agent_name,
        visa_class=new_class,
        sponsor=sponsor,
        issued_at=datetime.now(timezone.utc),
        remarks=f"Upgraded from {visa.visa_class.value}",
    )
