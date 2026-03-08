"""Campaign registry — heartbeat-driven long-horizon orientation above Sankalpa missions."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.CAMPAIGNS")


class CampaignStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class CampaignSignal:
    kind: str
    target: bool | int = True
    description: str = ""


@dataclass
class CampaignRecord:
    id: str
    title: str
    north_star: str
    success_signals: list[CampaignSignal] = field(default_factory=list)
    heartbeat_interval: int = 4
    max_active_missions: int = 1
    status: CampaignStatus = CampaignStatus.ACTIVE
    owner: str = "mayor"
    derived_mission_ids: list[str] = field(default_factory=list)
    last_evaluated_heartbeat: int = 0
    last_compiled_heartbeat: int = 0
    last_gap_summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignRecord":
        return cls(
            id=data["id"],
            title=data.get("title", data["id"]),
            north_star=data.get("north_star", ""),
            success_signals=[CampaignSignal(**signal) for signal in data.get("success_signals", [])],
            heartbeat_interval=int(data.get("heartbeat_interval", 4)),
            max_active_missions=int(data.get("max_active_missions", 1)),
            status=CampaignStatus(data.get("status", CampaignStatus.ACTIVE.value)),
            owner=data.get("owner", "mayor"),
            derived_mission_ids=list(data.get("derived_mission_ids", [])),
            last_evaluated_heartbeat=int(data.get("last_evaluated_heartbeat", 0)),
            last_compiled_heartbeat=int(data.get("last_compiled_heartbeat", 0)),
            last_gap_summary=list(data.get("last_gap_summary", [])),
        )


class CampaignRegistry:
    """Owns campaign state and compiles bounded issue missions from campaign gaps."""

    __slots__ = ("_campaigns",)

    def __init__(self, campaigns: list[CampaignRecord] | None = None) -> None:
        self._campaigns = {campaign.id: campaign for campaign in campaigns or []}

    def add_campaign(self, campaign: CampaignRecord) -> None:
        self._campaigns[campaign.id] = campaign

    def list_campaigns(self) -> list[CampaignRecord]:
        return list(self._campaigns.values())

    def summary(self, *, active_only: bool = False) -> list[dict]:
        campaigns = self.get_active_campaigns() if active_only else self.list_campaigns()
        return [
            {
                "id": campaign.id,
                "title": campaign.title,
                "status": campaign.status.value,
                "last_gap_summary": list(campaign.last_gap_summary[:3]),
                "last_evaluated_heartbeat": campaign.last_evaluated_heartbeat,
            }
            for campaign in campaigns
        ]

    def get_active_campaigns(self) -> list[CampaignRecord]:
        return [c for c in self._campaigns.values() if c.status == CampaignStatus.ACTIVE]

    def snapshot(self) -> dict:
        return {"campaigns": [campaign.to_dict() for campaign in self.list_campaigns()]}

    def restore(self, payload: dict) -> None:
        self._campaigns = {
            campaign.id: campaign
            for campaign in (CampaignRecord.from_dict(item) for item in payload.get("campaigns", []))
        }

    def evaluate(self, ctx: PhaseContext) -> list[str]:
        operations: list[str] = []
        active_missions = getattr(ctx.sankalpa.registry, "get_active_missions", lambda: [])()
        active_ids = {getattr(mission, "id", "") for mission in active_missions}

        for campaign in self.get_active_campaigns():
            if not self._due(campaign, ctx.heartbeat_count):
                continue

            campaign.last_evaluated_heartbeat = ctx.heartbeat_count
            gaps = self._compute_gaps(ctx, campaign, active_missions)
            campaign.last_gap_summary = list(gaps)

            if not gaps:
                operations.append(f"campaign_ok:{campaign.id}")
                continue

            active_bound = active_ids.intersection(campaign.derived_mission_ids)
            if len(active_bound) >= campaign.max_active_missions:
                operations.append(f"campaign_wait:{campaign.id}:active_mission")
                continue

            compiled = self._compile_issue_mission(ctx, campaign, gaps)
            if compiled is None:
                operations.append(f"campaign_blocked:{campaign.id}:issue_compilation_failed")
                continue

            campaign.derived_mission_ids.append(compiled)
            campaign.last_compiled_heartbeat = ctx.heartbeat_count
            operations.append(f"campaign_compiled:{campaign.id}:{compiled}")

        return operations

    def _due(self, campaign: CampaignRecord, heartbeat: int) -> bool:
        if campaign.last_evaluated_heartbeat == 0:
            return True
        return (heartbeat - campaign.last_evaluated_heartbeat) >= max(campaign.heartbeat_interval, 1)

    def _compute_gaps(
        self,
        ctx: PhaseContext,
        campaign: CampaignRecord,
        active_missions: list[object],
    ) -> list[str]:
        gaps: list[str] = []
        for signal in campaign.success_signals:
            if signal.kind == "heartbeat_healthy":
                diag = getattr(ctx, "_heartbeat_diagnosis", None)
                healthy = True if diag is None else bool(getattr(diag, "healthy", True))
                if healthy is not bool(signal.target):
                    gaps.append(signal.description or "heartbeat unhealthy")
            elif signal.kind == "chain_valid":
                chain_valid = bool(ctx.pokedex.verify_chain())
                if chain_valid is not bool(signal.target):
                    gaps.append(signal.description or "ledger chain invalid")
            elif signal.kind == "active_missions_at_most":
                limit = int(signal.target)
                if len(active_missions) > limit:
                    gaps.append(signal.description or f"active missions {len(active_missions)} > {limit}")
            else:
                gaps.append(signal.description or f"unknown signal:{signal.kind}")
        return gaps

    def _compile_issue_mission(
        self,
        ctx: PhaseContext,
        campaign: CampaignRecord,
        gaps: list[str],
    ) -> str | None:
        from city.issues import IssueType
        from city.missions import create_issue_mission

        title = f"[Campaign] {campaign.title}"
        body_lines = [
            f"Campaign: {campaign.id}",
            "",
            f"North star: {campaign.north_star}",
            "",
            "Current gaps:",
            *[f"- {gap}" for gap in gaps],
            "",
            f"Derived automatically on heartbeat {ctx.heartbeat_count}.",
        ]
        issue = ctx.issues.create_issue(
            title=title,
            body="\n".join(body_lines),
            issue_type=IssueType.ITERATIVE,
        )
        if issue is None:
            logger.warning("Campaign %s failed to create issue", campaign.id)
            return None

        mission_id = create_issue_mission(ctx, issue["number"], issue["title"], "intent_needed")
        if mission_id is None:
            logger.warning("Campaign %s failed to create mission for issue #%s", campaign.id, issue["number"])
            return None

        ctx.issues.bind_mission(issue["number"], mission_id)
        return mission_id