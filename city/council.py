"""
CITY COUNCIL — Democratic Governance Layer
=============================================

SHARANAGATI (6) council seats. Deterministic prana-ranked elections.
Proposals voted by council, executed by SystemMayor.

Wired from steward-protocol:
- GuardianRouter: route_text() for proposal topic routing
- AntarangaRegistry: Resonance chamber reads for city health
- MahajanaSabha: Council of 12 governance status

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TypedDict

from vibe_core.mahamantra.protocols import MALA, SHARANAGATI

from config import get_config

logger = logging.getLogger("AGENT_CITY.COUNCIL")

# SSOT: Council seats = SHARANAGATI = KSHETRA // QUARTERS = 24 // 4
COUNCIL_SEATS: int = SHARANAGATI

# SSOT: Election cycle = MALA = 108 heartbeats
ELECTION_CYCLE: int = MALA

# Voting thresholds — sourced from config/city.yaml
_gov = get_config().get("governance", {})
DEMOCRATIC_THRESHOLD: float = _gov.get("democratic_threshold", 0.5)
SUPERMAJORITY_THRESHOLD: float = _gov.get("supermajority_threshold", 0.67)


class ProposalStatus(str, Enum):
    """Lifecycle of a governance proposal."""

    OPEN = "open"
    PASSED = "passed"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ProposalType(str, Enum):
    """Determines voting threshold."""

    POLICY = "policy"  # Simple majority (>50%)
    CONSTITUTIONAL = "constitutional"  # Supermajority (>67%)


class VoteChoice(str, Enum):
    """Vote options."""

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


class ElectionResult(TypedDict):
    """Result of a council election."""

    heartbeat: int
    elected_mayor: str | None
    council_seats: dict[int, str]
    candidates_ranked: list[dict]


class VoteRecord(TypedDict):
    """Single vote on a proposal."""

    voter: str
    choice: str
    prana_weight: int


@dataclass(frozen=True)
class Proposal:
    """A governance proposal submitted to the council.

    Frozen dataclass — votes append by creating new Proposal instances.
    Result hash = SHA-256 of tally data (tamper-proof).
    """

    id: str
    title: str
    description: str
    proposer: str
    proposal_type: ProposalType
    action: dict
    guardian_route: str
    route_score: float
    submitted_at: float
    status: ProposalStatus = ProposalStatus.OPEN
    votes: tuple[VoteRecord, ...] = ()
    result_hash: str = ""

    def threshold(self) -> float:
        """Voting threshold for this proposal type."""
        if self.proposal_type == ProposalType.CONSTITUTIONAL:
            return SUPERMAJORITY_THRESHOLD
        return DEMOCRATIC_THRESHOLD

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "proposer": self.proposer,
            "proposal_type": self.proposal_type.value,
            "action": self.action,
            "guardian_route": self.guardian_route,
            "route_score": self.route_score,
            "submitted_at": self.submitted_at,
            "status": self.status.value,
            "votes": list(self.votes),
            "result_hash": self.result_hash,
        }


@dataclass
class CityCouncil:
    """The City Council — SHARANAGATI (6) elected seats.

    Deterministic elections: same agents + same prana = same result.
    Council votes on proposals. SystemMayor executes approved ones.
    """

    _seats: dict[int, str] = field(default_factory=dict)
    _elected_mayor: str | None = None
    _proposals: dict[str, Proposal] = field(default_factory=dict)
    _next_proposal_num: int = 1
    _last_election_heartbeat: int = -ELECTION_CYCLE  # Force first election
    _state_path: Path | None = None

    def __post_init__(self) -> None:
        """Auto-load state from disk if state_path is set and exists."""
        if self._state_path is not None and self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                self._restore_from_dict(data)
                logger.info("Council state loaded from %s", self._state_path)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Council state load failed: %s", e)

    def _auto_save(self) -> None:
        """Persist state to disk after mutations (if state_path is set)."""
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(self.to_dict(), indent=2))

    def _restore_from_dict(self, data: dict) -> None:
        """Restore council state from serialized dict."""
        self._seats = {int(k): v for k, v in data.get("seats", {}).items()}
        self._elected_mayor = data.get("elected_mayor")
        self._next_proposal_num = data.get("next_proposal_num", 1)
        self._last_election_heartbeat = data.get(
            "last_election_heartbeat",
            -ELECTION_CYCLE,
        )
        # Restore proposals
        self._proposals = {}
        for pid, pdata in data.get("proposals", {}).items():
            self._proposals[pid] = Proposal(
                id=pdata["id"],
                title=pdata["title"],
                description=pdata.get("description", ""),
                proposer=pdata["proposer"],
                proposal_type=ProposalType(pdata["proposal_type"]),
                action=pdata["action"],
                guardian_route=pdata.get("guardian_route", ""),
                route_score=pdata.get("route_score", 0.0),
                submitted_at=pdata.get("submitted_at", 0.0),
                status=ProposalStatus(pdata["status"]),
                votes=tuple(pdata.get("votes", [])),
                result_hash=pdata.get("result_hash", ""),
            )

    @classmethod
    def from_dict(cls, data: dict, state_path: Path | None = None) -> CityCouncil:
        """Create a CityCouncil from a serialized dict."""
        council = cls(_state_path=state_path)
        council._restore_from_dict(data)
        return council

    # ── Elections ────────────────────────────────────────────────────

    def election_due(self, heartbeat_count: int) -> bool:
        """Check if election is due. Every ELECTION_CYCLE heartbeats."""
        if not self._seats:
            return True
        return (heartbeat_count - self._last_election_heartbeat) >= ELECTION_CYCLE

    def run_election(
        self,
        candidates: list[dict],
        heartbeat_count: int,
    ) -> ElectionResult:
        """Run deterministic council election.

        Candidates sorted by (prana DESC, name ASC) for determinism.
        Top COUNCIL_SEATS candidates fill seats.
        Seat 0 = ElectedMayor (highest prana citizen).

        Each candidate dict: {name, prana, guardian, position}.
        """
        eligible = [c for c in candidates if c.get("prana", 0) > 0]
        eligible.sort(key=lambda c: (-c.get("rank_score", c["prana"] / 21600), c["name"]))

        new_seats: dict[int, str] = {}
        for i, candidate in enumerate(eligible[:COUNCIL_SEATS]):
            new_seats[i] = candidate["name"]

        new_mayor = new_seats.get(0)

        self._seats = new_seats
        self._elected_mayor = new_mayor
        self._last_election_heartbeat = heartbeat_count

        result: ElectionResult = {
            "heartbeat": heartbeat_count,
            "elected_mayor": new_mayor,
            "council_seats": dict(new_seats),
            "candidates_ranked": [
                {
                    "name": c["name"],
                    "prana": c["prana"],
                    "guardian": c.get("guardian", ""),
                    "rank": i,
                }
                for i, c in enumerate(eligible[: COUNCIL_SEATS * 2])
            ],
        }

        logger.info(
            "Election complete: mayor=%s, %d seats filled",
            new_mayor,
            len(new_seats),
        )
        self._auto_save()
        return result

    # ── Proposals ───────────────────────────────────────────────────

    def propose(
        self,
        title: str,
        description: str,
        proposer: str,
        proposal_type: ProposalType,
        action: dict,
        timestamp: float,
    ) -> Proposal | None:
        """Submit a proposal. Only council members can propose.

        Returns None if proposer is not on council.
        """
        if proposer not in self._seats.values():
            logger.warning("Proposal rejected: %s not on council", proposer)
            return None

        guardian_name = ""
        route_score = 0.0
        try:
            from vibe_core.mahamantra.substrate.services.guardian_router import route_text

            routes = route_text(title, top_n=1)
            if routes:
                guardian_name = routes[0].guardian.name
                route_score = routes[0].score
        except Exception as e:
            logger.warning("Guardian routing failed: %s", e)

        proposal_id = f"GOV-{self._next_proposal_num:04d}"
        self._next_proposal_num += 1

        proposal = Proposal(
            id=proposal_id,
            title=title,
            description=description,
            proposer=proposer,
            proposal_type=proposal_type,
            action=action,
            guardian_route=guardian_name,
            route_score=route_score,
            submitted_at=timestamp,
        )

        self._proposals[proposal_id] = proposal
        logger.info("Proposal %s by %s: %s", proposal_id, proposer, title)
        self._auto_save()
        return proposal

    def vote(
        self,
        proposal_id: str,
        voter: str,
        choice: VoteChoice,
        prana_weight: int,
    ) -> bool:
        """Cast a vote. Only council members can vote.

        Returns True if vote recorded, False if rejected.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.OPEN:
            return False
        if voter not in self._seats.values():
            return False

        existing_voters = {v["voter"] for v in proposal.votes}
        if voter in existing_voters:
            return False

        record: VoteRecord = {
            "voter": voter,
            "choice": choice.value,
            "prana_weight": prana_weight,
        }

        new_votes = proposal.votes + (record,)
        updated = Proposal(
            id=proposal.id,
            title=proposal.title,
            description=proposal.description,
            proposer=proposal.proposer,
            proposal_type=proposal.proposal_type,
            action=proposal.action,
            guardian_route=proposal.guardian_route,
            route_score=proposal.route_score,
            submitted_at=proposal.submitted_at,
            status=proposal.status,
            votes=new_votes,
        )
        self._proposals[proposal_id] = updated
        self._auto_save()
        return True

    def tally(self, proposal_id: str) -> Proposal | None:
        """Tally votes and update proposal status.

        Uses prana-weighted voting. Returns updated proposal or None.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.OPEN:
            return None

        yes_weight = sum(v["prana_weight"] for v in proposal.votes if v["choice"] == "yes")
        no_weight = sum(v["prana_weight"] for v in proposal.votes if v["choice"] == "no")
        total_weight = yes_weight + no_weight

        if total_weight == 0:
            return proposal

        yes_ratio = yes_weight / total_weight
        threshold = proposal.threshold()
        passed = yes_ratio > threshold

        tally_data = json.dumps(
            {
                "proposal_id": proposal.id,
                "yes_weight": yes_weight,
                "no_weight": no_weight,
                "threshold": threshold,
                "passed": passed,
            },
            sort_keys=True,
        )
        result_hash = hashlib.sha256(tally_data.encode()).hexdigest()

        new_status = ProposalStatus.PASSED if passed else ProposalStatus.REJECTED

        updated = Proposal(
            id=proposal.id,
            title=proposal.title,
            description=proposal.description,
            proposer=proposal.proposer,
            proposal_type=proposal.proposal_type,
            action=proposal.action,
            guardian_route=proposal.guardian_route,
            route_score=proposal.route_score,
            submitted_at=proposal.submitted_at,
            status=new_status,
            votes=proposal.votes,
            result_hash=result_hash,
        )
        self._proposals[proposal_id] = updated

        logger.info(
            "Tally %s: %s (yes=%d no=%d ratio=%.2f threshold=%.2f)",
            proposal.id,
            new_status.value,
            yes_weight,
            no_weight,
            yes_ratio,
            threshold,
        )
        self._auto_save()
        return updated

    # ── Queries ─────────────────────────────────────────────────────

    @property
    def elected_mayor(self) -> str | None:
        """The current elected mayor (seat 0)."""
        return self._elected_mayor

    @property
    def seats(self) -> dict[int, str]:
        """Current council seat assignments."""
        return dict(self._seats)

    @property
    def member_count(self) -> int:
        """Number of filled seats."""
        return len(self._seats)

    def is_member(self, name: str) -> bool:
        """Check if an agent is on the council."""
        return name in self._seats.values()

    def get_open_proposals(self) -> list[Proposal]:
        """Proposals awaiting votes."""
        return [p for p in self._proposals.values() if p.status == ProposalStatus.OPEN]

    def get_passed_proposals(self) -> list[Proposal]:
        """Proposals that passed and await execution."""
        return [p for p in self._proposals.values() if p.status == ProposalStatus.PASSED]

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Look up a proposal by ID."""
        return self._proposals.get(proposal_id)

    def mark_executed(self, proposal_id: str) -> None:
        """Mark a passed proposal as executed."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != ProposalStatus.PASSED:
            return
        updated = Proposal(
            id=proposal.id,
            title=proposal.title,
            description=proposal.description,
            proposer=proposal.proposer,
            proposal_type=proposal.proposal_type,
            action=proposal.action,
            guardian_route=proposal.guardian_route,
            route_score=proposal.route_score,
            submitted_at=proposal.submitted_at,
            status=ProposalStatus.EXECUTED,
            votes=proposal.votes,
            result_hash=proposal.result_hash,
        )
        self._proposals[proposal_id] = updated
        self._auto_save()

    def query_guardians(self, text: str) -> list[dict]:
        """Route text through Guardian Router for topic analysis."""
        try:
            from vibe_core.mahamantra.substrate.services.guardian_router import route_text

            routes = route_text(text, top_n=3)
            return [
                {
                    "guardian": r.guardian.name,
                    "function": r.guardian.function,
                    "score": round(r.score, 4),
                }
                for r in routes
            ]
        except Exception as e:
            logger.warning("Guardian query failed: %s", e)
            return []

    def query_antaranga(self) -> dict:
        """Query the Mahamantra Antaranga for city health metrics."""
        try:
            from vibe_core.mahamantra.substrate.cell_system.antaranga import AntarangaRegistry

            antaranga = AntarangaRegistry()
            return {
                "active_slots": antaranga.active_count(),
                "total_prana": antaranga.total_prana(),
            }
        except Exception as e:
            logger.warning("Antaranga query failed: %s", e)
            return {}

    def query_sabha(self) -> dict:
        """Query the Mahajana Sabha for governance status."""
        try:
            from vibe_core.protocols.mahajanas.sabha import get_sabha

            sabha = get_sabha()
            status = sabha.get_status()
            return {
                "total_chants": status.total_chants,
                "current_position": status.current_position,
                "resonance": status.resonance,
                "active_mahajanas": len(sabha.get_active_mahajanas()),
            }
        except Exception as e:
            logger.warning("Sabha query failed: %s", e)
            return {}

    def to_dict(self) -> dict:
        """Serialize council state."""
        return {
            "seats": self._seats,
            "elected_mayor": self._elected_mayor,
            "proposals": {k: v.to_dict() for k, v in self._proposals.items()},
            "next_proposal_num": self._next_proposal_num,
            "last_election_heartbeat": self._last_election_heartbeat,
        }
