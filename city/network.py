"""
NAGA NETWORK — Agent Communication & Health
=============================================

NAGA provides the network layer. Agents communicate via MahaHeader routing.
The network self-heals via Ouroboros.

Three Bodies (Ouroboros Protocol) per agent:
- STHULA (Physical): SQLite row + cell_bytes (persistent)
- PRANA (Vital): Runtime MahaCellUnified state (prana, integrity, cycle)
- PURUSHA (Soul): ECDSA identity + Mahamantra seed (eternal, immutable)

Wired from steward-protocol:
- AnantaShesha — system bridge, gene registration
- EventBus — pub/sub with DIW-aware filtering
- NagaOuroboros — loop detection + circuit breaker

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TypedDict

from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified
from vibe_core.ouroboros.ananta_shesha import AnantaShesha, get_system_anchor

from city.addressing import CityAddressBook
from city.gateway import CityGateway

from config import get_config

logger = logging.getLogger("AGENT_CITY.NETWORK")

# Operation codes for MahaHeader.pada_sevanam
OP_MESSAGE = 1
OP_BROADCAST = 2
OP_REGISTER = 3
OP_HEALTH_CHECK = 4


class MessageRecord(TypedDict):
    """Immutable record of a routed message."""
    timestamp: float
    from_name: str
    to_name: str
    from_address: int
    to_address: int
    operation: int
    payload_hash: int
    verified: bool


@dataclass
class CityNetwork:
    """Agent-to-agent communication layer backed by NAGA infrastructure.

    Routes messages via MahaHeader, verifies ECDSA signatures,
    registers agents with AnantaShesha for health monitoring.
    """

    _address_book: CityAddressBook = field(default_factory=CityAddressBook)
    _gateway: CityGateway = field(default_factory=CityGateway)
    _anchor: AnantaShesha = field(default_factory=get_system_anchor)
    _message_log: list[MessageRecord] = field(default_factory=list)
    _registered_agents: set[str] = field(default_factory=set)
    _message_limit: int = field(
        default_factory=lambda: get_config().get("network", {}).get("message_log_limit", 1000)
    )

    def send(
        self,
        from_name: str,
        to_name: str,
        message: str,
        *,
        signature: str | None = None,
        public_key_pem: str | None = None,
    ) -> bool:
        """Route a message from one agent to another.

        Creates a MahaHeader for routing, optionally verifies ECDSA signature,
        and records the message in the event ledger.
        """
        # Create routing header
        header = self._address_book.route(from_name, to_name, operation=OP_MESSAGE)

        # Verify signature if provided
        verified = False
        if signature and public_key_pem:
            verified = self._gateway.validate_agent_message(
                from_name, message.encode(), signature, public_key_pem,
            )
            if not verified:
                logger.warning(
                    "Message from %s to %s: ECDSA verification failed",
                    from_name, to_name,
                )
                return False

        # Record message
        record: MessageRecord = {
            "timestamp": time.time(),
            "from_name": from_name,
            "to_name": to_name,
            "from_address": header.sravanam,
            "to_address": header.kirtanam,
            "operation": OP_MESSAGE,
            "payload_hash": hash(message),
            "verified": verified,
        }
        self._append_record(record)

        # Emit event on AnantaShesha
        self._anchor.emit_event("AGENT_MESSAGE", {
            "from": from_name,
            "to": to_name,
            "source_address": header.sravanam,
            "target_address": header.kirtanam,
        })

        logger.debug("Message routed: %s → %s (verified=%s)", from_name, to_name, verified)
        return True

    def broadcast(self, from_name: str, message: str) -> int:
        """Broadcast a message to all registered agents.

        Emits on AnantaShesha event bus. Returns number of recipients.
        """
        header = self._address_book.route(from_name, from_name, operation=OP_BROADCAST)

        # Emit event
        self._anchor.emit_event("AGENT_BROADCAST", {
            "from": from_name,
            "source_address": header.sravanam,
            "message_hash": hash(message),
            "recipients": len(self._registered_agents),
        })

        record: MessageRecord = {
            "timestamp": time.time(),
            "from_name": from_name,
            "to_name": "*",
            "from_address": header.sravanam,
            "to_address": 0,
            "operation": OP_BROADCAST,
            "payload_hash": hash(message),
            "verified": True,
        }
        self._append_record(record)

        recipients = len(self._registered_agents - {from_name})
        logger.debug("Broadcast from %s to %d agents", from_name, recipients)
        return recipients

    def register_agent(self, name: str, cell: MahaCellUnified) -> int:
        """Register agent in the network for routing and health monitoring.

        Registers in CityAddressBook (CellRouter) and AnantaShesha (gene).
        Returns the agent's address.
        """
        address = self._address_book.register(name, cell)
        self._registered_agents.add(name)

        # Register as gene with AnantaShesha for health monitoring
        self._anchor.register_gene_simple(f"city_agent_{name}", {
            "name": name,
            "address": address,
            "body": "PRANA",  # Runtime state
        })

        self._anchor.emit_event("AGENT_REGISTERED", {
            "name": name,
            "address": address,
        })

        logger.debug("Agent %s registered at address %d", name, address)
        return address

    def unregister_agent(self, name: str) -> bool:
        """Remove an agent from the network."""
        removed = self._address_book.unregister(name)
        self._registered_agents.discard(name)
        if removed:
            self._anchor.emit_event("AGENT_UNREGISTERED", {"name": name})
        return removed

    def get_message_log(self, limit: int = 50) -> list[MessageRecord]:
        """Get recent messages from the log."""
        return self._message_log[-limit:]

    def agent_health(self, name: str) -> dict | None:
        """Check an agent's health via their cell in the router."""
        address = self._address_book.resolve(name)
        cell = self._address_book.lookup(address)
        if cell is None:
            return None
        return {
            "name": name,
            "address": address,
            "prana": cell.prana,
            "integrity": cell.membrane_integrity,
            "is_alive": cell.is_alive,
            "age": cell.age,
            "body_sthula": True,   # Persistent (SQLite)
            "body_prana": cell.is_alive,  # Runtime vitality
            "body_purusha": True,  # Eternal (ECDSA + seed)
        }

    def stats(self) -> dict:
        """Network statistics."""
        sesha_status = self._anchor.heartbeat()
        return {
            "registered_agents": len(self._registered_agents),
            "messages_routed": len(self._message_log),
            "address_book": self._address_book.stats(),
            "sesha_genes": sesha_status.get("genes_registered", 0),
            "sesha_events": sesha_status.get("events_processed", 0),
        }

    def _append_record(self, record: MessageRecord) -> None:
        """Append a message record, trimming to limit."""
        self._message_log.append(record)
        if len(self._message_log) > self._message_limit:
            self._message_log = self._message_log[-self._message_limit:]
