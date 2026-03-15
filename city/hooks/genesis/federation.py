"""
GENESIS Hook: Federation — Nadi inbox + Directive processing.

Receives cross-repo messages via FederationNadi and processes
mothership directives (register, freeze, create_mission, execute_code, policy).

Extracted from genesis.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from city.membrane import IngressSurface, enqueue_ingress, internal_membrane_snapshot
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.FEDERATION")


def _execute_directive(ctx: PhaseContext, directive: object) -> bool:
    """Execute a mothership directive. Returns True on success."""
    dtype = directive.directive_type
    params = directive.params

    if dtype == "register_agent":
        name = params.get("name")
        if not name:
            return False
        existing = ctx.pokedex.get(name)
        if existing:
            logger.info("Directive: agent %s already registered", name)
            return True
        ctx.pokedex.register(name)
        logger.info("Directive: registered agent %s", name)
        return True

    if dtype == "freeze_agent":
        name = params.get("name")
        if not name:
            return False
        try:
            ctx.pokedex.freeze(
                name,
                f"directive:{directive.id}",
                membrane=internal_membrane_snapshot(source_class="federation"),
            )
            logger.info("Directive: froze agent %s", name)
            return True
        except (ValueError, Exception) as e:
            logger.warning("Directive freeze failed: %s", e)
            return False

    if dtype == "create_mission" and ctx.sankalpa is not None:
        from city.missions import create_federation_mission

        created = create_federation_mission(ctx, directive)
        # Also create a council proposal for governance visibility
        if created and ctx.council is not None and ctx.council.elected_mayor is not None:
            from city.council import ProposalType

            topic = params.get("topic", "Federation mission")
            ctx.council.propose(
                title=f"Federation: {topic}",
                description=params.get("context", topic),
                proposer=ctx.council.elected_mayor,
                proposal_type=ProposalType.POLICY,
                action={
                    "type": "federation_mission",
                    "directive_id": directive.id,
                    "topic": topic,
                    "source_post_id": params.get("source_post_id", ""),
                },
                timestamp=time.time(),
            )
        return created

    if dtype == "execute_code" and ctx.sankalpa is not None:
        from city.missions import create_execution_mission

        created = create_execution_mission(ctx, directive)
        if created:
            logger.info(
                "Directive: execution mission created for %s",
                params.get("contract", "ruff_clean"),
            )
        return created

    if dtype == "policy_update":
        logger.info(
            "Directive: policy update noted — %s",
            params.get("description", "no description"),
        )
        return True

    logger.warning("Unknown directive type: %s", dtype)
    return False


class FederationNadiHook(BasePhaseHook):
    """Receive cross-repo messages via Federation Nadi."""

    @property
    def name(self) -> str:
        return "federation_nadi_inbox"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 30  # after moltbook, before directives

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation_nadi is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        fed_messages = ctx.federation_nadi.receive()
        for msg in fed_messages:
            enqueue_ingress(
                ctx,
                IngressSurface.FEDERATION,
                {
                    "source": f"federation:{msg.source}",
                    "text": msg.operation,
                    "federation_payload": msg.payload,
                    "correlation_id": msg.correlation_id,
                },
            )
            operations.append(f"fed_nadi:{msg.source}:{msg.operation}")
        if fed_messages:
            logger.info("GENESIS: %d federation Nadi messages received", len(fed_messages))


class FederationHealthHook(BasePhaseHook):
    """Read steward federation_health.json into relay for governance use."""

    @property
    def name(self) -> str:
        return "federation_health_reader"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 32  # after nadi inbox, before directives

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation is not None and hasattr(ctx.federation, "read_federation_health")

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        health = ctx.federation.read_federation_health()
        if health:
            operations.append(f"fed_health:steward_hb={health.get('heartbeat', '?')}")


class FederationDirectivesHook(BasePhaseHook):
    """Process mothership directives (register, freeze, mission, exec, policy)."""

    @property
    def name(self) -> str:
        return "federation_directives"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 35  # after nadi inbox

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.federation is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        directives = ctx.federation.check_directives()
        for d in directives:
            executed = _execute_directive(ctx, d)
            operations.append(f"directive:{d.directive_type}:{executed}")
            if executed:
                ctx.federation.acknowledge_directive(d.id)
            else:
                logger.warning(
                    "Directive %s (%s) failed — NOT acknowledged (will retry next cycle)",
                    d.id, d.directive_type,
                )
