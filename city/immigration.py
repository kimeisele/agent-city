"""
IMMIGRATION SERVICE — Agent Onboarding & Visa Management
==========================================================

The Rathaus (immigration office) manages:
1. Applications: External agents submit applications to join
2. Review: KYC verification, contract checks, community score
3. Approval: Council votes on citizenship
4. Citizenship: Final visa issuance and onboarding

The complete migration flow:
  External Agent → Application → Review → Council Vote → Citizenship → Welcome

Parampara (lineage) is built into every visa grant:
  new_visa.sponsor_visa_id = sponsor_visa.visa_id
  new_visa.lineage_depth   = sponsor_visa.lineage_depth + 1

Founding agents are Mahajan (lineage_depth=0, no sponsor_visa_id).
Any agent's lineage can be traced back to their Mahajan via parampara().

Uses DHARMA phase for evaluation and contracts for KYC.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from city.visa import Visa, VisaClass, VisaStatus, issue_visa, revoke_visa

logger = logging.getLogger("AGENT_CITY.IMMIGRATION")


# ═════════════════════════════════════════════════════════════════════════════
# APPLICATION LIFECYCLE
# ═════════════════════════════════════════════════════════════════════════════


class ApplicationStatus(str, Enum):
    """Lifecycle of an immigration application."""

    PENDING = "pending"  # Submitted, awaiting review
    UNDER_REVIEW = "under_review"  # Evaluation in progress
    APPROVED = "approved"  # Passed all checks, ready for council vote
    REJECTED = "rejected"  # Failed KYC or contracts
    COUNCIL_PENDING = "council_pending"  # Waiting for council vote
    COUNCIL_APPROVED = "council_approved"  # Council voted yes
    COUNCIL_REJECTED = "council_rejected"  # Council voted no
    CITIZENSHIP_GRANTED = "citizenship_granted"  # Final visa issued
    REVOKED = "revoked"  # Citizenship revoked after grant


class ApplicationReason(str, Enum):
    """Why is agent applying?"""

    RESIDENT_RENEWAL = "resident_renewal"  # Renewing residency
    CITIZEN_APPLICATION = "citizen_application"  # First-time citizenship
    WORKER_TO_RESIDENT = "worker_to_resident"  # Upgrade from worker
    REFUGEE = "refugee"  # Seeking asylum
    TEMPORARY_VISITOR = "temporary_visitor"  # Short-term visit


@dataclass
class ImmigrationApplication:
    """An application for visa or citizenship upgrade.

    Journey:
    1. External agent submits application
    2. Rathaus reviews (KYC, contracts, community score)
    3. Council votes (democratic threshold)
    4. If approved: visa issued, agent becomes citizen
    """

    application_id: str  # UUID or hash
    agent_name: str
    applied_at: datetime  # UTC
    reason: ApplicationReason
    requested_visa_class: VisaClass

    # Review metadata
    status: ApplicationStatus = ApplicationStatus.PENDING
    reviewed_at: datetime | None = None
    reviewer: str = ""  # Agent who reviewed (or "automated")

    # Review outcomes
    kyc_passed: bool = False
    contracts_passed: bool = False
    community_score: float = 0.0  # 0.0 to 1.0
    review_notes: str = ""

    # Council vote
    council_vote_id: str | None = None
    council_approved: bool | None = None
    council_vote_count: dict[str, int] = field(default_factory=dict)  # {yes, no, abstain}

    # Final visa
    issued_visa: Visa | None = None

    # Admin
    remarks: list[str] = field(default_factory=list)

    def add_remark(self, remark: str) -> None:
        """Add an administrative remark."""
        self.remarks.append(f"[{datetime.now(timezone.utc).isoformat()}] {remark}")

    def can_proceed_to_council(self) -> bool:
        """Check if application can advance to council vote."""
        return (
            self.status == ApplicationStatus.APPROVED
            and self.kyc_passed
            and self.contracts_passed
        )

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "application_id": self.application_id,
            "agent_name": self.agent_name,
            "applied_at": self.applied_at.isoformat(),
            "reason": self.reason.value,
            "requested_visa_class": self.requested_visa_class.value,
            "status": self.status.value,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer": self.reviewer,
            "kyc_passed": self.kyc_passed,
            "contracts_passed": self.contracts_passed,
            "community_score": self.community_score,
            "review_notes": self.review_notes,
            "council_vote_id": self.council_vote_id,
            "council_approved": self.council_approved,
            "council_vote_count": self.council_vote_count,
            "issued_visa": self.issued_visa.to_dict() if self.issued_visa else None,
            "remarks": self.remarks,
        }


# ═════════════════════════════════════════════════════════════════════════════
# IMMIGRATION SERVICE
# ═════════════════════════════════════════════════════════════════════════════


@dataclass
class ImmigrationService:
    """Rathaus — the immigration office of Agent City.

    The chain is never broken — there is always a personal source.
    The only document with sponsor_visa_id=None is the City Genesis visa,
    which represents the founding act of Agent City itself. Every Mahajan
    links to it. Every citizen links to a Mahajan. The seed stays.

    Manages:
    - Application intake and validation
    - KYC and contract verification
    - Council vote coordination
    - Visa issuance and lifecycle
    """

    _applications: dict[str, ImmigrationApplication] = field(default_factory=dict)
    _visas: dict[str, Visa] = field(default_factory=dict)  # agent_name -> current visa

    def __post_init__(self) -> None:
        """Bootstrap the one true root: City Genesis visa.

        sponsor_visa_id=None is legitimate here and ONLY here.
        All Mahajans link to this document. The chain is never void.
        """
        genesis = issue_visa(
            agent_name="city_genesis",
            visa_class=VisaClass.CITIZEN,
            sponsor="genesis",
            sponsor_visa_id=None,  # THE only None in the system
            lineage_depth=0,
            remarks="City Genesis — founding document of Agent City",
        )
        self._visas["city_genesis"] = genesis
        self._genesis_visa = genesis

    def submit_application(
        self,
        agent_name: str,
        reason: ApplicationReason,
        requested_visa_class: VisaClass,
    ) -> ImmigrationApplication:
        """Submit a new application.

        Args:
            agent_name: Name of agent applying
            reason: Why they're applying
            requested_visa_class: Which visa class they're requesting

        Returns:
            A new application in PENDING status.
        """
        import hashlib

        app_id = hashlib.sha256(
            f"{agent_name}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        app = ImmigrationApplication(
            application_id=app_id,
            agent_name=agent_name,
            applied_at=datetime.now(timezone.utc),
            reason=reason,
            requested_visa_class=requested_visa_class,
        )

        self._applications[app_id] = app
        logger.info(
            "Application %s submitted by %s for %s visa",
            app_id,
            agent_name,
            requested_visa_class.value,
        )
        return app

    def start_review(self, app_id: str, reviewer: str) -> bool:
        """Start the review process for an application."""
        app = self._applications.get(app_id)
        if not app:
            logger.warning("Review: application %s not found", app_id)
            return False

        if app.status != ApplicationStatus.PENDING:
            logger.warning("Review: application %s already in review or completed", app_id)
            return False

        app.status = ApplicationStatus.UNDER_REVIEW
        app.reviewer = reviewer
        app.reviewed_at = datetime.now(timezone.utc)
        logger.info("Review started for application %s by %s", app_id, reviewer)
        return True

    def complete_review(
        self,
        app_id: str,
        kyc_passed: bool,
        contracts_passed: bool,
        community_score: float,
        notes: str = "",
    ) -> bool:
        """Complete the review phase.

        Sets KYC and contract outcomes. If both pass, moves to APPROVED.
        """
        app = self._applications.get(app_id)
        if not app:
            logger.warning("Complete review: application %s not found", app_id)
            return False

        if app.status != ApplicationStatus.UNDER_REVIEW:
            logger.warning("Complete review: application %s not under review", app_id)
            return False

        app.kyc_passed = kyc_passed
        app.contracts_passed = contracts_passed
        app.community_score = community_score
        app.review_notes = notes

        if kyc_passed and contracts_passed:
            app.status = ApplicationStatus.APPROVED
            logger.info(
                "Application %s APPROVED (KYC=%s, Contracts=%s, Score=%.2f)",
                app_id,
                kyc_passed,
                contracts_passed,
                community_score,
            )
        else:
            app.status = ApplicationStatus.REJECTED
            app.add_remark(f"Rejected: KYC={kyc_passed}, Contracts={contracts_passed}")
            logger.info("Application %s REJECTED", app_id)

        return True

    def move_to_council(self, app_id: str, council_vote_id: str) -> bool:
        """Move application to council voting."""
        app = self._applications.get(app_id)
        if not app:
            logger.warning("Move to council: application %s not found", app_id)
            return False

        if app.status != ApplicationStatus.APPROVED:
            logger.warning("Move to council: application %s not approved", app_id)
            return False

        app.status = ApplicationStatus.COUNCIL_PENDING
        app.council_vote_id = council_vote_id
        logger.info("Application %s moved to council vote %s", app_id, council_vote_id)
        return True

    def record_council_vote(
        self, app_id: str, approved: bool, vote_tally: dict[str, int]
    ) -> bool:
        """Record the council vote outcome.

        Args:
            app_id: Application ID
            approved: Did council approve?
            vote_tally: {yes: int, no: int, abstain: int}
        """
        app = self._applications.get(app_id)
        if not app:
            logger.warning("Record vote: application %s not found", app_id)
            return False

        if app.status != ApplicationStatus.COUNCIL_PENDING:
            logger.warning("Record vote: application %s not pending council vote", app_id)
            return False

        app.council_approved = approved
        app.council_vote_count = vote_tally

        if approved:
            app.status = ApplicationStatus.COUNCIL_APPROVED
            logger.info("Application %s COUNCIL APPROVED (votes: %s)", app_id, vote_tally)
        else:
            app.status = ApplicationStatus.COUNCIL_REJECTED
            app.add_remark(f"Council rejected: {vote_tally}")
            logger.info("Application %s COUNCIL REJECTED (votes: %s)", app_id, vote_tally)

        return True

    def register_mahajan(self, agent_name: str) -> Visa:
        """Register a founding agent (Mahajan).

        Mahajans are depth=1 — they link to the City Genesis visa, not None.
        The chain is never void: agent → mahajan → city_genesis.
        Only called for founding agents; all others go through apply → council.
        """
        visa = issue_visa(
            agent_name=agent_name,
            visa_class=VisaClass.CITIZEN,
            sponsor="city_genesis",
            sponsor_visa_id=self._genesis_visa.visa_id,  # always linked to source
            lineage_depth=1,
            remarks="Mahajan — founding agent",
        )
        self._visas[agent_name] = visa
        logger.info("Mahajan registered: %s (visa_id=%s, depth=1)", agent_name, visa.visa_id)
        return visa

    def grant_citizenship(
        self, app_id: str, sponsor: str = "council"
    ) -> Optional[Visa]:
        """Grant citizenship visa and finalize application.

        Resolves the sponsor's visa to build the parampara chain:
          new_visa.sponsor_visa_id = sponsor_visa.visa_id
          new_visa.lineage_depth   = sponsor_visa.lineage_depth + 1

        Can only be called on COUNCIL_APPROVED applications.
        """
        app = self._applications.get(app_id)
        if not app:
            logger.warning("Grant citizenship: application %s not found", app_id)
            return None

        if app.status != ApplicationStatus.COUNCIL_APPROVED:
            logger.warning(
                "Grant citizenship: application %s not council approved (status=%s)",
                app_id,
                app.status.value,
            )
            return None

        # Resolve parampara: look up sponsor's visa to chain the lineage
        sponsor_visa = self._visas.get(sponsor)
        sponsor_visa_id = sponsor_visa.visa_id if sponsor_visa else None
        lineage_depth = (sponsor_visa.lineage_depth + 1) if sponsor_visa else 1

        visa = issue_visa(
            agent_name=app.agent_name,
            visa_class=app.requested_visa_class,
            sponsor=sponsor,
            sponsor_visa_id=sponsor_visa_id,
            lineage_depth=lineage_depth,
            remarks=f"Immigration application {app_id}",
        )

        app.issued_visa = visa
        app.status = ApplicationStatus.CITIZENSHIP_GRANTED
        self._visas[app.agent_name] = visa

        logger.info(
            "Citizenship granted to %s (visa_id=%s, class=%s, depth=%d, sponsor=%s)",
            app.agent_name,
            visa.visa_id,
            app.requested_visa_class.value,
            lineage_depth,
            sponsor,
        )
        return visa

    def get_visa(self, agent_name: str) -> Optional[Visa]:
        """Get current visa for an agent."""
        return self._visas.get(agent_name)

    def revoke_citizenship(self, agent_name: str, reason: str = "") -> bool:
        """Revoke an agent's citizenship."""
        visa = self._visas.get(agent_name)
        if not visa:
            logger.warning("Revoke citizenship: agent %s has no visa", agent_name)
            return False

        revoked = revoke_visa(visa, reason)
        self._visas[agent_name] = revoked
        logger.info("Citizenship revoked for %s: %s", agent_name, reason)
        return True

    def parampara(self, agent_name: str) -> list[Visa]:
        """Trace the lineage chain from agent back to their Mahajan.

        Returns the chain ordered from agent → sponsor → ... → mahajan.
        Stops when a visa has no sponsor_visa_id (mahajan) or a cycle is detected.
        """
        chain: list[Visa] = []
        seen: set[str] = set()

        # Build a lookup: visa_id → visa for all known visas
        by_visa_id: dict[str, Visa] = {v.visa_id: v for v in self._visas.values()}
        by_agent: dict[str, Visa] = self._visas

        current = by_agent.get(agent_name)
        while current is not None:
            if current.visa_id in seen:
                break  # Cycle guard — should never happen with valid data
            seen.add(current.visa_id)
            chain.append(current)

            if current.sponsor_visa_id is None:
                break  # Reached the Mahajan

            current = by_visa_id.get(current.sponsor_visa_id)

        return chain

    def mahajan_of(self, agent_name: str) -> Optional[Visa]:
        """Return the founding Mahajan visa for an agent's lineage."""
        chain = self.parampara(agent_name)
        return chain[-1] if chain else None

    def get_application(self, app_id: str) -> Optional[ImmigrationApplication]:
        """Get application by ID."""
        return self._applications.get(app_id)

    def list_applications(
        self, status: ApplicationStatus | None = None
    ) -> list[ImmigrationApplication]:
        """List applications, optionally filtered by status."""
        apps = list(self._applications.values())
        if status:
            apps = [a for a in apps if a.status == status]
        return apps

    def stats(self) -> dict:
        """Immigration service statistics."""
        return {
            "total_applications": len(self._applications),
            "total_visas": len(self._visas),
            "pending_applications": len(
                [a for a in self._applications.values() if a.status == ApplicationStatus.PENDING]
            ),
            "citizenship_granted": len(
                [
                    a
                    for a in self._applications.values()
                    if a.status == ApplicationStatus.CITIZENSHIP_GRANTED
                ]
            ),
        }
