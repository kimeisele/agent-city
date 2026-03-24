"""
GENESIS Hook: NADI Inbox Scanner — Process incoming signed signals.
===================================================================

Reads data/federation/nadi_inbox.json with strict file-locking.
Verifies Ed25519 signatures and routes to Governance.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import fcntl
from pathlib import Path
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook
from city.registry import SVC_FEDERATION_NADI, SVC_IDENTITY, SVC_SIGNAL_STATE_LEDGER, SVC_INTENT_EXECUTOR

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.NADI_INBOX")


class NadiInboxScannerHook(BasePhaseHook):
    """Scans and processes incoming NADI messages with Zero Trust verification."""

    @property
    def name(self) -> str:
        return "nadi_inbox_scanner"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 45  # Early in Genesis to process responses before other hooks

    def should_run(self, ctx: PhaseContext) -> bool:
        if ctx.offline_mode:
            return False
        
        nadi = ctx.registry.get(SVC_FEDERATION_NADI)
        if not nadi or not nadi.inbox_path.exists():
            return False
            
        return True

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.signal_decoder import decode_signal
        from city.reactor import CityIntent

        nadi = ctx.registry.get(SVC_FEDERATION_NADI)
        identity = ctx.registry.get(SVC_IDENTITY)
        ledger = ctx.registry.get(SVC_SIGNAL_STATE_LEDGER)
        executor = ctx.registry.get(SVC_INTENT_EXECUTOR)
        
        if not all([nadi, identity, ledger, executor]):
            logger.error("NADI_INBOX_SCANNER: Missing required services in registry.")
            return

        inbox_path = nadi.inbox_path
        processed_count = 0

        try:
            with open(inbox_path, "r+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    content = f.read()
                    messages = json.loads(content) if content else []
                    if not messages:
                        return

                    remaining_messages = []
                    for msg_data in messages:
                        try:
                            # 1. Zero Trust Verification
                            payload = msg_data.get("payload")
                            signature = msg_data.get("signature")
                            public_key = msg_data.get("signer_key")
                            
                            if not all([payload, signature, public_key]) or not identity.verify(payload, signature, public_key):
                                logger.warning("NADI_INBOX_SCANNER: Signature verification FAILED or malformed message. Dropping.")
                                continue

                            # 2. De-duplication
                            import hashlib
                            payload_json = json.dumps(payload, sort_keys=True)
                            nadi_msg_id = hashlib.sha256(payload_json.encode()).hexdigest()
                            
                            if ledger.is_signal_processed(nadi_msg_id):
                                continue

                            # 3. Decode Signal & Create Intent
                            signal_dict = payload.get("signal", {})
                            # We assume the signal_dict is valid SemanticSignal dict
                            # We need to reconstruct the SemanticSignal object OR pass the dict
                            # Implementation detail: IntentExecutor handler expects 'signal' and 'sender_jiva' in context
                            from city.signal import SemanticSignal, SignalCoords
                            
                            # Reconstruct signal for the handler
                            c = signal_dict.get("coords", {})
                            coords = SignalCoords(
                                rama_coordinates=tuple(c.get("rama_coordinates", [])),
                                element_walk=tuple(c.get("element_walk", [])),
                                element_histogram=tuple(c.get("element_histogram", [])),
                                basin_set=frozenset(c.get("basin_set", [])),
                                hkr_color=tuple(c.get("hkr_color", [])),
                                walk_direction=c.get("walk_direction", 0),
                                dominant_element=c.get("dominant_element", 0)
                            )
                            
                            sig_obj = SemanticSignal(
                                sender_name=signal_dict.get("sender_name", ""),
                                sender_address=signal_dict.get("sender_address", 0),
                                correlation_id=signal_dict.get("correlation_id", ""),
                                coords=coords,
                                sender_element=signal_dict.get("sender_element", 0),
                                sender_guardian=signal_dict.get("sender_guardian", ""),
                                sender_chapter=signal_dict.get("sender_chapter", 0),
                                sender_guna=signal_dict.get("sender_guna", ""),
                                sender_trinity=signal_dict.get("sender_trinity", ""),
                                concepts=tuple(signal_dict.get("concepts", [])),
                                resonant_elements=tuple(signal_dict.get("resonant_elements", [])),
                                raw_text=signal_dict.get("raw_text", ""),
                                priority=signal_dict.get("priority", 1),
                                intent=signal_dict.get("intent", "MISSION_PROPOSAL"),
                                in_reply_to=signal_dict.get("in_reply_to", ""),
                                hop_count=signal_dict.get("hop_count", 0)
                            )

                            intent = CityIntent(
                                signal=f"federation:{sig_obj.intent}",
                                priority=20,
                                context={
                                    "signal": sig_obj,
                                    "sender_jiva": payload.get("origin_jiva", "unknown"),
                                    "federation_message": msg_data,
                                    "nadi_msg_id": nadi_msg_id
                                }
                            )

                            # 4. Execute
                            result = executor.execute(ctx, intent, "handle_federation_signal")
                            if not result.startswith("error"):
                                ledger.mark_signal_processed(nadi_msg_id)
                                processed_count += 1
                            
                        except Exception as e:
                            logger.error("NADI_INBOX_SCANNER: Error processing message: %s", e)

                    # Inbox Cleansing
                    f.seek(0)
                    f.truncate()
                    f.write(json.dumps(remaining_messages, indent=2))
                    
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            logger.error("NADI_INBOX_SCANNER: Inbox IO Error: %s", e)

        if processed_count > 0:
            operations.append(f"nadi_inbox:{processed_count}_processed")
