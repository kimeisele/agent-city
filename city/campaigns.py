"""Campaign registry — heartbeat-driven long-horizon orientation above Sankalpa missions."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.CAMPAIGNS")


def load_campaign_payload(path: Path) -> dict:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "campaigns" in payload:
        return payload
    if isinstance(payload, dict) and "id" in payload:
        return {"campaigns": [payload]}
    raise ValueError("campaign file must contain a campaign object or {\"campaigns\": [...]} payload")


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
    derived_issue_numbers: list[int] = field(default_factory=list)
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
            derived_issue_numbers=[int(number) for number in data.get("derived_issue_numbers", [])],
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

    def get_campaign(self, campaign_id: str) -> CampaignRecord | None:
        return self._campaigns.get(campaign_id)

    def list_campaigns(self) -> list[CampaignRecord]:
        return sorted(self._campaigns.values(), key=lambda campaign: campaign.id)

    def apply_payload(self, payload: dict, *, replace: bool = False) -> list[CampaignRecord]:
        campaigns = [CampaignRecord.from_dict(item) for item in payload.get("campaigns", [])]
        if replace:
            self._campaigns = {}
        for campaign in campaigns:
            self._campaigns[campaign.id] = campaign
        return campaigns

    def summary(self, *, active_only: bool = False) -> list[dict]:
        campaigns = self.get_active_campaigns() if active_only else self.list_campaigns()
        return [
            {
                "id": campaign.id,
                "title": campaign.title,
                "north_star": campaign.north_star,
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
            campaign.derived_mission_ids = [
                mission_id for mission_id in campaign.derived_mission_ids if mission_id in active_ids
            ]
            campaign.derived_issue_numbers = [
                issue_number
                for issue_number in campaign.derived_issue_numbers
                if self._is_issue_open(ctx, issue_number)
            ]

            if not gaps:
                operations.append(f"campaign_ok:{campaign.id}")
                continue

            active_bound = set(campaign.derived_mission_ids)
            if len(active_bound) >= campaign.max_active_missions:
                operations.append(f"campaign_wait:{campaign.id}:active_mission")
                continue

            compiled, issue_number = self._compile_issue_mission(ctx, campaign, gaps)
            if compiled is None:
                operations.append(f"campaign_blocked:{campaign.id}:issue_compilation_failed")
                continue

            if compiled not in campaign.derived_mission_ids:
                campaign.derived_mission_ids.append(compiled)
            if issue_number is not None and issue_number not in campaign.derived_issue_numbers:
                campaign.derived_issue_numbers.append(issue_number)
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
    ) -> tuple[str | None, int | None]:
        from city.issues import IssueType
        from city.missions import create_issue_mission

        reusable_issue_number = self._find_reusable_issue_number(ctx, campaign)
        if reusable_issue_number is not None:
            mission_id = create_issue_mission(
                ctx,
                reusable_issue_number,
                f"[Campaign] {campaign.title}",
                "intent_needed",
            )
            if mission_id is None:
                logger.warning(
                    "Campaign %s failed to reuse issue #%s",
                    campaign.id,
                    reusable_issue_number,
                )
                return None, reusable_issue_number

            ctx.issues.bind_mission(reusable_issue_number, mission_id)
            logger.info(
                "Campaign %s reused issue #%s via mission %s",
                campaign.id,
                reusable_issue_number,
                mission_id,
            )
            return mission_id, reusable_issue_number

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
            return None, None

        mission_id = create_issue_mission(ctx, issue["number"], issue["title"], "intent_needed")
        if mission_id is None:
            logger.warning("Campaign %s failed to create mission for issue #%s", campaign.id, issue["number"])
            return None, issue["number"]

        ctx.issues.bind_mission(issue["number"], mission_id)
        return mission_id, issue["number"]

    def _find_reusable_issue_number(self, ctx: PhaseContext, campaign: CampaignRecord) -> int | None:
        for issue_number in reversed(campaign.derived_issue_numbers):
            if self._is_issue_open(ctx, issue_number):
                return issue_number
        return None

    def _is_issue_open(self, ctx: PhaseContext, issue_number: int) -> bool:
        checker = getattr(ctx.issues, "is_issue_open", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(issue_number))
        except Exception as e:
            logger.warning("Campaign issue-open check failed for #%s: %s", issue_number, e)
            return False