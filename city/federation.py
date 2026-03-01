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
