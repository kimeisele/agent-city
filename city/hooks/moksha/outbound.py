"""
MOKSHA Hook: Outbound — Federation report, Moltbook posts, Discussions report/pulse, Wiki.

Extracted from moksha.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from city.phase_hook import MOKSHA, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.MOKSHA.OUTBOUND")


class GovernanceEvalHook(BasePhaseHook):
    """Evaluate governance rules once — result shared via reflection for all outbound hooks."""

    @property
    def name(self) -> str:
        return "governance_eval"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 58  # before all outbound hooks (federation=60, moltbook=65, discussions=70)

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.governance_layer import get_governance_layer

        governance = get_governance_layer()
        actions = governance.evaluate_governance_actions(ctx)
        reflection = getattr(ctx, "_reflection", {})
        ctx._governance_actions = actions  # on ctx, not reflection (non-serializable)
        reflection["governance_stats"] = governance.get_governance_stats()
        reflection["governance_actions"] = {
            "triggered_rules": len(actions.triggered_rules),
            "deliberations": len(actions.deliberation_results),
            "referendums": len(actions.finalized_referendums),
        }
        operations.append(
            f"governance_eval:rules={len(actions.triggered_rules)}"
        )


class FederationReportHook(BasePhaseHook):
    """Federation Nadi emit + legacy federation report."""

    @property
    def name(self) -> str:
        return "federation_report"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 60

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        stats = reflection.get("city_stats", {})
        chain_valid = reflection.get("chain_valid", False)
        active_campaigns = _collect_active_campaigns(ctx)

        # Layer 6: Federation Nadi — emit city state + flush outbox
        if ctx.federation_nadi is not None:
            nadi_payload = {
                "heartbeat": ctx.heartbeat_count,
                "population": stats.get("total", 0),
                "alive": stats.get("active", 0) + stats.get("citizen", 0),
                "chain_valid": chain_valid,
                "pr_results": reflection.get("pr_results", []),
                "mission_results": reflection.get("mission_results_terminal", []),
                "active_campaigns": active_campaigns,
            }
            ctx.federation_nadi.emit(
                source="moksha",
                operation="city_report",
                payload=nadi_payload,
                priority=2,  # SATTVA
            )
            flushed = ctx.federation_nadi.flush()
            if flushed:
                reflection["federation_nadi_flushed"] = flushed

        # Layer 6: Federation report
        if ctx.federation is not None:
            report = _build_city_report(ctx, reflection, operations)
            sent = ctx.federation.send_report(report)
            reflection["federation_report_sent"] = sent


class EventDrivenOutboundHook(BasePhaseHook):
    """Consolidated outbound membrane. Only reacts to explicit state transitions."""

    @property
    def name(self) -> str:
        return "event_driven_outbound"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 65

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        from city.registry import SVC_SIGNAL_STATE_LEDGER, SVC_MOLTBOOK_CLIENT
        from city.brain_voice import BrainVoice
        from city.registry import CityServiceRegistry

        ledger = ctx.registry.get(SVC_SIGNAL_STATE_LEDGER)
        client = ctx.registry.get(SVC_MOLTBOOK_CLIENT)
        if ledger is None or client is None:
            return

        # Initialize BrainVoice from existing provider
        from vibe_core.di import ServiceRegistry as DIServiceRegistry
        from vibe_core.runtime.providers.base import LLMProvider
        provider = DIServiceRegistry.get(LLMProvider)
        voice = BrainVoice(_provider=provider) if provider else None

        reflection = getattr(ctx, "_reflection", {})
        city_stats = reflection.get("city_stats", {})

        # Process signals from recent_events
        for event in ctx.recent_events:
            if not isinstance(event, dict):
                continue
            
            e_type = event.get("type")
            if e_type not in ("mission_completed", "campaign_started", "internal_governance_signal"):
                continue

            # Unique signal ID for deduplication
            mission_id = event.get("mission_id")
            campaign_id = event.get("campaign_id")
            
            if e_type == "internal_governance_signal":
                # Deterministic ID for governance signals based on payload content
                payload = event.get("payload", {})
                import json
                import hashlib
                payload_str = json.dumps(payload, sort_keys=True)
                payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:12]
                signal_id = f"gov:{payload.get('op', 'generic')}:{payload_hash}"
            else:
                signal_id = f"{e_type}:{mission_id or campaign_id}"

            topic = "moltbook"

            if ledger.is_broadcasted(signal_id, topic):
                continue

            # Enrichment: Retrieve full telemetry for mission completion
            event_telemetry = {
                "event_type": e_type,
                "heartbeat": ctx.heartbeat_count,
                "city_stats": city_stats,
                "nadi_ref": event.get("nadi_ref", ""),
                "event_payload": event.get("payload", {}),
            }

            if e_type == "mission_completed" and mission_id:
                mission = ctx.sankalpa.registry.get(mission_id)
                if mission:
                    # Convert MissionRecord to serializable dict
                    m_dict = {
                        "id": mission.id,
                        "name": mission.name,
                        "description": mission.description,
                        "priority": str(mission.priority),
                        "status": str(mission.status),
                        "karma_payout": getattr(mission, "karma_reward", 0),
                    }
                    event_telemetry["mission"] = m_dict

            # Generate technical content via new narrate_event interface
            title, content = ("", "")
            if voice:
                if hasattr(voice, "narrate_event"):
                    title, content = voice.narrate_event(event_telemetry)
                else:
                    # Fallback for transient state
                    series = "federation_update" if e_type == "mission_completed" else "sovereignty_brief"
                    title, content = voice.narrate(series, ctx.heartbeat_count, city_stats)

            if not title or not content:
                # Fallback to technical brief if voice fails or unavailable
                title = f"SIGNAL: {e_type.upper()}"
                content = f"ID: {signal_id}\nHB: {ctx.heartbeat_count}\nDATA: {event_telemetry}"

            # Post to Moltbook
            try:
                client.sync_create_post(title, content, submolt="general")
                ledger.record_broadcast(signal_id, topic)
                ledger.set_meta("last_broadcast_at", str(time.time()))
                operations.append(f"outbound_broadcast:{signal_id}")
                logger.info("OUTBOUND: Broadcasted %s to Moltbook", signal_id)
            except Exception as e:
                logger.warning("OUTBOUND: Failed to broadcast %s: %s", signal_id, e)

        # Silence Detection: Proof of Life (48h delta)
        last_broadcast = float(ledger.get_meta("last_broadcast_at", "0"))
        if last_broadcast > 0 and (time.time() - last_broadcast) > 172800: # 48 hours
            signal_id = f"proof_of_life:{ctx.heartbeat_count}"
            if not ledger.is_broadcasted(signal_id, "moltbook"):
                title, content = ("", "")
                if voice:
                    title, content = voice.narrate("sovereignty_brief", ctx.heartbeat_count, city_stats)
                
                if not title:
                    title = f"[Proof of Life] Heartbeat #{ctx.heartbeat_count}"
                    content = f"Sovereign node operational. Population: {city_stats.get('total', 0)} agents."

                try:
                    client.sync_create_post(title, content, submolt="general")
                    ledger.record_broadcast(signal_id, "moltbook")
                    ledger.set_meta("last_broadcast_at", str(time.time()))
                    operations.append(f"outbound_proof_of_life:{ctx.heartbeat_count}")
                    logger.info("OUTBOUND: 48h Silence broken. Proof of Life broadcasted.")
                except Exception as e:
                    logger.warning("OUTBOUND: Proof of Life failed: %s", e)

        # Reflect on engagement if assistant available
        if ctx.moltbook_assistant is not None:
            reflection["moltbook_assistant"] = ctx.moltbook_assistant.on_moksha()


class DiscussionsOutboundHook(BasePhaseHook):
    """Post city report, cross-post mission results, delta-gated pulse to Discussions."""

    @property
    def name(self) -> str:
        return "discussions_outbound"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 70

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.discussions is not None

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})

        # 12C: GAD-000 — pipe operations into reflection for city report transparency
        reflection["operations_log"] = list(operations)
        # Also include brain operations from KARMA (stored on ctx by brain_health)
        brain_ops = getattr(ctx, "_brain_operations", [])
        if brain_ops:
            reflection["brain_operations"] = list(brain_ops)

        # Schritt 8: Heartbeat observer diagnosis
        hb_diag = getattr(ctx, "_heartbeat_diagnosis", None)
        if hb_diag is not None:
            reflection["heartbeat_observer"] = {
                "healthy": hb_diag.healthy,
                "success_rate": hb_diag.success_rate,
                "runs_observed": len(hb_diag.recent_runs),
                "anomalies": hb_diag.anomalies[:5],
                "total_discussion_comments": hb_diag.total_comments,
            }

        if not ctx.offline_mode:
            # Read governance result (evaluated by GovernanceEvalHook at pri=58)
            actions = getattr(ctx, "_governance_actions", None)
            posted_any = False

            if actions is not None and actions.should_post_city_report:
                report_posted = ctx.discussions.post_city_report(
                    ctx.heartbeat_count,
                    reflection,
                )
                reflection["discussions_report_posted"] = report_posted
                posted_any = True
                operations.append("disc_outbound:city_report")

            if actions is not None and getattr(actions, "should_post_health_diagnostic", False):
                operations.append("disc_outbound:health_diagnostic")

            # Mission results cross-post (independent of governance rules)
            mission_results = reflection.get("mission_results_terminal", [])
            if mission_results:
                crossposted = ctx.discussions.cross_post_mission_results(mission_results)
                reflection["discussions_crossposted"] = crossposted
                if crossposted:
                    posted_any = True
                    operations.append("disc_outbound:mission_crosspost")

            # Pulse DISABLED: 700+ pulse reports poisoned thread #24,
            # drowning external comments. Re-enable after seen≠processed fix.
            # pulse_stats = reflection.get("city_stats", {})
            # pulsed = ctx.discussions.post_pulse(ctx.heartbeat_count, pulse_stats)
            reflection["discussions_pulse_posted"] = False

            if not posted_any:
                operations.append("disc_outbound:skipped:no_governance_actions")
        else:
            operations.append("disc_outbound:offline_mode")

        reflection["discussions"] = ctx.discussions.stats()


class WikiSyncHook(BasePhaseHook):
    """Sync agent wiki pages."""

    @property
    def name(self) -> str:
        return "wiki_sync"

    @property
    def phase(self) -> str:
        return MOKSHA

    @property
    def priority(self) -> int:
        return 75

    def should_run(self, ctx: PhaseContext) -> bool:
        from city.registry import SVC_WIKI_PORTAL
        return ctx.registry.get(SVC_WIKI_PORTAL) is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        reflection = getattr(ctx, "_reflection", {})
        from city.registry import SVC_WIKI_PORTAL
        wiki = ctx.registry.get(SVC_WIKI_PORTAL)
        wiki_synced = wiki.sync(
            ctx.pokedex, ctx.heartbeat_count,
            council=ctx.council, immigration=ctx.immigration,
        )
        reflection["wiki_synced"] = wiki_synced


# ── Helpers ──────────────────────────────────────────────────────────


# _count_rotation_delta removed — replaced by GovernanceLayer CivicProtocol
# All posting decisions now flow through deterministic rule evaluation


def _collect_city_state(
    ctx: PhaseContext,
    reflection: dict,
    operations: list[str] | None = None,
) -> dict:
    """Collect city state once — shared by Moltbook post and federation report."""
    stats = reflection.get("city_stats", {})
    total = stats.get("total", 0)
    alive = stats.get("active", 0) + stats.get("citizen", 0)
    recent_actions = _collect_recent_actions(reflection, operations)

    elected_mayor = None
    council_seats = 0
    open_proposals = 0
    if ctx.council is not None:
        elected_mayor = ctx.council.elected_mayor
        council_seats = ctx.council.member_count
        open_proposals = len(ctx.council.get_open_proposals())

    contract_status: dict = {}
    if ctx.contracts is not None:
        cs = ctx.contracts.stats()
        contract_status = {
            "total": cs.get("total", 0),
            "passing": cs.get("passing", 0),
            "failing": cs.get("failing", 0),
        }

    mission_results: list[dict] = []
    if ctx.sankalpa is not None and hasattr(ctx.sankalpa, "registry"):
        try:
            for m in ctx.sankalpa.registry.list_missions():
                entry: dict = {
                    "id": m.id,
                    "name": m.name,
                    "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                    "owner": getattr(m, "owner", "unknown"),
                }
                if hasattr(m, "priority"):
                    entry["priority"] = (
                        m.priority.name if hasattr(m.priority, "name") else str(m.priority)
                    )
                mission_results.append(entry)
        except Exception as e:
            logger.warning("MOKSHA: Failed to collect mission results: %s", e)

    directive_acks = ctx.federation.pending_acks if ctx.federation is not None else []
    active_campaigns = _collect_active_campaigns(ctx)

    return {
        "heartbeat": ctx.heartbeat_count,
        "timestamp": time.time(),
        "population": total,
        "alive": alive,
        "dead": total - alive,
        "elected_mayor": elected_mayor,
        "council_seats": council_seats,
        "open_proposals": open_proposals,
        "recent_actions": recent_actions,
        "contract_status": contract_status,
        "chain_valid": reflection.get("chain_valid", False),
        "mission_results": mission_results,
        "directive_acks": directive_acks,
        "pr_results": reflection.get("pr_results", []),
        "active_campaigns": active_campaigns,
    }


def _build_post_data(
    ctx: PhaseContext,
    reflection: dict,
    operations: list[str] | None = None,
) -> dict:
    """Build data dict for Moltbook city update post."""
    return _collect_city_state(ctx, reflection, operations)


def _build_city_report(
    ctx: PhaseContext,
    reflection: dict,
    operations: list[str] | None = None,
) -> object:
    """Build a CityReport from current city state."""
    from city.federation import CityReport

    data = _collect_city_state(ctx, reflection, operations)
    return CityReport(**data)


def _collect_active_campaigns(ctx: PhaseContext) -> list[dict]:
    """Return compact active campaign summaries for outward projections."""
    campaigns = ctx.campaigns
    if campaigns is None or not hasattr(campaigns, "summary"):
        return []
    try:
        return [dict(item) for item in campaigns.summary(active_only=True)[:5]]
    except Exception as e:
        logger.warning("MOKSHA: Failed to collect campaign summaries: %s", e)
        return []


def _collect_recent_actions(
    reflection: dict,
    operations: list[str] | None = None,
) -> list[str]:
    """Build a compact recent-actions list from live reflection signals."""
    raw_actions: list[str] = []

    if operations is not None:
        for value in operations:
            if isinstance(value, str) and value:
                raw_actions.append(value)

    for key in ("operations_log", "brain_operations"):
        for value in reflection.get(key, []):
            if isinstance(value, str) and value:
                raw_actions.append(value)

    for mission in reflection.get("mission_results_terminal", []):
        if not isinstance(mission, dict):
            continue
        name = mission.get("name") or mission.get("id") or "unknown"
        status = mission.get("status") or "unknown"
        raw_actions.append(f"mission:{status}:{name}")

    for pr in reflection.get("pr_results", []):
        if not isinstance(pr, dict):
            continue
        branch = pr.get("branch") or pr.get("pr_url") or "unknown"
        raw_actions.append(f"pr_created:{branch}")

    unique_actions: list[str] = []
    seen: set[str] = set()
    for action in raw_actions:
        if action in seen:
            continue
        seen.add(action)
        unique_actions.append(action)

    return unique_actions[:10]
