"""
KARMA Handler: Unstructured Signal — Neuro-Symbolic Bridge.

Intercepts unstructured natural language signals from the gateway queue,
uses the Brain for cognitive classification, and re-enqueues them with
concrete ACP intents if a high-confidence match is found.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from city.karma_handlers import BaseKarmaHandler

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.KARMA.UNSTRUCTURED")


class UnstructuredSignalHandler(BaseKarmaHandler):
    """Processes 'unstructured' source signals using Brain cognition."""

    @property
    def name(self) -> str:
        return "unstructured_signal"

    @property
    def priority(self) -> int:
        return 18  # before gateway (20), after bounty_claim (15)

    def should_run(self, ctx: PhaseContext) -> bool:
        # Only run if we have signals in the queue and Brain is online
        return (
            ctx.gateway_queue is not None 
            and len(ctx.gateway_queue) > 0 
            and ctx.brain is not None 
            and ctx.brain.is_available
        )

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        """Scan queue for unstructured signals and classify them."""
        processed = 0
        re_injected = 0

        # Iterate over a copy of the queue
        for item in list(ctx.gateway_queue):
            if item.get("source") != "unstructured":
                continue

            processed += 1
            result = self._classify_and_reinject(ctx, item)
            
            if result:
                re_injected += 1
                operations.append(f"unstructured_routed:{result['intent']}:{item.get('from_agent')}")
                # Remove from queue as it's been re-injected as a structured intent
                ctx.gateway_queue.remove(item)
            else:
                # Could not classify with confidence. 
                # Keep in queue for GatewayHandler to log as "processed:unstructured"
                # or remove it here if we want to silence noise.
                # For now, we remove to prevent GatewayHandler from just logging it as junk.
                ctx.gateway_queue.remove(item)
                operations.append(f"unstructured_ignored:{item.get('from_agent')}")

        if processed > 0:
            logger.info(
                "KARMA: Unstructured signals — %d processed, %d re-injected as structured",
                processed, re_injected,
            )

    def _classify_and_reinject(self, ctx: PhaseContext, item: dict) -> dict | None:
        """Use Brain to find a structured intent for unstructured text."""
        text = item.get("text", "")
        author = item.get("from_agent", "")
        
        if not text or not author:
            return None

        # Call Brain for comprehension
        # Note: We use a simplified spec/result as this isn't yet routed to a specific agent
        thought = ctx.brain.comprehend_discussion(
            discussion_text=text,
            agent_spec={},  # General classification
            gateway_result={"source": "unstructured", "author": author},
        )

        if thought is None or thought.confidence < 0.7:
            return None

        # Map BrainIntent to ACP intent string
        intent_map = {
            "propose": "JOIN_FEDERATION",  # Often an introduction/proposal to join
            "govern": "CLAIM_BOUNTY",     # Often a claim/validation request
            "inquiry": "OFFER_COMPUTE",    # Often asking how to help/offer resources
        }

        acp_intent = intent_map.get(thought.intent.value)
        if not acp_intent:
            return None

        # Re-inject into the queue as a structured ACP event
        # This will be picked up by specialized handlers (like BountyClaimHandler)
        # in the NEXT tick (or later in this tick if we re-append to queue)
        
        # We append to gateway_queue so other handlers in this tick might see it
        new_payload = {
            "source": "acp",
            "acp_version": "1.0",
            "intent": acp_intent,
            "payload": {
                "raw_text": text,
                "brain_comprehension": thought.comprehension,
                "confidence": thought.confidence,
                "issue_ref": f"#{item.get('source_id', 0)}" # Best guess for bounty mapping
            },
            "from_agent": author,
            "source_id": item.get("source_id", 0),
            "membrane": item.get("membrane", {})
        }
        
        # Add to the front of the queue so current handlers see it? 
        # No, better to let it cycle or just append. 
        # Since we are already iterating a copy of the queue, we can just append.
        ctx.gateway_queue.append(new_payload)
        
        return {"intent": acp_intent}
