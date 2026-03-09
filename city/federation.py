"""
FEDERATION RELAY & DIPLOMACY — Cross-Repo Communication
=========================================================

Bidirectional federation between agent-city instances and mothership (steward-protocol).

MOKSHA: Mayor saves CityReport locally (audit trail) + posts via MoltbookBridge
GENESIS: Mayor reads FederationDirectives from data/federation/directives/

Social channel: MoltbookBridge posts to m/agent-city (primary)
Directive intake: file-based (mothership workflow commits JSON files)

Diplomacy: Peer-to-peer city recognition, treaty negotiation, and alliance management.
Each fork starts UNKNOWN and progresses through diplomatic states based on
verified interactions. Trust is earned through constitutional compatibility,
contract health, and consistent heartbeat exchange.

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
from pathlib import Path

from config import get_config

logger = logging.getLogger("AGENT_CITY.FEDERATION")

# Default mothership — sourced from config/city.yaml
_fed_cfg = get_config().get("federation", {})
DEFAULT_MOTHERSHIP: str = _fed_cfg.get("mothership_repo", "kimeisele/steward-protocol")


@dataclass(frozen=True)
class CityReport:
    """Status report sent to mothership in MOKSHA."""

    heartbeat: int
    timestamp: float
    population: int
    alive: int
    dead: int
    elected_mayor: str | None
    council_seats: int
    open_proposals: int
    chain_valid: bool
    recent_actions: list[str]
    contract_status: dict
    mission_results: list[dict]
    directive_acks: list[str]
    pr_results: list[dict] = field(default_factory=list)  # PRs from KARMA issue/exec missions
    active_campaigns: list[dict] = field(default_factory=list)  # Strategic campaign summaries

    def to_dict(self) -> dict:
        return {
            "heartbeat": self.heartbeat,
            "timestamp": self.timestamp,
            "population": self.population,
            "alive": self.alive,
            "dead": self.dead,
            "elected_mayor": self.elected_mayor,
            "council_seats": self.council_seats,
            "open_proposals": self.open_proposals,
            "chain_valid": self.chain_valid,
            "recent_actions": self.recent_actions,
            "contract_status": self.contract_status,
            "mission_results": self.mission_results,
            "directive_acks": self.directive_acks,
            "pr_results": self.pr_results,
            "active_campaigns": self.active_campaigns,
        }


@dataclass(frozen=True)
class FederationDirective:
    """Instruction from mothership, read from directive files."""

    id: str
    directive_type: str  # "create_mission", "register_agent", "freeze_agent", "policy_update"
    params: dict
    timestamp: float
    source: str  # "mothership" | "council"


@dataclass
class FederationRelay:
    """Cross-repo federation relay.

    Saves CityReports locally (audit trail). Social posting via MoltbookBridge.
    Reads directives from data/federation/directives/ (file-based intake).
    """

    _mothership_repo: str = DEFAULT_MOTHERSHIP
    _dry_run: bool = False
    _directives_dir: Path = field(default=Path("data/federation/directives"))
    _reports_dir: Path = field(default=Path("data/federation/reports"))
    _last_report: dict = field(default_factory=dict)
    _report_log: list[dict] = field(default_factory=list)
    _acknowledged: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._directives_dir.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def send_report(self, report: CityReport) -> bool:
        """Save city status report locally (audit trail).

        Social posting handled by MoltbookBridge in MOKSHA phase.
        """
        payload = report.to_dict()
        self._last_report = payload

        # Save report locally for audit trail
        report_file = self._reports_dir / f"report_{report.heartbeat}.json"
        report_file.write_text(json.dumps(payload, indent=2))
        self._report_log.append(payload)

        # Cap report log
        _log_max = _fed_cfg.get("report_log_max", 50)
        _log_trim = _fed_cfg.get("report_log_trim", 25)
        if len(self._report_log) > _log_max:
            self._report_log = self._report_log[-_log_trim:]

        logger.info(
            "Federation: saved report (heartbeat=%d, pop=%d)",
            report.heartbeat,
            report.population,
        )
        self._acknowledged.clear()
        return True

    def check_directives(self) -> list[FederationDirective]:
        """Read pending directives from the directives directory.

        Reads all .json files (not .done). Returns parsed directives.
        """
        directives: list[FederationDirective] = []

        if not self._directives_dir.exists():
            return directives

        for path in sorted(self._directives_dir.glob("*.json")):
            if path.suffix == ".json" and not path.name.endswith(".done.json"):
                try:
                    data = json.loads(path.read_text())
                    directive = FederationDirective(
                        id=data.get("id", path.stem),
                        directive_type=data.get("directive_type", "unknown"),
                        params=data.get("params", {}),
                        timestamp=data.get("timestamp", 0.0),
                        source=data.get("source", "mothership"),
                    )
                    directives.append(directive)
                    logger.info(
                        "Federation: read directive %s (%s)",
                        directive.id,
                        directive.directive_type,
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(
                        "Federation: bad directive file %s: %s",
                        path.name,
                        e,
                    )

        return directives

    def acknowledge_directive(self, directive_id: str) -> bool:
        """Mark a directive as processed. Renames .json to .json.done."""
        self._acknowledged.append(directive_id)

        # Find and rename the file
        for path in self._directives_dir.glob("*.json"):
            if path.name.endswith(".done.json"):
                continue
            try:
                data = json.loads(path.read_text())
                if data.get("id", path.stem) == directive_id:
                    done_path = path.with_suffix(".json.done")
                    path.rename(done_path)
                    logger.info("Federation: acknowledged directive %s", directive_id)
                    return True
            except (json.JSONDecodeError, KeyError):
                continue

        # File not found by ID — try by stem
        path = self._directives_dir / f"{directive_id}.json"
        if path.exists():
            done_path = path.with_suffix(".json.done")
            path.rename(done_path)
            logger.info("Federation: acknowledged directive %s (by stem)", directive_id)
            return True

        return False

    @property
    def last_report(self) -> dict:
        """Last sent report payload."""
        return dict(self._last_report)

    @property
    def pending_acks(self) -> list[str]:
        """Directive IDs acknowledged since last report."""
        return list(self._acknowledged)

    def stats(self) -> dict:
        """Federation relay statistics."""
        pending = (
            len(list(self._directives_dir.glob("*.json"))) if self._directives_dir.exists() else 0
        )
        done = (
            len(list(self._directives_dir.glob("*.done")))
            + len(list(self._directives_dir.glob("*.done.json")))
            if self._directives_dir.exists()
            else 0
        )
        return {
            "mothership": self._mothership_repo,
            "dry_run": self._dry_run,
            "reports_sent": len(self._report_log),
            "pending_directives": pending,
            "processed_directives": done,
            "last_report_heartbeat": self._last_report.get("heartbeat"),
        }


# ═════════════════════════════════════════════════════════════════════════════
# DIPLOMATIC STATE — Peer-to-Peer City Federation
# ═════════════════════════════════════════════════════════════════════════════


class DiplomaticState(str, Enum):
    """Lifecycle state of a city-to-city relationship.

    UNKNOWN → DISCOVERED → RECOGNIZED → ALLIED → FEDERATED
                                             ↕
                                         SUSPENDED → SEVERED

    Progression requires verified interactions:
    - DISCOVERED: First city_report received and parsed successfully
    - RECOGNIZED: Constitution hash matches, contracts pass, council approves
    - ALLIED: Treaty signed, bidirectional Nadi open
    - FEDERATED: Deep integration — agent migration, economic bridge, shared governance
    - SUSPENDED: Treaty violation detected, under review
    - SEVERED: Diplomatic break, all channels closed
    """

    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    RECOGNIZED = "recognized"
    ALLIED = "allied"
    FEDERATED = "federated"
    SUSPENDED = "suspended"
    SEVERED = "severed"


# Valid state transitions
_DIPLOMATIC_TRANSITIONS: dict[DiplomaticState, set[DiplomaticState]] = {
    DiplomaticState.UNKNOWN: {DiplomaticState.DISCOVERED},
    DiplomaticState.DISCOVERED: {DiplomaticState.RECOGNIZED, DiplomaticState.SEVERED},
    DiplomaticState.RECOGNIZED: {DiplomaticState.ALLIED, DiplomaticState.SUSPENDED},
    DiplomaticState.ALLIED: {DiplomaticState.FEDERATED, DiplomaticState.SUSPENDED},
    DiplomaticState.FEDERATED: {DiplomaticState.SUSPENDED},
    DiplomaticState.SUSPENDED: {
        DiplomaticState.RECOGNIZED,  # restored after review
        DiplomaticState.SEVERED,  # permanent break
    },
    DiplomaticState.SEVERED: set(),  # terminal — no recovery
}


@dataclass(frozen=True)
class CityTreaty:
    """Agreement between two federated cities.

    Defines the terms of cooperation: visa reciprocity, economic exchange,
    agent migration rules, and knowledge sharing scope.
    """

    city_a: str  # repo identifier (e.g., "kimeisele/agent-city")
    city_b: str  # repo identifier (e.g., "user/agent-city-medical")
    signed_at: float  # UTC timestamp
    treaty_id: str = ""  # SHA-256(city_a:city_b:signed_at)[:16]

    # Visa reciprocity: which classes are honored across cities
    visa_reciprocity: tuple[str, ...] = ("temporary", "worker")

    # Economic bridge
    prana_exchange_enabled: bool = False
    prana_exchange_rate: float = 1.0  # city_b prana per city_a prana

    # Agent migration
    agent_migration_enabled: bool = False
    migration_visa_class: str = "temporary"  # default visa for migrants

    # Knowledge sharing
    wiki_propagation: bool = False

    def __post_init__(self) -> None:
        if not self.treaty_id:
            tid = hashlib.sha256(
                f"{self.city_a}:{self.city_b}:{self.signed_at}".encode()
            ).hexdigest()[:16]
            object.__setattr__(self, "treaty_id", tid)

    def to_dict(self) -> dict:
        return {
            "city_a": self.city_a,
            "city_b": self.city_b,
            "signed_at": self.signed_at,
            "treaty_id": self.treaty_id,
            "visa_reciprocity": list(self.visa_reciprocity),
            "prana_exchange_enabled": self.prana_exchange_enabled,
            "prana_exchange_rate": self.prana_exchange_rate,
            "agent_migration_enabled": self.agent_migration_enabled,
            "migration_visa_class": self.migration_visa_class,
            "wiki_propagation": self.wiki_propagation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CityTreaty:
        return cls(
            city_a=data["city_a"],
            city_b=data["city_b"],
            signed_at=data["signed_at"],
            treaty_id=data.get("treaty_id", ""),
            visa_reciprocity=tuple(data.get("visa_reciprocity", ("temporary", "worker"))),
            prana_exchange_enabled=data.get("prana_exchange_enabled", False),
            prana_exchange_rate=data.get("prana_exchange_rate", 1.0),
            agent_migration_enabled=data.get("agent_migration_enabled", False),
            migration_visa_class=data.get("migration_visa_class", "temporary"),
            wiki_propagation=data.get("wiki_propagation", False),
        )


@dataclass(frozen=True)
class PeerCity:
    """A known city in the federation."""

    repo: str  # GitHub repo identifier (e.g., "user/agent-city-fork")
    state: DiplomaticState
    discovered_at: float  # UTC timestamp of first contact
    last_report_at: float = 0.0  # Last city_report received
    constitution_hash: str = ""  # SHA-256 of their CONSTITUTION.md
    population: int = 0
    contracts_passing: bool = False
    heartbeat_count: int = 0
    treaty_id: str = ""  # Active treaty (empty if none)
    remarks: str = ""

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "state": self.state.value,
            "discovered_at": self.discovered_at,
            "last_report_at": self.last_report_at,
            "constitution_hash": self.constitution_hash,
            "population": self.population,
            "contracts_passing": self.contracts_passing,
            "heartbeat_count": self.heartbeat_count,
            "treaty_id": self.treaty_id,
            "remarks": self.remarks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PeerCity:
        return cls(
            repo=data["repo"],
            state=DiplomaticState(data.get("state", "unknown")),
            discovered_at=data.get("discovered_at", 0.0),
            last_report_at=data.get("last_report_at", 0.0),
            constitution_hash=data.get("constitution_hash", ""),
            population=data.get("population", 0),
            contracts_passing=data.get("contracts_passing", False),
            heartbeat_count=data.get("heartbeat_count", 0),
            treaty_id=data.get("treaty_id", ""),
            remarks=data.get("remarks", ""),
        )


@dataclass
class DiplomacyLedger:
    """Manages diplomatic relationships with peer cities.

    File-backed ledger stored in data/federation/diplomacy.json.
    Integrates with FederationRelay (not a parallel structure).
    """

    _federation_dir: Path = field(default=Path("data/federation"))
    _peers: dict[str, PeerCity] = field(default_factory=dict)
    _treaties: dict[str, CityTreaty] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._federation_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    @property
    def _ledger_path(self) -> Path:
        return self._federation_dir / "diplomacy.json"

    # ── Peer Discovery & State Management ─────────────────────────────

    def discover(self, repo: str, report_payload: dict) -> PeerCity:
        """Register first contact with a peer city.

        Called when a city_report arrives from an unknown source.
        Transitions: UNKNOWN → DISCOVERED.
        """
        now = time.time()
        if repo in self._peers:
            # Update existing peer with fresh report data
            return self._update_from_report(repo, report_payload)

        peer = PeerCity(
            repo=repo,
            state=DiplomaticState.DISCOVERED,
            discovered_at=now,
            last_report_at=now,
            population=report_payload.get("population", 0),
            contracts_passing=report_payload.get("chain_valid", False),
            heartbeat_count=report_payload.get("heartbeat", 0),
            constitution_hash=report_payload.get("constitution_hash", ""),
        )
        self._peers[repo] = peer
        self._save()
        logger.info("Diplomacy: discovered peer city %s", repo)
        return peer

    def _update_from_report(self, repo: str, report_payload: dict) -> PeerCity:
        """Update peer city data from an incoming city_report."""
        old = self._peers[repo]
        updated = PeerCity(
            repo=old.repo,
            state=old.state,
            discovered_at=old.discovered_at,
            last_report_at=time.time(),
            constitution_hash=report_payload.get("constitution_hash", old.constitution_hash),
            population=report_payload.get("population", old.population),
            contracts_passing=report_payload.get("chain_valid", old.contracts_passing),
            heartbeat_count=report_payload.get("heartbeat", old.heartbeat_count),
            treaty_id=old.treaty_id,
            remarks=old.remarks,
        )
        self._peers[repo] = updated
        self._save()
        return updated

    def transition(self, repo: str, new_state: DiplomaticState, remarks: str = "") -> PeerCity:
        """Transition a peer city to a new diplomatic state.

        Validates the transition against _DIPLOMATIC_TRANSITIONS.
        Raises ValueError on invalid transition.
        """
        if repo not in self._peers:
            raise ValueError(f"Unknown peer city: {repo}")

        old = self._peers[repo]
        allowed = _DIPLOMATIC_TRANSITIONS.get(old.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {old.state.value} → {new_state.value} "
                f"(allowed: {[s.value for s in allowed]})"
            )

        updated = PeerCity(
            repo=old.repo,
            state=new_state,
            discovered_at=old.discovered_at,
            last_report_at=old.last_report_at,
            constitution_hash=old.constitution_hash,
            population=old.population,
            contracts_passing=old.contracts_passing,
            heartbeat_count=old.heartbeat_count,
            treaty_id=old.treaty_id,
            remarks=remarks or old.remarks,
        )
        self._peers[repo] = updated
        self._save()
        logger.info(
            "Diplomacy: %s transitioned %s → %s",
            repo, old.state.value, new_state.value,
        )
        return updated

    def sign_treaty(self, treaty: CityTreaty) -> CityTreaty:
        """Register a signed treaty between two cities.

        Both cities must be ALLIED or FEDERATED.
        """
        # Validate at least one side is this city's peer
        peer_repo = treaty.city_b  # convention: city_a = self, city_b = peer
        if peer_repo in self._peers:
            peer = self._peers[peer_repo]
            if peer.state not in (DiplomaticState.ALLIED, DiplomaticState.FEDERATED):
                raise ValueError(
                    f"Cannot sign treaty with {peer_repo}: state is {peer.state.value}, "
                    f"need allied or federated"
                )
            # Bind treaty to peer
            updated = PeerCity(
                repo=peer.repo,
                state=peer.state,
                discovered_at=peer.discovered_at,
                last_report_at=peer.last_report_at,
                constitution_hash=peer.constitution_hash,
                population=peer.population,
                contracts_passing=peer.contracts_passing,
                heartbeat_count=peer.heartbeat_count,
                treaty_id=treaty.treaty_id,
                remarks=peer.remarks,
            )
            self._peers[peer_repo] = updated

        self._treaties[treaty.treaty_id] = treaty
        self._save()
        logger.info(
            "Diplomacy: treaty %s signed between %s and %s",
            treaty.treaty_id, treaty.city_a, treaty.city_b,
        )
        return treaty

    # ── Queries ───────────────────────────────────────────────────────

    def get_peer(self, repo: str) -> PeerCity | None:
        """Get peer city by repo identifier."""
        return self._peers.get(repo)

    def get_treaty(self, treaty_id: str) -> CityTreaty | None:
        """Get treaty by ID."""
        return self._treaties.get(treaty_id)

    def get_treaty_with(self, repo: str) -> CityTreaty | None:
        """Get active treaty with a specific peer city."""
        peer = self._peers.get(repo)
        if peer and peer.treaty_id:
            return self._treaties.get(peer.treaty_id)
        return None

    def list_peers(self, state: DiplomaticState | None = None) -> list[PeerCity]:
        """List all known peer cities, optionally filtered by state."""
        peers = list(self._peers.values())
        if state is not None:
            peers = [p for p in peers if p.state == state]
        return peers

    def list_allies(self) -> list[PeerCity]:
        """List cities in ALLIED or FEDERATED state."""
        return [
            p for p in self._peers.values()
            if p.state in (DiplomaticState.ALLIED, DiplomaticState.FEDERATED)
        ]

    def stats(self) -> dict:
        """Diplomacy statistics."""
        state_counts: dict[str, int] = {}
        for peer in self._peers.values():
            state_counts[peer.state.value] = state_counts.get(peer.state.value, 0) + 1
        return {
            "total_peers": len(self._peers),
            "total_treaties": len(self._treaties),
            "allies": len(self.list_allies()),
            "by_state": state_counts,
        }

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        """Load ledger from disk."""
        if not self._ledger_path.exists():
            return
        try:
            data = json.loads(self._ledger_path.read_text())
            for pd in data.get("peers", []):
                peer = PeerCity.from_dict(pd)
                self._peers[peer.repo] = peer
            for td in data.get("treaties", []):
                treaty = CityTreaty.from_dict(td)
                self._treaties[treaty.treaty_id] = treaty
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Diplomacy: failed to load ledger: %s", e)

    def _save(self) -> None:
        """Save ledger to disk (atomic write)."""
        data = {
            "peers": [p.to_dict() for p in self._peers.values()],
            "treaties": [t.to_dict() for t in self._treaties.values()],
        }
        temp = self._ledger_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2))
        temp.replace(self._ledger_path)
