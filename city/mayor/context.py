from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from city.phases import PhaseContext

if TYPE_CHECKING:
    from .kernel import Mayor


@dataclass(frozen=True)
class MayorContextBridge:
    """Owns Mayor ↔ PhaseContext assembly and mutable state synchronization."""

    def build_phase_context(self, mayor: Mayor) -> PhaseContext:
        mayor._service_bridge.sync_legacy_services(mayor)
        ctx = PhaseContext(
            pokedex=mayor._pokedex,
            gateway=mayor._gateway,
            network=mayor._network,
            heartbeat_count=mayor._heartbeat_count,
            offline_mode=mayor._offline_mode,
            state_path=mayor._state_path,
            active_agents=mayor._active_agents,
            gateway_queue=mayor._gateway_queue,
            registry=mayor._registry,
            last_audit_time=mayor._last_audit_time,
            recent_events=mayor._recent_events,
        )
        # Triage items survive across MURALI phases (DHARMA sets, KARMA consumes)
        ctx._triage_items = getattr(mayor, "_triage_items", [])  # type: ignore[attr-defined]
        # Gateway discussion numbers survive GENESIS→DHARMA (triage exclusion)
        ctx._gateway_disc_nums = getattr(mayor, "_gateway_disc_nums", set())  # type: ignore[attr-defined]
        return ctx

    def sync_from_phase_context(self, mayor: Mayor, ctx: PhaseContext) -> None:
        mayor._last_audit_time = ctx.last_audit_time
        # Sync triage items back (DHARMA may have added, KARMA may have consumed)
        mayor._triage_items = getattr(ctx, "_triage_items", [])
        # Sync gateway disc nums (GENESIS sets, DHARMA reads for triage exclusion)
        mayor._gateway_disc_nums = getattr(ctx, "_gateway_disc_nums", set())