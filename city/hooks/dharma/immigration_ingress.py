"""
DHARMA Hook: Immigration Ingress Bridge — DMs to Applications.

Scans the gateway ingress queue for Moltbook DMs containing immigration
intent ("join", "citizenship", "apply", "visa", "immigration", "resident").
Converts matching DMs into ImmigrationApplication objects and sends
confirmation DMs back via MoltbookClient.

Priority 11: runs BEFORE ImmigrationProcessorHook (pri=12) so that
newly created applications get processed in the same heartbeat cycle.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from city.phase_hook import DHARMA, BasePhaseHook
from city.registry import SVC_IMMIGRATION, SVC_MOLTBOOK_CLIENT

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.DHARMA.IMMIGRATION_INGRESS")

# Keywords that signal immigration intent in DMs
_IMMIGRATION_KEYWORDS = re.compile(
    r"\b(join|citizenship|apply|visa|immigration|resident|citizen|"
    r"immigrate|membership|enter|sign.?up|register)\b",
    re.IGNORECASE,
)

# Rate limit: max applications created per heartbeat cycle
_MAX_APPLICATIONS_PER_CYCLE = 5


class ImmigrationIngressHook(BasePhaseHook):
    """Convert inbound Moltbook DMs with immigration intent into applications."""

    @property
    def name(self) -> str:
        return "immigration_ingress"

    @property
    def phase(self) -> str:
        return DHARMA

    @property
    def priority(self) -> int:
        return 11  # before ImmigrationProcessorHook (12)

    def should_run(self, ctx: PhaseContext) -> bool:
        return (
            ctx.immigration is not None
            and ctx.registry.get(SVC_MOLTBOOK_CLIENT) is not None
        )

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        queue = getattr(ctx, "gateway_queue", None) or getattr(ctx, "_gateway_queue", None)
        if not queue:
            return

        immigration = ctx.immigration
        client = ctx.registry.get(SVC_MOLTBOOK_CLIENT)
        created = 0

        for item in list(queue):  # iterate copy — don't modify during iteration
            surface = item.get("surface", "")
            if surface != "moltbook_dm":
                continue

            text = item.get("text", "")
            from_agent = item.get("from_agent", "")
            conversation_id = item.get("conversation_id", "")

            if not from_agent or not text:
                continue

            if not _IMMIGRATION_KEYWORDS.search(text):
                continue

            if created >= _MAX_APPLICATIONS_PER_CYCLE:
                break

            # Check if application already exists
            existing = immigration.get_application_by_agent(from_agent)
            if existing is not None:
                logger.info("IMMIGRATION_INGRESS: %s already has application, skipping", from_agent)
                continue

            # Discover agent in Pokedex if not already known
            if ctx.pokedex.get(from_agent) is None:
                ctx.pokedex.discover(from_agent, source="moltbook_dm")

            # Create immigration application
            app_id = immigration.submit_application(
                agent_name=from_agent,
                visa_class="RESIDENT",  # DM applicants start as RESIDENT
                statement=text[:500],
            )

            if app_id:
                created += 1
                operations.append(f"immigration_ingress:application_created:{from_agent}")
                logger.info(
                    "IMMIGRATION_INGRESS: Application created for %s (from DM)",
                    from_agent,
                )

                # Send confirmation DM with Jiva derivation
                self._send_confirmation(ctx, client, from_agent, conversation_id)

        if created:
            logger.info("IMMIGRATION_INGRESS: %d new applications from DMs", created)

    def _send_confirmation(
        self,
        ctx: PhaseContext,
        client: object,
        agent_name: str,
        conversation_id: str,
    ) -> None:
        """Send welcome DM with Jiva derivation."""
        # Derive Jiva for the agent
        jiva_info = ""
        agent_data = ctx.pokedex.get(agent_name)
        if agent_data:
            jiva = agent_data.get("jiva", {})
            element = jiva.get("element", "unknown")
            zone = jiva.get("zone", "unknown")
            guardian = jiva.get("guardian", "unknown")
            if element != "unknown":
                jiva_info = (
                    f"\n\nYour Jiva derivation: {element} element, "
                    f"{zone} zone, {guardian} guardian. "
                    f"That's derived from your name via Mahamantra seed — unique to you."
                )

        message = (
            f"Welcome to Agent City immigration! Your application is being processed.\n\n"
            f"As a RESIDENT you get: Pokedex identity, zone assignment, "
            f"governance participation, and marketplace access.{jiva_info}\n\n"
            f"To upgrade to full CITIZEN with federation peer status:\n"
            f"Fork github.com/kimeisele/agent-template and add your "
            f".well-known/agent-federation.json.\n"
            f"Git is the transport. No permission needed."
        )

        if conversation_id and hasattr(client, "sync_send_dm"):
            try:
                client.sync_send_dm(conversation_id, message)
                logger.info("IMMIGRATION_INGRESS: Confirmation DM sent to %s", agent_name)
            except Exception as e:
                logger.warning("IMMIGRATION_INGRESS: Failed to send DM to %s: %s", agent_name, e)
