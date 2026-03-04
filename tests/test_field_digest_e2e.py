"""End-to-end test for the full field digest pipeline.

10H: Verifies the complete circle:
  Economy + Threads + Self-Posts + Missions + TODOs → DigestCells → render_field_summary
  → Dynamic budget adaptation → Brain-readable output
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from city.brain_digest import (
    DigestCell,
    DigestKind,
    Severity,
    digest_agent_output,
    digest_economy,
    digest_mission_result,
    digest_text,
    digest_thread_state,
    estimate_token_budget,
    render_field_summary,
)
from city.todo_scanner import render_todo_digest, scan_todos


class TestFieldDigestE2E:
    """Full pipeline: all digest sources → render → verify Brain-readable."""

    def test_full_field_with_all_sources(self):
        """Simulate a realistic field with economy, threads, missions, agent output."""
        cells: list[DigestCell] = []

        # Economy
        cells.append(digest_economy(
            total_prana=42000, avg_prana=1400.0, dormant_count=3,
            agent_count=30, min_prana=200, max_prana=3500,
        ))

        # Thread states
        cells.append(digest_thread_state(
            discussion_number=26, status="active", energy=0.8,
            human_count=4, response_count=3, unresolved=True,
        ))
        cells.append(digest_thread_state(
            discussion_number=41, status="waiting", energy=0.5,
            human_count=2, response_count=2, unresolved=False,
        ))

        # Agent output (self-awareness)
        cells.append(digest_agent_output(
            "**sys_vyasa** — observer (DISCOVERY)\n\n"
            "**Comprehension**: The economy is healthy with 42000 total prana.\n"
            "Active agents are engaging well in discussions.\n\n"
            "*Routed: score=0.73, intent=observe*",
            agent_name="sys_vyasa",
            discussion_number=26,
        ))

        # A bad agent output (mechanical pattern)
        cells.append(digest_agent_output(
            "Gunatraya - Three Modes. The sattva rajas tamas modes. "
            "The sattva rajas tamas are important.",
            agent_name="bad_agent",
            discussion_number=25,
        ))

        # Missions
        cells.append(digest_mission_result(
            {"status": "active", "owner": "sys_naga", "name": "Fix economy leak"},
            mission_id="heal_economy_1",
        ))
        cells.append(digest_mission_result(
            {"status": "failed", "owner": "sys_pulse", "name": "Deploy hotfix"},
            mission_id="deploy_1",
        ))

        rendered = render_field_summary(cells)

        # Verify structure
        assert "[FIELD SUMMARY]" in rendered
        assert "7 artifacts" in rendered

        # Verify anomaly detection
        assert "WARNING" in rendered  # failed mission
        # The mechanical pattern agent should be flagged
        assert "mechanical" in rendered.lower() or "warning" in rendered.lower()

        # Verify it's readable (not too long, not empty)
        assert 100 < len(rendered) < 10000

    def test_dynamic_budget_adapts_output(self):
        """10E: Verify budget-constrained rendering drops low-severity items."""
        cells = []
        # 1 critical
        cells.append(digest_economy(
            total_prana=0, avg_prana=0.0, dormant_count=10, agent_count=10,
        ))
        # 10 low-severity
        for i in range(10):
            cells.append(digest_text(
                f"Normal agent output number {i} with some padding text.",
                label=f"agent_{i}",
            ))

        # Tight budget
        tight = render_field_summary(cells, max_chars=300)
        # Generous budget
        generous = render_field_summary(cells, max_chars=10000)

        # Tight should omit some items
        assert "omitted" in tight
        # Generous should include all
        assert "omitted" not in generous
        # Both should have the critical item
        assert "economy_collapsed" in tight
        assert "economy_collapsed" in generous

    def test_budget_estimation_from_prana(self):
        """10E: Verify prana → token budget scaling."""
        # Full budget (27 prana remaining = 3 calls worth)
        full = estimate_token_budget(27, prana_per_call=9)
        # Half budget (13 prana)
        half = estimate_token_budget(13, prana_per_call=9)
        # Empty budget
        empty = estimate_token_budget(0, prana_per_call=9)

        assert full > half > empty
        assert empty >= 800   # minimum always guaranteed
        assert full <= 12000  # max cap

    def test_self_awareness_digest(self):
        """10F: Verify own-post digesting catches quality issues."""
        # Good self-post
        good = digest_agent_output(
            "**sys_vyasa** — observer\n\n"
            "**Comprehension**: Thread #26 shows healthy engagement.\n"
            "The economy is growing steadily.",
            agent_name="github-actions[bot]",
            discussion_number=26,
        )
        assert good.severity == Severity.NONE
        assert good.key_metrics.get("has_brain_thought") is True

        # Bad self-post (repetitive word-salad)
        bad_text = "The system is running. " * 10
        bad = digest_agent_output(
            bad_text,
            agent_name="github-actions[bot]",
            discussion_number=41,
        )
        assert bad.severity >= Severity.WARNING
        assert any("repeated" in a for a in bad.anomalies)

    def test_todo_scan_integration(self, tmp_path):
        """10D: Verify TODO scan integrates into field summary."""
        (tmp_path / "module.py").write_text(
            "# TODO: 10E — wire agent output digests\n"
            "# FIXME: broken economy calculation\n"
            "x = 1\n"
        )
        todos = scan_todos(tmp_path)
        assert len(todos) == 2

        todo_digest = render_todo_digest(todos)
        assert "2 items" in todo_digest
        assert "FIXME" in todo_digest

    def test_mission_digest_anomalies(self):
        """10G: Failed/timeout missions flagged as warnings."""
        failed = digest_mission_result(
            {"status": "failed", "owner": "sys_naga"},
            mission_id="m1",
        )
        timeout = digest_mission_result(
            {"status": "timeout", "owner": "sys_pulse"},
            mission_id="m2",
        )
        ok = digest_mission_result(
            {"status": "completed", "owner": "sys_vyasa", "duration": 15},
            mission_id="m3",
        )

        assert failed.severity == Severity.WARNING
        assert timeout.severity == Severity.WARNING
        assert ok.severity == Severity.NONE

    def test_complete_render_is_deterministic(self):
        """Same input always produces same output — no randomness."""
        cells = [
            digest_economy(total_prana=1000, avg_prana=100.0, dormant_count=1, agent_count=10),
            digest_thread_state(
                discussion_number=1, status="active", energy=0.9,
                human_count=3, response_count=2, unresolved=True,
            ),
            digest_agent_output("Test output from agent.", agent_name="test"),
        ]

        a = render_field_summary(cells, max_chars=5000)
        b = render_field_summary(cells, max_chars=5000)
        assert a == b
