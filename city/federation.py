"""
FEDERATION RELAY — Cross-Repo Communication
=============================================

Bidirectional federation between agent-city and mothership (steward-protocol).

MOKSHA: Mayor saves CityReport locally (audit trail) + posts via MoltbookBridge
GENESIS: Mayor reads FederationDirectives from data/federation/directives/

Social channel: MoltbookBridge posts to m/agent-city (primary)
Directive intake: file-based (mothership workflow commits JSON files)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
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
    Reads federation health from steward's .steward/federation_health.json.
    """

    _mothership_repo: str = DEFAULT_MOTHERSHIP
    _dry_run: bool = False
    _directives_dir: Path = field(default=Path("data/federation/directives"))
    _reports_dir: Path = field(default=Path("data/federation/reports"))
    _health_path: Path = field(default=Path("data/federation/steward_health.json"))
    _last_report: dict = field(default_factory=dict)
    _last_health: dict = field(default_factory=dict)
    _report_log: list[dict] = field(default_factory=list)
    _acknowledged: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._directives_dir.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def _get_node_id(self) -> str:
        """Lese Node-ID aus der peer.json Datei."""
        peer_path = self._directives_dir.parent / "peer.json"
        if not peer_path.exists():
            return "unknown"
        try:
            with open(peer_path, 'r') as f:
                data = json.load(f)
            return data.get("identity", {}).get("node_id", "unknown")
        except (json.JSONDecodeError, OSError):
            return "unknown"

    def _send_heartbeat_via_nadi(self, report: CityReport) -> None:
        """Sende Heartbeat via NADI Outbox an den Steward."""
        outbox_path = self._directives_dir.parent / "nadi_outbox.json"
        
        # Lade bestehende Outbox oder initialisiere leere Liste
        try:
            if outbox_path.exists():
                outbox_data = json.loads(outbox_path.read_text())
                if not isinstance(outbox_data, list):
                    outbox_data = []
            else:
                outbox_data = []
        except (json.JSONDecodeError, OSError):
            outbox_data = []
        
        # Erstelle Heartbeat-Nachricht
        heartbeat_msg = {
            "type": "heartbeat",
            "timestamp": report.timestamp,
            "heartbeat": report.heartbeat,
            "node_id": self._get_node_id(),
            "population": report.population,
            "alive": report.alive,
            "dead": report.dead,
            "elected_mayor": report.elected_mayor,
            "chain_valid": report.chain_valid,
            "source": "agent-city",
            "directive_acks": report.directive_acks,
            "contract_status": report.contract_status,
            "mission_results": len(report.mission_results)
        }
        
        # Füge Nachricht zur Outbox hinzu
        outbox_data.append(heartbeat_msg)
        
        # Speichere Outbox zurück
        try:
            outbox_path.write_text(json.dumps(outbox_data, indent=2))
            logger.info(
                "Federation: Heartbeat via NADI gesendet (heartbeat=%d, node_id=%s)",
                report.heartbeat, self._get_node_id()
            )
        except OSError as e:
            logger.warning("Federation: Konnte NADI Outbox nicht schreiben: %s", e)

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
        
        # Sende Heartbeat via NADI an den Steward
        self._send_heartbeat_via_nadi(report)
        
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

    def read_federation_health(self) -> dict:
        """Read federation health from steward's federation_health.json.

        Returns cached health data if the file hasn't changed.
        This data is used by GovernanceLayer to incorporate federation
        health into civic decisions (e.g. degraded steward → local safety mode).
        """
        if not self._health_path.exists():
            return self._last_health

        try:
            data = json.loads(self._health_path.read_text())
            if isinstance(data, dict):
                prev_hb = self._last_health.get("heartbeat")
                new_hb = data.get("heartbeat")
                self._last_health = data
                if new_hb != prev_hb:
                    logger.info(
                        "Federation: health updated (steward hb %s→%s, repos=%d)",
                        prev_hb, new_hb, len(data.get("repos", {})),
                    )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Federation: failed to read health: %s", e)

        return self._last_health

    @property
    def federation_health(self) -> dict:
        """Last read federation health snapshot."""
        return dict(self._last_health)

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
        health = self._last_health
        return {
            "mothership": self._mothership_repo,
            "dry_run": self._dry_run,
            "reports_sent": len(self._report_log),
            "pending_directives": pending,
            "processed_directives": done,
            "last_report_heartbeat": self._last_report.get("heartbeat"),
            "federation_health": {
                "available": bool(health),
                "steward_heartbeat": health.get("heartbeat"),
                "repos_tracked": len(health.get("repos", {})),
            },
        }
