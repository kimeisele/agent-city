"""Campaign tests — long-horizon heartbeat evaluation above Sankalpa."""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_ctx(tmp, **kwargs):
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from city.phases import PhaseContext

    bank = CivicBank(db_path=str(tmp / "economy.db"))
    pdx = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
    gw = CityGateway()
    net = CityNetwork(_address_book=gw.address_book, _gateway=gw)
    return PhaseContext(
        pokedex=pdx,
        gateway=gw,
        network=net,
        heartbeat_count=10,
        offline_mode=True,
        state_path=tmp / "state.json",
        **kwargs,
    )


def test_campaign_registry_snapshot_round_trip():
    from city.campaigns import CampaignRecord, CampaignRegistry, CampaignSignal

    registry = CampaignRegistry()
    registry.add_campaign(
        CampaignRecord(
            id="north-star",
            title="North Star",
            north_star="Keep heartbeat healthy.",
            success_signals=[CampaignSignal(kind="heartbeat_healthy", description="heartbeat must stay healthy")],
            last_gap_summary=["heartbeat must stay healthy"],
        )
    )

    payload = registry.snapshot()
    restored = CampaignRegistry()
    restored.restore(payload)

    summary = restored.summary(active_only=True)
    assert summary[0]["id"] == "north-star"
    assert summary[0]["last_gap_summary"] == ["heartbeat must stay healthy"]


def test_campaign_hook_compiles_issue_mission_from_gap():
    tmp = Path(tempfile.mkdtemp())
    try:
        from city.campaigns import CampaignRecord, CampaignRegistry, CampaignSignal
        from city.hooks.dharma.governance import CampaignEvaluationHook

        active_mission = MagicMock()
        active_mission.id = "heal_existing_9"

        mock_registry = MagicMock()
        mock_registry.get_active_missions.return_value = [active_mission]

        mock_sankalpa = MagicMock()
        mock_sankalpa.registry = mock_registry

        mock_issues = MagicMock()
        mock_issues.create_issue.return_value = {
            "number": 42,
            "title": "[Campaign] Keep system focus",
        }

        campaigns = CampaignRegistry(
            [
                CampaignRecord(
                    id="system-focus",
                    title="Keep system focus",
                    north_star="Bound active work so heartbeat stays strategic.",
                    success_signals=[
                        CampaignSignal(
                            kind="active_missions_at_most",
                            target=0,
                            description="too many active missions for focused execution",
                        )
                    ],
                )
            ]
        )

        ctx = _make_ctx(tmp, sankalpa=mock_sankalpa, issues=mock_issues, campaigns=campaigns)
        operations: list[str] = []

        CampaignEvaluationHook().execute(ctx, operations)

        assert any(op.startswith("campaign_compiled:system-focus:issue_42_10") for op in operations)
        mock_issues.create_issue.assert_called_once()
        mock_issues.bind_mission.assert_called_once_with(42, "issue_42_10")
        mock_sankalpa.registry.add_mission.assert_called_once()
        mission = mock_sankalpa.registry.add_mission.call_args[0][0]
        assert mission.id == "issue_42_10"
        assert mission.name == "IssueHeal: #42"
        assert campaigns.summary(active_only=True)[0]["last_gap_summary"] == [
            "too many active missions for focused execution"
        ]
    finally:
        shutil.rmtree(tmp)


def test_load_campaign_payload_accepts_single_object(tmp_path: Path):
    from city.campaigns import load_campaign_payload

    payload_path = tmp_path / "campaign.json"
    payload_path.write_text('{"id": "north-star", "title": "North Star", "north_star": "Stay aligned."}')

    payload = load_campaign_payload(payload_path)
    assert payload == {
        "campaigns": [
            {"id": "north-star", "title": "North Star", "north_star": "Stay aligned."}
        ]
    }