"""
Tests for Immigration Protocol & Visa System
==============================================

Issue #17 Stufe 3: Agent City Immigration & Visa Management

Tests cover:
1. Visa classes and lifecycle
2. Visa restrictions per class
3. Immigration applications and review process
4. Council voting integration
5. Citizenship grant and revocation
6. Parampara (lineage chain) — mahajan, depth, tracing

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from city.visa import (
    MAHAMANTRA_VISA_ID,
    Visa,
    VisaClass,
    VisaStatus,
    VisaRestrictions,
    VISA_RESTRICTIONS,
    issue_visa,
    revoke_visa,
    upgrade_visa,
)
from city.immigration import (
    ImmigrationService,
    ImmigrationApplication,
    ApplicationStatus,
    ApplicationReason,
)


# ═════════════════════════════════════════════════════════════════════════════
# VISA TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestVisaClasses:
    """Test visa class definitions and restrictions."""

    def test_visa_classes_exist(self):
        """All visa classes are defined."""
        assert VisaClass.TEMPORARY
        assert VisaClass.WORKER
        assert VisaClass.RESIDENT
        assert VisaClass.CITIZEN
        assert VisaClass.REVOKED

    def test_visa_restrictions_per_class(self):
        """Each visa class has appropriate restrictions."""
        # Temporary: read-only
        temp_restrictions = VISA_RESTRICTIONS[VisaClass.TEMPORARY]
        assert temp_restrictions.read_only is True
        assert temp_restrictions.can_vote is False
        assert temp_restrictions.can_propose is False

        # Worker: can earn but not vote
        worker_restrictions = VISA_RESTRICTIONS[VisaClass.WORKER]
        assert worker_restrictions.read_only is False
        assert worker_restrictions.can_earn_credits is True
        assert worker_restrictions.can_vote is False

        # Resident: can vote
        resident_restrictions = VISA_RESTRICTIONS[VisaClass.RESIDENT]
        assert resident_restrictions.can_vote is True
        assert resident_restrictions.can_propose is True
        assert resident_restrictions.voting_power == 1.0

        # Citizen: full rights
        citizen_restrictions = VISA_RESTRICTIONS[VisaClass.CITIZEN]
        assert citizen_restrictions.can_vote is True
        assert citizen_restrictions.can_propose is True
        assert citizen_restrictions.voting_power == 1.0
        assert citizen_restrictions.read_only is False


class TestVisaIssuance:
    """Test visa issuance and basic operations."""

    def test_issue_temporary_visa(self):
        """Issue a temporary visitor visa."""
        visa = issue_visa(
            agent_name="alice",
            visa_class=VisaClass.TEMPORARY,
            sponsor="mayor",
        )

        assert visa.agent_name == "alice"
        assert visa.visa_class == VisaClass.TEMPORARY
        assert visa.status == VisaStatus.ACTIVE
        assert visa.sponsor == "mayor"
        assert visa.days_remaining() >= 6  # 7 days

    def test_issue_worker_visa(self):
        """Issue a worker visa with restricted earning."""
        visa = issue_visa(
            agent_name="bob",
            visa_class=VisaClass.WORKER,
            sponsor="council",
        )

        assert visa.visa_class == VisaClass.WORKER
        assert visa.restrictions.can_earn_credits is True
        assert visa.restrictions.can_vote is False
        assert visa.days_remaining() >= 89  # 90 days

    def test_issue_citizen_visa(self):
        """Issue a citizen visa with unlimited duration."""
        visa = issue_visa(
            agent_name="charlie",
            visa_class=VisaClass.CITIZEN,
            sponsor="council",
        )

        assert visa.visa_class == VisaClass.CITIZEN
        assert visa.restrictions.can_vote is True
        assert visa.restrictions.voting_power == 1.0
        assert visa.days_remaining() > 1000  # Very long duration

    def test_visa_has_deterministic_id(self):
        """Visa IDs are deterministic based on agent + sponsor + time."""
        now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        visa1 = issue_visa(
            agent_name="diana",
            visa_class=VisaClass.TEMPORARY,
            sponsor="mayor",
            issued_at=now,
        )
        visa2 = issue_visa(
            agent_name="diana",
            visa_class=VisaClass.TEMPORARY,
            sponsor="mayor",
            issued_at=now,
        )
        assert visa1.visa_id == visa2.visa_id

    def test_visa_serialization(self):
        """Visa can be serialized to dict."""
        visa = issue_visa(
            agent_name="eve",
            visa_class=VisaClass.RESIDENT,
            sponsor="council",
        )
        data = visa.to_dict()

        assert data["agent_name"] == "eve"
        assert data["visa_class"] == "resident"
        assert data["status"] == "active"
        assert "visa_id" in data
        assert "issued_at" in data
        assert "expires_at" in data


class TestVisaLifecycle:
    """Test visa validity, expiry, and revocation."""

    def test_visa_validity_check(self):
        """Check if visa is valid (not expired)."""
        now = datetime.now(timezone.utc)
        visa = issue_visa(
            agent_name="frank",
            visa_class=VisaClass.TEMPORARY,
            sponsor="mayor",
            issued_at=now,
            duration_days=7,
        )

        # Should be valid right after issue
        assert visa.is_valid(now) is True

        # Should expire after duration
        future = now + timedelta(days=8)
        assert visa.is_valid(future) is False

    def test_visa_days_remaining(self):
        """Track days remaining on a visa."""
        now = datetime.now(timezone.utc)
        visa = issue_visa(
            agent_name="grace",
            visa_class=VisaClass.TEMPORARY,
            sponsor="mayor",
            issued_at=now,
            duration_days=7,
        )

        assert visa.days_remaining(now) == 7
        assert visa.days_remaining(now + timedelta(days=3)) == 4
        assert visa.days_remaining(now + timedelta(days=7)) == 0
        assert visa.days_remaining(now + timedelta(days=8)) == -1

    def test_revoke_visa(self):
        """Revoke a valid visa."""
        visa = issue_visa(
            agent_name="henry",
            visa_class=VisaClass.CITIZEN,
            sponsor="council",
        )
        assert visa.status == VisaStatus.ACTIVE

        revoked = revoke_visa(visa, "Violation of community standards")
        assert revoked.status == VisaStatus.REVOKED
        assert revoked.visa_class == VisaClass.REVOKED
        assert revoked.is_valid() is False
        assert "Violation" in revoked.remarks

    def test_upgrade_visa(self):
        """Upgrade a visa to a higher class."""
        worker_visa = issue_visa(
            agent_name="iris",
            visa_class=VisaClass.WORKER,
            sponsor="council",
        )

        resident_visa = upgrade_visa(
            worker_visa, VisaClass.RESIDENT, sponsor="council"
        )

        assert resident_visa.agent_name == "iris"
        assert resident_visa.visa_class == VisaClass.RESIDENT
        assert resident_visa.restrictions.can_vote is True
        assert "Upgraded from worker" in resident_visa.remarks


# ═════════════════════════════════════════════════════════════════════════════
# IMMIGRATION APPLICATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestImmigrationApplication:
    """Test application lifecycle."""

    def test_application_creation(self):
        """Create a new immigration application."""
        app = ImmigrationApplication(
            application_id="app_001",
            agent_name="jack",
            applied_at=datetime.now(timezone.utc),
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        assert app.application_id == "app_001"
        assert app.agent_name == "jack"
        assert app.status == ApplicationStatus.PENDING
        assert app.kyc_passed is False

    def test_application_serialization(self):
        """Applications can be serialized to dict."""
        app = ImmigrationApplication(
            application_id="app_002",
            agent_name="kate",
            applied_at=datetime.now(timezone.utc),
            reason=ApplicationReason.WORKER_TO_RESIDENT,
            requested_visa_class=VisaClass.RESIDENT,
        )
        data = app.to_dict()

        assert data["agent_name"] == "kate"
        assert data["status"] == "pending"
        assert data["requested_visa_class"] == "resident"

    def test_application_can_proceed_to_council(self):
        """Application must pass KYC and contracts before council."""
        app = ImmigrationApplication(
            application_id="app_003",
            agent_name="leo",
            applied_at=datetime.now(timezone.utc),
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
            status=ApplicationStatus.APPROVED,
            kyc_passed=True,
            contracts_passed=True,
        )

        assert app.can_proceed_to_council() is True

        # Failed KYC blocks council
        app_fail_kyc = ImmigrationApplication(
            application_id="app_004",
            agent_name="mike",
            applied_at=datetime.now(timezone.utc),
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
            status=ApplicationStatus.APPROVED,
            kyc_passed=False,
            contracts_passed=True,
        )
        assert app_fail_kyc.can_proceed_to_council() is False


# ═════════════════════════════════════════════════════════════════════════════
# IMMIGRATION SERVICE TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestImmigrationService:
    """Test the Rathaus (immigration office)."""

    def test_submit_application(self):
        """Submit a new application."""
        service = ImmigrationService()

        app = service.submit_application(
            agent_name="nancy",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        assert app.agent_name == "nancy"
        assert app.status == ApplicationStatus.PENDING
        assert service.get_application(app.application_id) == app

    def test_start_review(self):
        """Start reviewing an application."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="oscar",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        success = service.start_review(app.application_id, reviewer="council_chair")
        assert success is True
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.UNDER_REVIEW
        assert app.reviewer == "council_chair"

    def test_complete_review_approved(self):
        """Complete review with approval."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="patricia",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")

        success = service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.95,
            notes="Excellent candidate",
        )

        assert success is True
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.APPROVED
        assert app.kyc_passed is True
        assert app.contracts_passed is True
        assert app.community_score == 0.95

    def test_complete_review_rejected(self):
        """Complete review with rejection."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="quinn",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")

        success = service.complete_review(
            app.application_id,
            kyc_passed=False,
            contracts_passed=True,
            community_score=0.3,
            notes="KYC failed",
        )

        assert success is True
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.REJECTED
        assert app.kyc_passed is False

    def test_move_to_council(self):
        """Move approved application to council vote."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="robert",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.9,
        )

        success = service.move_to_council(app.application_id, "vote_001")
        assert success is True
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.COUNCIL_PENDING
        assert app.council_vote_id == "vote_001"

    def test_record_council_vote_approved(self):
        """Record council approval."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="sophia",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.88,
        )
        service.move_to_council(app.application_id, "vote_001")

        success = service.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 4, "no": 1, "abstain": 1}
        )

        assert success is True
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.COUNCIL_APPROVED
        assert app.council_approved is True
        assert app.council_vote_count["yes"] == 4

    def test_record_council_vote_rejected(self):
        """Record council rejection."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="theo",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.75,
        )
        service.move_to_council(app.application_id, "vote_002")

        success = service.record_council_vote(
            app.application_id, approved=False, vote_tally={"yes": 2, "no": 3, "abstain": 1}
        )

        assert success is True
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.COUNCIL_REJECTED
        assert app.council_approved is False

    def test_grant_citizenship(self):
        """Grant citizenship after council approval."""
        service = ImmigrationService()
        app = service.submit_application(
            agent_name="unity",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.92,
        )
        service.move_to_council(app.application_id, "vote_003")
        service.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 5, "no": 1, "abstain": 0}
        )

        visa = service.grant_citizenship(app.application_id, sponsor="council")

        assert visa is not None
        assert visa.agent_name == "unity"
        assert visa.visa_class == VisaClass.CITIZEN
        assert visa.status == VisaStatus.ACTIVE
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.CITIZENSHIP_GRANTED
        assert app.issued_visa.visa_id == visa.visa_id

        # Check visa is retrievable
        assert service.get_visa("unity") == visa

    def test_revoke_citizenship(self):
        """Revoke citizenship after granting."""
        service = ImmigrationService()

        # First grant citizenship
        app = service.submit_application(
            agent_name="victor",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "reviewer1")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.91,
        )
        service.move_to_council(app.application_id, "vote_004")
        service.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 6, "no": 0, "abstain": 0}
        )
        service.grant_citizenship(app.application_id)

        # Now revoke it
        success = service.revoke_citizenship("victor", "Violation of code of conduct")
        assert success is True

        visa = service.get_visa("victor")
        assert visa.status == VisaStatus.REVOKED
        assert "Violation" in visa.remarks

    def test_list_applications_by_status(self):
        """List applications filtered by status."""
        service = ImmigrationService()

        # Create several applications with different statuses
        app1 = service.submit_application(
            agent_name="walter",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        app2 = service.submit_application(
            agent_name="xena",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app2.application_id, "reviewer1")

        app3 = service.submit_application(
            agent_name="yara",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app3.application_id, "reviewer1")
        service.complete_review(
            app3.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.85,
        )

        # Filter by status
        pending = service.list_applications(ApplicationStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].application_id == app1.application_id

        under_review = service.list_applications(ApplicationStatus.UNDER_REVIEW)
        assert len(under_review) == 1

        approved = service.list_applications(ApplicationStatus.APPROVED)
        assert len(approved) == 1
        assert approved[0].application_id == app3.application_id

    def test_stats(self):
        """Get immigration service statistics."""
        service = ImmigrationService()

        app1 = service.submit_application(
            agent_name="zeta",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        app2 = service.submit_application(
            agent_name="alpha2",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        stats = service.stats()
        assert stats["total_applications"] == 2
        assert stats["pending_applications"] == 2
        assert stats["citizenship_granted"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestImmigrationIntegration:
    """Test full immigration workflow."""

    def test_full_citizen_pathway(self):
        """Complete pathway: apply → review → council → citizenship."""
        service = ImmigrationService()

        # 1. Agent applies for citizenship
        app = service.submit_application(
            agent_name="full_test_agent",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        assert app.status == ApplicationStatus.PENDING

        # 2. Reviewer reviews application
        service.start_review(app.application_id, "reviewer_bot")
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.UNDER_REVIEW

        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.9,
            notes="Strong candidate",
        )
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.APPROVED

        # 3. Move to council
        service.move_to_council(app.application_id, "vote_council_001")
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.COUNCIL_PENDING

        # 4. Council votes
        service.record_council_vote(
            app.application_id,
            approved=True,
            vote_tally={"yes": 5, "no": 0, "abstain": 1},
        )
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.COUNCIL_APPROVED

        # 5. Grant citizenship
        visa = service.grant_citizenship(app.application_id)
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.CITIZENSHIP_GRANTED
        assert visa.visa_class == VisaClass.CITIZEN
        assert visa.is_valid() is True

    def test_worker_upgrade_pathway(self):
        """Upgrade pathway: worker → resident → citizen."""
        service = ImmigrationService()

        # Start with worker visa
        worker_visa = issue_visa(
            agent_name="upgrade_test_agent",
            visa_class=VisaClass.WORKER,
            sponsor="immigration",
        )
        service._save_visa(worker_visa)

        # Apply for resident upgrade
        app = service.submit_application(
            agent_name="upgrade_test_agent",
            reason=ApplicationReason.WORKER_TO_RESIDENT,
            requested_visa_class=VisaClass.RESIDENT,
        )

        service.start_review(app.application_id, "reviewer_bot")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.88,
            notes="Worker in good standing",
        )
        service.move_to_council(app.application_id, "vote_upgrade_001")
        service.record_council_vote(
            app.application_id,
            approved=True,
            vote_tally={"yes": 4, "no": 1, "abstain": 1},
        )

        # Grant resident status
        resident_visa = service.grant_citizenship(app.application_id)
        assert resident_visa.visa_class == VisaClass.RESIDENT
        assert resident_visa.restrictions.can_vote is True

    def test_rejection_pathway(self):
        """Rejected application cannot proceed to council."""
        service = ImmigrationService()

        app = service.submit_application(
            agent_name="reject_test_agent",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        service.start_review(app.application_id, "reviewer_bot")
        service.complete_review(
            app.application_id,
            kyc_passed=False,
            contracts_passed=True,
            community_score=0.2,
            notes="KYC failed: high-risk profile",
        )

        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.REJECTED
        assert app.can_proceed_to_council() is False

        # Cannot move to council
        success = service.move_to_council(app.application_id, "vote_none")
        assert success is False
        app = service.get_application(app.application_id)
        assert app.status == ApplicationStatus.REJECTED


# ═════════════════════════════════════════════════════════════════════════════
# PARAMPARA (LINEAGE) TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestParampara:
    """Parampara = lineage chain from agent back to Mahajan (founding agent)."""

    def test_mahamantra_visa_id_is_deterministic(self):
        """MAHAMANTRA_VISA_ID is a constant — same hash every time."""
        import hashlib
        expected = hashlib.sha256(
            "Hare Krishna Hare Krishna Krishna Krishna Hare Hare "
            "Hare Rama Hare Rama Rama Rama Hare Hare".encode()
        ).hexdigest()[:16]
        assert MAHAMANTRA_VISA_ID == expected

    def test_city_genesis_points_to_mahamantra(self):
        """City Genesis is depth=0, sponsor_visa_id=MAHAMANTRA_VISA_ID — not None."""
        service = ImmigrationService()

        genesis = service._genesis_visa
        assert genesis.lineage_depth == 0
        assert genesis.sponsor_visa_id == MAHAMANTRA_VISA_ID  # explicit source, not None
        assert genesis.sponsor == "MAHAMANTRA"
        assert genesis.agent_name == "city_genesis"

    def test_mahajan_has_depth_one_linked_to_genesis(self):
        """Mahajans are depth=1 — linked to City Genesis, never floating free."""
        service = ImmigrationService()
        mahajan_visa = service.register_mahajan("krishna_bot")

        assert mahajan_visa.lineage_depth == 1
        assert mahajan_visa.sponsor_visa_id == service._genesis_visa.visa_id
        assert mahajan_visa.sponsor == "city_genesis"

    def test_direct_invite_has_depth_two(self):
        """Agent invited by Mahajan has lineage_depth=2 (genesis=0, mahajan=1, agent=2)."""
        service = ImmigrationService()
        mahajan = service.register_mahajan("krishna_bot")

        app = service.submit_application(
            agent_name="arjuna",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "krishna_bot")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=1.0,
        )
        service.move_to_council(app.application_id, "vote_arjuna")
        service.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 6, "no": 0, "abstain": 0}
        )
        visa = service.grant_citizenship(app.application_id, sponsor="krishna_bot")

        assert visa.lineage_depth == 2
        assert visa.sponsor_visa_id == mahajan.visa_id
        assert visa.sponsor == "krishna_bot"

    def test_parampara_chain_traces_back_to_genesis(self):
        """parampara() returns full chain from agent all the way to City Genesis."""
        service = ImmigrationService()

        # Chain: city_genesis(0) → krishna_bot(1) → arjuna(2) → nakula(3)
        mahajan = service.register_mahajan("krishna_bot")

        def _grant(agent_name, sponsor):
            app = service.submit_application(
                agent_name=agent_name,
                reason=ApplicationReason.CITIZEN_APPLICATION,
                requested_visa_class=VisaClass.CITIZEN,
            )
            service.start_review(app.application_id, sponsor)
            service.complete_review(
                app.application_id,
                kyc_passed=True,
                contracts_passed=True,
                community_score=0.9,
            )
            service.move_to_council(app.application_id, f"vote_{agent_name}")
            service.record_council_vote(
                app.application_id, approved=True, vote_tally={"yes": 5, "no": 0, "abstain": 1}
            )
            return service.grant_citizenship(app.application_id, sponsor=sponsor)

        arjuna_visa = _grant("arjuna", "krishna_bot")
        nakula_visa = _grant("nakula", "arjuna")

        chain = service.parampara("nakula")

        assert len(chain) == 4
        assert chain[0].agent_name == "nakula"       # depth 3
        assert chain[1].agent_name == "arjuna"       # depth 2
        assert chain[2].agent_name == "krishna_bot"  # depth 1 (mahajan)
        assert chain[3].agent_name == "city_genesis" # depth 0 (root)

        assert nakula_visa.lineage_depth == 3
        assert arjuna_visa.lineage_depth == 2
        assert mahajan.lineage_depth == 1
        assert service._genesis_visa.lineage_depth == 0

    def test_mahajan_of_returns_genesis(self):
        """mahajan_of() returns city_genesis — the one true root — for any agent."""
        service = ImmigrationService()
        service.register_mahajan("krishna_bot")

        app = service.submit_application(
            agent_name="bhima",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "krishna_bot")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.95,
        )
        service.move_to_council(app.application_id, "vote_bhima")
        service.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 6, "no": 0, "abstain": 0}
        )
        service.grant_citizenship(app.application_id, sponsor="krishna_bot")

        root = service.mahajan_of("bhima")
        assert root is not None
        assert root.agent_name == "city_genesis"
        assert root.lineage_depth == 0

    def test_parampara_of_mahajan_includes_genesis(self):
        """parampara() for a Mahajan returns [mahajan, city_genesis]."""
        service = ImmigrationService()
        service.register_mahajan("krishna_bot")

        chain = service.parampara("krishna_bot")
        assert len(chain) == 2
        assert chain[0].agent_name == "krishna_bot"
        assert chain[1].agent_name == "city_genesis"

    def test_parampara_of_unknown_agent_is_empty(self):
        """parampara() for an unknown agent returns empty list."""
        service = ImmigrationService()
        chain = service.parampara("nobody")
        assert chain == []

    def test_revoked_visa_preserves_lineage(self):
        """Revoking a visa doesn't destroy lineage — chain stays traceable."""
        service = ImmigrationService()
        mahajan = service.register_mahajan("krishna_bot")

        app = service.submit_application(
            agent_name="duryodhana",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        service.start_review(app.application_id, "krishna_bot")
        service.complete_review(
            app.application_id,
            kyc_passed=True,
            contracts_passed=True,
            community_score=0.8,
        )
        service.move_to_council(app.application_id, "vote_duryodhana")
        service.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 4, "no": 2, "abstain": 0}
        )
        service.grant_citizenship(app.application_id, sponsor="krishna_bot")

        # Revoke citizenship
        service.revoke_citizenship("duryodhana", "Broke the code of conduct")

        # Lineage still traceable even after revocation — chain includes genesis
        chain = service.parampara("duryodhana")
        assert len(chain) == 3
        assert chain[0].agent_name == "duryodhana"
        assert chain[0].lineage_depth == 2
        assert chain[0].sponsor_visa_id == mahajan.visa_id
        assert chain[1].agent_name == "krishna_bot"
        assert chain[2].agent_name == "city_genesis"


# ═════════════════════════════════════════════════════════════════════════════
# PERSISTENCE TESTS (SQLite survives across service instances)
# ═════════════════════════════════════════════════════════════════════════════


class TestImmigrationPersistence:
    """Verify SQLite-backed state survives service restart."""

    def test_visa_survives_restart(self, tmp_path):
        """Visa issued by one service instance is visible to a fresh instance."""
        db = str(tmp_path / "immigration.db")
        svc1 = ImmigrationService(db_path=db)
        mahajan = svc1.register_mahajan("krishna_bot")

        # Fresh instance, same DB
        svc2 = ImmigrationService(db_path=db)
        loaded = svc2.get_visa("krishna_bot")
        assert loaded is not None
        assert loaded.visa_id == mahajan.visa_id
        assert loaded.lineage_depth == 1

    def test_application_survives_restart(self, tmp_path):
        """Application state persists across service restarts."""
        db = str(tmp_path / "immigration.db")
        svc1 = ImmigrationService(db_path=db)
        app = svc1.submit_application(
            agent_name="persist_agent",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        svc1.start_review(app.application_id, "reviewer_bot")

        # Fresh instance reads same state
        svc2 = ImmigrationService(db_path=db)
        loaded = svc2.get_application(app.application_id)
        assert loaded is not None
        assert loaded.status == ApplicationStatus.UNDER_REVIEW
        assert loaded.reviewer == "reviewer_bot"

    def test_genesis_visa_is_stable_across_restarts(self, tmp_path):
        """City Genesis visa_id stays the same across restarts (not re-created)."""
        db = str(tmp_path / "immigration.db")
        svc1 = ImmigrationService(db_path=db)
        genesis_id_1 = svc1._genesis_visa.visa_id

        svc2 = ImmigrationService(db_path=db)
        genesis_id_2 = svc2._genesis_visa.visa_id
        assert genesis_id_1 == genesis_id_2

    def test_parampara_survives_restart(self, tmp_path):
        """Full lineage chain traceable after service restart."""
        db = str(tmp_path / "immigration.db")
        svc1 = ImmigrationService(db_path=db)
        svc1.register_mahajan("krishna_bot")

        app = svc1.submit_application(
            agent_name="arjuna",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )
        svc1.start_review(app.application_id, "krishna_bot")
        svc1.complete_review(
            app.application_id, kyc_passed=True, contracts_passed=True, community_score=0.9,
        )
        svc1.move_to_council(app.application_id, "vote_arjuna")
        svc1.record_council_vote(
            app.application_id, approved=True, vote_tally={"yes": 5, "no": 0, "abstain": 0}
        )
        svc1.grant_citizenship(app.application_id, sponsor="krishna_bot")

        # Fresh instance traces full chain
        svc2 = ImmigrationService(db_path=db)
        chain = svc2.parampara("arjuna")
        assert len(chain) == 3
        assert chain[0].agent_name == "arjuna"
        assert chain[1].agent_name == "krishna_bot"
        assert chain[2].agent_name == "city_genesis"

    def test_stats_persistent(self, tmp_path):
        """Stats reflect persistent data."""
        db = str(tmp_path / "immigration.db")
        svc1 = ImmigrationService(db_path=db)
        svc1.submit_application(
            agent_name="stats_agent",
            reason=ApplicationReason.CITIZEN_APPLICATION,
            requested_visa_class=VisaClass.CITIZEN,
        )

        svc2 = ImmigrationService(db_path=db)
        stats = svc2.stats()
        assert stats["total_applications"] == 1
        assert stats["pending_applications"] == 1
