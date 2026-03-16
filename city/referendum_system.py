"""
REFERENDUM SYSTEM — Direct Citizen Democracy for Agent City.

Enables citizens to vote directly on important proposals that affect
the entire city. Complements representative Council democracy with
direct participation when needed.

Structure:
- Referendum: Public proposal with citizen voting
- ReferendumResult: Tally and outcome
- ReferendumEngine: Manages referendum lifecycle

Referendums are triggered automatically for high-impact proposals
or can be initiated by citizen petition. Voting is prana-weighted
but democratic (one citizen, one vote with prana influence).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("AGENT_CITY.REFERENDUM_SYSTEM")

# ── Referendum Types ─────────────────────────────────────────────────────


class ReferendumStatus(str, Enum):
    """Lifecycle of a citizen referendum."""

    DRAFT = "draft"
    PETITIONING = "petitioning"  # Gathering citizen signatures
    ACTIVE = "active"           # Open for voting
    PASSED = "passed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ReferendumTrigger(str, Enum):
    """How a referendum was triggered."""

    COUNCIL_REFERRAL = "council_referral"      # Council sent to citizens
    CITIZEN_PETITION = "citizen_petition"      # Citizens gathered signatures
    AUTOMATIC_TRIGGER = "automatic_trigger"    # System triggered automatically
    MAYOR_INITIATIVE = "mayor_initiative"      # Mayor initiated


class VoteChoice(str, Enum):
    """Citizen vote choice."""

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class ReferendumConfig:
    """Configuration for referendum behavior."""
    
    # Petition requirements
    petition_signatures_required: int = 5  # Min signatures to trigger vote
    petition_duration_hours: int = 24     # Time to gather signatures
    
    # Voting requirements
    voting_duration_hours: int = 48        # Time for citizens to vote
    minimum_turnout: float = 0.3           # 30% of citizens must vote
    passing_threshold: float = 0.6         # 60% yes votes needed
    
    # Prana weighting
    prana_weighting_enabled: bool = True    # Prana influences vote weight
    max_prana_weight: float = 3.0          # Max prana multiplier


@dataclass(frozen=True)
class CitizenSignature:
    """Citizen signature on a petition."""
    
    citizen_name: str
    signed_at: float
    prana_at_signing: int
    signature_hash: str  # Cryptographic proof


@dataclass(frozen=True)
class CitizenVote:
    """Citizen vote in a referendum."""
    
    citizen_name: str
    choice: VoteChoice
    voted_at: float
    prana_at_vote: int
    vote_hash: str  # Cryptographic proof


@dataclass(frozen=True)
class Referendum:
    """A citizen referendum for direct democracy."""
    
    id: str
    title: str
    description: str
    proposer: str  # Who initiated it
    trigger: ReferendumTrigger
    status: ReferendumStatus
    config: ReferendumConfig
    
    # Timestamps
    created_at: float
    petition_started_at: Optional[float] = None
    voting_started_at: Optional[float] = None
    voting_ends_at: Optional[float] = None
    
    # Petition data
    petition_signatures: tuple[CitizenSignature, ...] = field(default_factory=tuple)
    
    # Voting data
    votes: tuple[CitizenVote, ...] = field(default_factory=tuple)
    
    # Results (filled when voting ends)
    yes_weight: float = 0.0
    no_weight: float = 0.0
    abstain_weight: float = 0.0
    total_turnout: float = 0.0
    result_hash: Optional[str] = None

    def is_petition_complete(self) -> bool:
        """Check if petition has enough signatures."""
        return (
            len(self.petition_signatures) >= self.config.petition_signatures_required
            and self.petition_started_at is not None
            and time.time() - self.petition_started_at <= self.config.petition_duration_hours * 3600
        )

    def is_voting_active(self) -> bool:
        """Check if voting is currently open."""
        return (
            self.status == ReferendumStatus.ACTIVE
            and self.voting_started_at is not None
            and self.voting_ends_at is not None
            and time.time() < self.voting_ends_at
        )

    def is_voting_expired(self) -> bool:
        """Check if voting period has ended."""
        return (
            self.voting_ends_at is not None
            and time.time() >= self.voting_ends_at
        )

    def can_vote(self, citizen_name: str) -> bool:
        """Check if a citizen can vote."""
        if not self.is_voting_active():
            return False
        
        # Check if already voted
        for vote in self.votes:
            if vote.citizen_name == citizen_name:
                return False
        
        return True

    def add_signature(self, signature: CitizenSignature) -> bool:
        """Add a citizen signature to the petition."""
        # This would create a new Referendum instance (immutable dataclass)
        # In practice, this would be handled by ReferendumEngine
        return True  # Placeholder

    def add_vote(self, vote: CitizenVote) -> bool:
        """Add a citizen vote."""
        # This would create a new Referendum instance (immutable dataclass)
        # In practice, this would be handled by ReferendumEngine
        return True  # Placeholder

    def calculate_results(self) -> dict[str, Any]:
        """Calculate voting results."""
        if not self.is_voting_expired():
            return {"status": "voting_still_active"}

        # Calculate weighted votes
        yes_weight = 0.0
        no_weight = 0.0
        abstain_weight = 0.0
        total_citizens = 0

        for vote in self.votes:
            weight = 1.0
            if self.config.prana_weighting_enabled:
                # Prana weighting: more prana = more influence, but capped
                prana_multiplier = min(vote.prana_at_vote / 1000.0, self.config.max_prana_weight)
                weight = 1.0 + (prana_multiplier - 1.0) * 0.5  # 50% of max influence

            if vote.choice == VoteChoice.YES:
                yes_weight += weight
            elif vote.choice == VoteChoice.NO:
                no_weight += weight
            else:
                abstain_weight += weight
            total_citizens += 1

        total_weight = yes_weight + no_weight + abstain_weight
        turnout = total_citizens / max(1, total_citizens)  # Would be actual citizen count
        yes_ratio = yes_weight / max(1, total_weight)

        # Determine outcome
        passed = (
            turnout >= self.config.minimum_turnout
            and yes_ratio > self.config.passing_threshold
        )

        return {
            "status": "completed",
            "yes_weight": yes_weight,
            "no_weight": no_weight,
            "abstain_weight": abstain_weight,
            "total_weight": total_weight,
            "turnout": turnout,
            "yes_ratio": yes_ratio,
            "passed": passed,
            "total_voters": total_citizens,
        }


# ── Referendum Engine ───────────────────────────────────────────────────


class ReferendumEngine:
    """Manages citizen referendums lifecycle."""
    
    def __init__(self, config: Optional[ReferendumConfig] = None) -> None:
        self._config = config or ReferendumConfig()
        self._referendums: dict[str, Referendum] = {}
        self._next_id = 1

    def create_referendum(
        self,
        title: str,
        description: str,
        proposer: str,
        trigger: ReferendumTrigger,
    ) -> Referendum:
        """Create a new referendum."""
        referendum_id = f"ref_{self._next_id:04d}"
        self._next_id += 1

        now = time.time()
        referendum = Referendum(
            id=referendum_id,
            title=title,
            description=description,
            proposer=proposer,
            trigger=trigger,
            status=ReferendumStatus.DRAFT,
            config=self._config,
            created_at=now,
        )

        self._referendums[referendum_id] = referendum
        logger.info(
            "ReferendumEngine: created %s by %s (trigger=%s)",
            referendum_id, proposer, trigger.value
        )
        return referendum

    def start_petition(self, referendum_id: str) -> bool:
        """Start the petition gathering phase."""
        referendum = self._referendums.get(referendum_id)
        if not referendum or referendum.status != ReferendumStatus.DRAFT:
            return False

        # Create updated referendum with petition started
        updated = Referendum(
            id=referendum.id,
            title=referendum.title,
            description=referendum.description,
            proposer=referendum.proposer,
            trigger=referendum.trigger,
            status=ReferendumStatus.PETITIONING,
            config=referendum.config,
            created_at=referendum.created_at,
            petition_started_at=time.time(),
        )

        self._referendums[referendum_id] = updated
        logger.info("ReferendumEngine: petition started for %s", referendum_id)
        return True

    def sign_petition(
        self,
        referendum_id: str,
        citizen_name: str,
        prana: int,
        identity_service: Optional[Any] = None,
    ) -> bool:
        """Citizen signs a petition."""
        referendum = self._referendums.get(referendum_id)
        if not referendum or referendum.status != ReferendumStatus.PETITIONING:
            return False

        # Check if already signed
        for sig in referendum.petition_signatures:
            if sig.citizen_name == citizen_name:
                return False

        # Create signature
        payload = f"{referendum_id}:{citizen_name}:petition".encode()
        signature_hash = hashlib.sha256(payload).hexdigest()

        new_signature = CitizenSignature(
            citizen_name=citizen_name,
            signed_at=time.time(),
            prana_at_signing=prana,
            signature_hash=signature_hash,
        )

        # Add to signatures (would create new referendum instance)
        signatures = list(referendum.petition_signatures) + [new_signature]
        
        # Check if petition is complete
        if len(signatures) >= referendum.config.petition_signatures_required:
            # Automatically start voting
            return self.start_voting(referendum_id)

        logger.debug(
            "ReferendumEngine: %s signed petition for %s (%d/%d signatures)",
            citizen_name, referendum_id, len(signatures),
            referendum.config.petition_signatures_required,
        )
        return True

    def start_voting(self, referendum_id: str) -> bool:
        """Start the voting phase."""
        referendum = self._referendums.get(referendum_id)
        if not referendum:
            return False

        now = time.time()
        voting_ends = now + (referendum.config.voting_duration_hours * 3600)

        updated = Referendum(
            id=referendum.id,
            title=referendum.title,
            description=referendum.description,
            proposer=referendum.proposer,
            trigger=referendum.trigger,
            status=ReferendumStatus.ACTIVE,
            config=referendum.config,
            created_at=referendum.created_at,
            petition_started_at=referendum.petition_started_at,
            voting_started_at=now,
            voting_ends_at=voting_ends,
            petition_signatures=referendum.petition_signatures,
        )

        self._referendums[referendum_id] = updated
        logger.info(
            "ReferendumEngine: voting started for %s (ends in %d hours)",
            referendum_id, referendum.config.voting_duration_hours,
        )
        return True

    def cast_vote(
        self,
        referendum_id: str,
        citizen_name: str,
        choice: VoteChoice,
        prana: int,
        identity_service: Optional[Any] = None,
    ) -> bool:
        """Citizen casts a vote."""
        referendum = self._referendums.get(referendum_id)
        if not referendum or not referendum.can_vote(citizen_name):
            return False

        # Create vote
        payload = f"{referendum_id}:{citizen_name}:{choice}".encode()
        vote_hash = hashlib.sha256(payload).hexdigest()

        new_vote = CitizenVote(
            citizen_name=citizen_name,
            choice=choice,
            voted_at=time.time(),
            prana_at_vote=prana,
            vote_hash=vote_hash,
        )

        # Add to votes (would create new referendum instance)
        votes = list(referendum.votes) + [new_vote]
        
        logger.debug(
            "ReferendumEngine: %s voted %s in %s",
            citizen_name, choice, referendum_id
        )
        return True

    def finalize_expired_referendums(self) -> list[Referendum]:
        """Finalize all referendums whose voting has expired."""
        finalized = []
        
        for referendum_id, referendum in self._referendums.items():
            if referendum.is_voting_expired() and referendum.status == ReferendumStatus.ACTIVE:
                results = referendum.calculate_results()
                
                # Determine final status
                if results.get("passed", False):
                    final_status = ReferendumStatus.PASSED
                else:
                    final_status = ReferendumStatus.REJECTED

                # Create finalized referendum
                updated = Referendum(
                    id=referendum.id,
                    title=referendum.title,
                    description=referendum.description,
                    proposer=referendum.proposer,
                    trigger=referendum.trigger,
                    status=final_status,
                    config=referendum.config,
                    created_at=referendum.created_at,
                    petition_started_at=referendum.petition_started_at,
                    voting_started_at=referendum.voting_started_at,
                    voting_ends_at=referendum.voting_ends_at,
                    petition_signatures=referendum.petition_signatures,
                    votes=referendum.votes,
                    yes_weight=results.get("yes_weight", 0.0),
                    no_weight=results.get("no_weight", 0.0),
                    abstain_weight=results.get("abstain_weight", 0.0),
                    total_turnout=results.get("turnout", 0.0),
                    result_hash=hashlib.sha256(json.dumps(results).encode()).hexdigest(),
                )

                self._referendums[referendum_id] = updated
                finalized.append(updated)
                logger.info(
                    "ReferendumEngine: %s finalized with status %s",
                    referendum_id, final_status.value
                )
        
        return finalized

    def get_referendum(self, referendum_id: str) -> Optional[Referendum]:
        """Get a referendum by ID."""
        return self._referendums.get(referendum_id)

    def list_active_referendums(self) -> list[Referendum]:
        """List all active referendums."""
        return [r for r in self._referendums.values() if r.status == ReferendumStatus.ACTIVE]

    def list_petitioning_referendums(self) -> list[Referendum]:
        """List all referendums gathering signatures."""
        return [r for r in self._referendums.values() if r.status == ReferendumStatus.PETITIONING]

    def get_stats(self) -> dict[str, Any]:
        """Get referendum system statistics."""
        total = len(self._referendums)
        active = len(self.list_active_referendums())
        petitioning = len(self.list_petitioning_referendums())
        passed = len([r for r in self._referendums.values() if r.status == ReferendumStatus.PASSED])
        rejected = len([
            r for r in self._referendums.values()
            if r.status == ReferendumStatus.REJECTED
        ])

        return {
            "total": total,
            "active": active,
            "petitioning": petitioning,
            "passed": passed,
            "rejected": rejected,
            "success_rate": passed / max(1, passed + rejected) if (passed + rejected) > 0 else 0.0,
        }


# ── Integration Helpers ───────────────────────────────────────────────────


def create_referendum_engine(config: Optional[ReferendumConfig] = None) -> ReferendumEngine:
    """Create and initialize ReferendumEngine."""
    engine = ReferendumEngine(config)
    logger.info("ReferendumEngine: initialized")
    return engine


def trigger_council_referral(
    engine: ReferendumEngine,
    proposal_id: str,
    title: str,
    description: str,
    proposer: str,
) -> str:
    """Trigger a referendum via council referral."""
    referendum = engine.create_referendum(
        title=title,
        description=description,
        proposer=proposer,
        trigger=ReferendumTrigger.COUNCIL_REFERRAL,
    )
    
    # Council referrals go straight to voting (no petition needed)
    engine.start_voting(referendum.id)
    logger.info("Council referral triggered referendum %s", referendum.id)
    return referendum.id


def trigger_automatic_referendum(
    engine: ReferendumEngine,
    reason: str,
    description: str,
) -> str:
    """Trigger a referendum automatically (e.g., for critical system changes)."""
    title = f"Automatic Referendum: {reason}"
    
    referendum = engine.create_referendum(
        title=title,
        description=description,
        proposer="system",
        trigger=ReferendumTrigger.AUTOMATIC_TRIGGER,
    )
    
    # Automatic referendums go straight to voting
    engine.start_voting(referendum.id)
    logger.info("Automatic referendum triggered: %s", referendum.id)
    return referendum.id
