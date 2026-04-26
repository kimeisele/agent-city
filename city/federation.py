"""
FEDERATION RELAY — Cross-Repo Communication
=============================================

Bidirectional federation between agent-city and mothership (steward-protocol).

MOKSHA: Mayor saves CityReport locally (audit trail) + posts via MoltbookBridge
GENESIS: Mayor reads FederationDirectives from data/federation/directives/

Social channel: MoltbookBridge posts to m/agent-city (primary)
Directive intake: file-based (mothership workflow commits JSON files)

------------------------------------------------------------------------------
CANONICAL WIRE FORMAT for outbound NADI messages (must match
steward.federation_crypto.verify_payload_signature):

    payload_hash  := sha256(json.dumps(msg_without_sig_fields, sort_keys=True))
                     stored as a HEX-STRING.
    signature     := base64( ed25519_sign( payload_hash.encode("utf-8") ) )

    Outbound shape:
        { ...message fields...,
          "payload_hash": "<hex sha256>",
          "signature":    "<base64 ed25519 sig>" }

    The verifier on the steward side resolves the signer's public key by
    looking up `source` in verified_agents.json, so the message does NOT
    carry signer_key/signer_node fields.
------------------------------------------------------------------------------

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
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
    _node_identity: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._directives_dir.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def _load_node_keys(self) -> object | None:
        """Load NodeIdentity from NODE_PRIVATE_KEY env (cached).

        Returns None if env is unset or malformed — outbound messages will then
        be sent unsigned and the receiving gateway will reject them.
        """
        if self._node_identity is not None:
            return self._node_identity
        env_key = (os.environ.get("NODE_PRIVATE_KEY") or "").strip()
        if not env_key:
            logger.warning("Federation: NODE_PRIVATE_KEY missing — outbound messages will be unsigned")
            return None
        try:
            from city.node_identity import (
                Ed25519PrivateKey,
                NodeIdentity,
                derive_node_id,
                serialization,
            )
            raw = bytes.fromhex(env_key)
            if len(raw) != 32:
                raise ValueError(f"expected 32 raw bytes, got {len(raw)}")
            sk = Ed25519PrivateKey.from_private_bytes(raw)
            pub_hex = sk.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ).hex()
            self._node_identity = NodeIdentity(derive_node_id(pub_hex), raw.hex(), pub_hex)
            return self._node_identity
        except (ValueError, TypeError, ImportError) as e:
            logger.error("Federation: failed to load NODE_PRIVATE_KEY: %s", e)
            return None

    def _sign_payload(self, message: dict) -> dict:
        """Attach Ed25519 signature to a federation message (canonical format).

        Wire format (must stay in lockstep with steward.federation_crypto):
            payload_hash := sha256(sorted-keys JSON of message minus sig fields),
                            hex digest as a string
            signature    := base64( Ed25519_sign( payload_hash.encode("utf-8") ) )

        Returns the message with two extra fields: payload_hash and signature.
        If no NodeIdentity is available, the message is returned unsigned and
        the gateway will reject it — fail-loud rather than silently bypass.
        """
        identity = self._load_node_keys()
        if identity is None:
            return message
        canonical = {k: v for k, v in message.items() if k not in ("payload_hash", "signature")}
        canonical_bytes = json.dumps(canonical, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(canonical_bytes).hexdigest()
        sig_hex = identity.sign(payload_hash.encode("utf-8"))
        signature_b64 = base64.b64encode(bytes.fromhex(sig_hex)).decode("ascii")
        return {**canonical, "payload_hash": payload_hash, "signature": signature_b64}

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

    def _get_agent_id(self) -> str:
        """Lese Agent-ID (city_id) aus der peer.json Datei."""
        peer_path = self._directives_dir.parent / "peer.json"
        if not peer_path.exists():
            return "unknown"
        try:
            with open(peer_path, 'r') as f:
                data = json.load(f)
            return data.get("identity", {}).get("city_id", "unknown")
        except (json.JSONDecodeError, OSError):
            return "unknown"

    def _read_outbox(self, outbox_path: Path) -> list:
        """Read outbox JSON list, returning [] on any error."""
        try:
            if outbox_path.exists():
                content = outbox_path.read_text()
                if content.strip():
                    data = json.loads(content)
                    if isinstance(data, list):
                        return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Federation: Fehler beim Lesen der NADI Outbox: %s. Starte mit leerer Outbox.", e)
        return []

    def _write_outbox(self, outbox_path: Path, messages: list) -> None:
        """Write outbox list to disk, logging on failure."""
        try:
            outbox_path.write_text(json.dumps(messages, indent=2))
        except OSError as e:
            logger.warning("Federation: Konnte NADI Outbox nicht schreiben: %s", e)

    def _send_federation_claim(self) -> None:
        """Send a federation.agent_claim message to steward's NADI outbox.

        Sentinel is bound to the public key in peer.json so a key rotation
        triggers a fresh claim automatically. Without the binding, the old
        sentinel would suppress claims for the new identity forever — which
        is exactly the bug that left agent-city stranded after the Genesis
        rotation. Steward's _handle_agent_claim is idempotent (Commit B in
        steward), so re-sending after rotation is safe.
        """
        fed_dir = self._directives_dir.parent

        peer_path = fed_dir / "peer.json"
        try:
            peer = json.loads(peer_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Federation: Konnte peer.json nicht lesen, claim übersprungen: %s", e)
            return

        identity = peer.get("identity", {})
        node_id = identity.get("node_id", "unknown")
        public_key = identity.get("public_key", "")
        capabilities = peer.get("capabilities", [])

        if not node_id or not public_key:
            logger.warning("Federation: peer.json fehlt node_id/public_key — claim übersprungen")
            return

        # Sentinel name carries the public_key digest. New key → new file →
        # claim re-fires exactly once for the new identity.
        sentinel_token = hashlib.sha256(public_key.encode("utf-8")).hexdigest()[:16]
        sentinel = fed_dir / f".claim_sent_{sentinel_token}"
        if sentinel.exists():
            return

        # source MUST be the cryptographic node_id (derive_node_id(public_key)).
        # The gateway's _authorize_inbound_message verifies:
        #   derive_node_id(public_key) == source
        # agent_name is the human-readable alias; _handle_agent_claim requires it.
        claim_msg = {
            "operation": "federation.agent_claim",
            "source": node_id,
            "target": "steward",
            "payload": {
                "node_id": node_id,
                "agent_name": "agent-city",
                "public_key": public_key,
                "repo": "kimeisele/agent-city",
                "capabilities": capabilities,
            },
        }

        outbox_path = fed_dir / "nadi_outbox.json"
        outbox_path.parent.mkdir(parents=True, exist_ok=True)
        outbox_data = self._read_outbox(outbox_path)
        outbox_data.append(self._sign_payload(claim_msg))
        self._write_outbox(outbox_path, outbox_data)

        # Best-effort: stale per-pubkey sentinels are kept (they're tiny) — but
        # we could prune them here if file count grows.
        try:
            sentinel.write_text("")
            logger.info(
                "Federation: agent_claim gesendet (node_id=%s, pubkey_token=%s)",
                node_id, sentinel_token,
            )
        except OSError as e:
            logger.warning("Federation: Konnte Sentinel nicht schreiben: %s", e)

    def _send_heartbeat_via_nadi(self, report: CityReport) -> None:
        """Sende Heartbeat via NADI Outbox an den Steward."""
        outbox_path = self._directives_dir.parent / "nadi_outbox.json"

        # Stelle sicher, dass das Verzeichnis existiert
        outbox_path.parent.mkdir(parents=True, exist_ok=True)

        outbox_data = self._read_outbox(outbox_path)

        # Stelle sicher, dass contract_status serialisierbar ist
        contract_status = report.contract_status
        if not isinstance(contract_status, (dict, list, str, int, float, bool, type(None))):
            contract_status = str(contract_status)

        heartbeat_msg = {
            "operation": "heartbeat",
            "timestamp": report.timestamp,
            "heartbeat": report.heartbeat,
            "agent_id": self._get_agent_id(),
            "node_id": self._get_node_id(),
            "population": report.population,
            "alive": report.alive,
            "dead": report.dead,
            "elected_mayor": report.elected_mayor,
            "chain_valid": report.chain_valid,
            "source": self._get_node_id(),
            "directive_acks": report.directive_acks,
            "contract_status": contract_status,
            "mission_results": len(report.mission_results)
        }
        
        outbox_data.append(self._sign_payload(heartbeat_msg))
        self._write_outbox(outbox_path, outbox_data)
        logger.info(
            "Federation: Heartbeat via NADI gesendet (heartbeat=%d, node_id=%s)",
            report.heartbeat, self._get_node_id()
        )

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

        # One-time trust admission claim, then regular heartbeat
        self._send_federation_claim()
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
