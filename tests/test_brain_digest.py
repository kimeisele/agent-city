"""Tests for city/brain_digest.py — adapted MahaCompression for Brain."""

from city.brain_digest import (
    DigestCell,
    DigestKind,
    Severity,
    digest_agent_output,
    digest_campaign_status,
    digest_economy,
    digest_mission_result,
    digest_text,
    digest_thread_state,
    render_field_summary,
)


# ── DigestCell basics ────────────────────────────────────────────────


class TestDigestCell:
    def test_render_for_brain_clean(self):
        cell = DigestCell(
            kind=DigestKind.RAW_TEXT,
            seed=12345, position=5, content_hash="abc123",
            word_count=20, line_count=2, compression_ratio=10.0,
            summary="test line", source_label="test",
        )
        rendered = cell.render_for_brain()
        assert "raw_text" in rendered
        assert "seed=12345" in rendered
        assert "test line" in rendered

    def test_render_for_brain_with_anomalies(self):
        cell = DigestCell(
            kind=DigestKind.AGENT_OUTPUT,
            seed=99, position=3, content_hash="def456",
            word_count=2, line_count=1, compression_ratio=5.0,
            severity=Severity.WARNING,
            anomalies=("too_short(2 words)",),
            summary="hi", source_label="agent:test",
        )
        rendered = cell.render_for_brain()
        assert "WARNING" in rendered
        assert "too_short" in rendered

    def test_to_dict_roundtrip(self):
        cell = DigestCell(
            kind=DigestKind.THREAD_STATE,
            seed=1, position=2, content_hash="x",
            word_count=10, line_count=3, compression_ratio=5.0,
            severity=Severity.INFO,
            anomalies=("test_anomaly",),
            key_metrics={"energy": 0.5},
            summary="test", source_label="thread:#1",
        )
        d = cell.to_dict()
        assert d["kind"] == "thread_state"
        assert d["severity"] == 1
        assert d["anomalies"] == ["test_anomaly"]
        assert d["key_metrics"]["energy"] == 0.5


# ── Agent Output Digest ──────────────────────────────────────────────


class TestDigestAgentOutput:
    def test_clean_output(self):
        text = "**sys_vyasa** — observer (DISCOVERY)\nThis is a meaningful response with good content."
        cell = digest_agent_output(text, agent_name="sys_vyasa", discussion_number=26)
        assert cell.kind == DigestKind.AGENT_OUTPUT
        assert cell.seed > 0
        assert cell.content_hash
        assert cell.source_label == "sys_vyasa:#26"
        assert cell.severity == Severity.NONE

    def test_empty_output_critical(self):
        cell = digest_agent_output("", agent_name="sys_vyasa", discussion_number=1)
        assert cell.severity == Severity.CRITICAL
        assert any("empty" in a for a in cell.anomalies)

    def test_too_short_output(self):
        cell = digest_agent_output("hi ok", agent_name="test", discussion_number=1)
        assert cell.severity >= Severity.INFO
        assert any("too_short" in a for a in cell.anomalies)

    def test_detects_brain_thought(self):
        text = "**agent** — role\n**Comprehension**: The system is healthy."
        cell = digest_agent_output(text, agent_name="agent")
        assert cell.key_metrics.get("has_brain_thought") is True

    def test_detects_routing_score(self):
        text = "**agent** — role\nSome content\n*Routed: score=0.73, intent=analyze*"
        cell = digest_agent_output(text, agent_name="agent")
        assert cell.key_metrics.get("routing_score") == 0.73

    def test_deterministic(self):
        text = "Same input always same output."
        a = digest_agent_output(text, agent_name="x", discussion_number=1)
        b = digest_agent_output(text, agent_name="x", discussion_number=1)
        assert a.seed == b.seed
        assert a.content_hash == b.content_hash
        assert a.position == b.position

    def test_repetition_detection(self):
        sentence = "The three modes of nature are important."
        text = (sentence + " ") * 5
        cell = digest_agent_output(text, agent_name="test")
        assert cell.severity >= Severity.WARNING
        assert any("repeated" in a for a in cell.anomalies)


# ── Mission Result Digest ────────────────────────────────────────────


class TestDigestMissionResult:
    def test_successful_mission(self):
        result = {"status": "completed", "owner": "sys_vyasa", "duration": 30}
        cell = digest_mission_result(result, mission_id="m1")
        assert cell.kind == DigestKind.MISSION_RESULT
        assert cell.severity == Severity.NONE
        assert cell.key_metrics["status"] == "completed"

    def test_failed_mission_warning(self):
        result = {"status": "failed", "owner": "sys_naga"}
        cell = digest_mission_result(result, mission_id="m2")
        assert cell.severity == Severity.WARNING
        assert any("failed" in a for a in cell.anomalies)

    def test_timeout_mission_warning(self):
        result = {"status": "timeout", "owner": "sys_pulse"}
        cell = digest_mission_result(result, mission_id="m3")
        assert cell.severity == Severity.WARNING


class TestDigestCampaignStatus:
    def test_campaign_with_gap_is_visible(self):
        cell = digest_campaign_status({
            "id": "internet-adaptation",
            "title": "Internet adaptation",
            "north_star": "Continuously adapt to relevant new protocols and standards.",
            "status": "active",
            "last_gap_summary": ["keep execution bounded"],
            "last_evaluated_heartbeat": 42,
        })
        assert cell.kind == DigestKind.CAMPAIGN_STATUS
        assert cell.severity == Severity.INFO
        assert cell.key_metrics["gap_count"] == 1
        assert "north_star=Continuously adapt to relevant new protocols and standards." in cell.summary
        assert "keep execution bounded" in cell.summary

    def test_campaign_without_gap_is_clean(self):
        cell = digest_campaign_status({
            "id": "mission-factory",
            "title": "Mission factory",
            "status": "active",
            "last_gap_summary": [],
        })
        assert cell.severity == Severity.NONE
        assert cell.key_metrics["gap_count"] == 0


# ── Thread State Digest ──────────────────────────────────────────────


class TestDigestThreadState:
    def test_healthy_thread(self):
        cell = digest_thread_state(
            discussion_number=26, status="active", energy=0.8,
            human_count=3, response_count=2, unresolved=True,
        )
        assert cell.kind == DigestKind.THREAD_STATE
        assert cell.severity == Severity.NONE

    def test_unresponsive_thread(self):
        cell = digest_thread_state(
            discussion_number=26, status="active", energy=0.5,
            human_count=5, response_count=0, unresolved=True,
        )
        assert cell.severity >= Severity.WARNING
        assert any("unresponsive" in a for a in cell.anomalies)

    def test_agent_spam(self):
        cell = digest_thread_state(
            discussion_number=26, status="active", energy=0.9,
            human_count=2, response_count=10, unresolved=False,
        )
        assert cell.severity == Severity.CRITICAL
        assert any("spam" in a for a in cell.anomalies)

    def test_dying_unresolved(self):
        cell = digest_thread_state(
            discussion_number=26, status="cooling", energy=0.05,
            human_count=1, response_count=0, unresolved=True,
        )
        assert cell.severity >= Severity.WARNING
        assert any("dying" in a for a in cell.anomalies)


# ── Economy Digest ───────────────────────────────────────────────────


class TestDigestEconomy:
    def test_healthy_economy(self):
        cell = digest_economy(
            total_prana=45000, avg_prana=1500.0, dormant_count=2,
            agent_count=30, min_prana=500, max_prana=3000,
        )
        assert cell.kind == DigestKind.ECONOMY_SNAPSHOT
        assert cell.severity == Severity.NONE

    def test_high_dormancy(self):
        cell = digest_economy(
            total_prana=10000, avg_prana=500.0, dormant_count=16,
            agent_count=30, min_prana=0, max_prana=2000,
        )
        assert cell.severity >= Severity.WARNING
        assert any("dormancy" in a for a in cell.anomalies)

    def test_economy_collapse(self):
        cell = digest_economy(
            total_prana=0, avg_prana=0.0, dormant_count=10,
            agent_count=10,
        )
        assert cell.severity == Severity.CRITICAL
        assert any("collapsed" in a for a in cell.anomalies)

    def test_prana_inequality(self):
        cell = digest_economy(
            total_prana=5000, avg_prana=500.0, dormant_count=0,
            agent_count=10, min_prana=0, max_prana=4000,
        )
        assert cell.severity >= Severity.WARNING
        assert any("inequality" in a for a in cell.anomalies)


# ── Generic Text Digest ──────────────────────────────────────────────


class TestDigestText:
    def test_basic(self):
        cell = digest_text("Some generic system output for the brain.", label="test")
        assert cell.kind == DigestKind.RAW_TEXT
        assert cell.source_label == "test"
        assert cell.word_count == 7

    def test_empty_text(self):
        cell = digest_text("", label="empty")
        assert cell.severity == Severity.CRITICAL


# ── Field Summary ────────────────────────────────────────────────────


class TestFieldSummary:
    def test_empty_field(self):
        rendered = render_field_summary([])
        assert "FIELD EMPTY" in rendered

    def test_mixed_severity_sorting(self):
        clean = digest_text("A perfectly normal output for the system.", label="ok")
        warning = digest_thread_state(
            discussion_number=1, status="active", energy=0.5,
            human_count=5, response_count=0, unresolved=True,
        )
        critical = digest_economy(
            total_prana=0, avg_prana=0.0, dormant_count=5, agent_count=5,
        )
        rendered = render_field_summary([clean, warning, critical])
        assert "FIELD SUMMARY" in rendered
        assert "1 critical" in rendered
        # Critical should appear before warning in output
        crit_pos = rendered.find("CRITICAL")
        warn_pos = rendered.find("WARNING")
        assert crit_pos < warn_pos

    def test_summary_counts(self):
        cells = [
            digest_text("Normal output one for the brain to read.", label="a"),
            digest_text("Normal output two for the brain to read.", label="b"),
            digest_text("", label="empty"),  # critical
        ]
        rendered = render_field_summary(cells)
        assert "3 artifacts" in rendered
        assert "1 critical" in rendered

    def test_budget_truncates_low_severity(self):
        """10E: Low-severity cells get dropped when budget is tight."""
        critical = digest_economy(
            total_prana=0, avg_prana=0.0, dormant_count=5, agent_count=5,
        )
        low1 = digest_text("Normal output one for the brain to read and evaluate.", label="a")
        low2 = digest_text("Normal output two for the brain to read and evaluate.", label="b")
        low3 = digest_text("Normal output three for the brain to read and evaluate.", label="c")
        # Very tight budget — only critical should survive
        rendered = render_field_summary([critical, low1, low2, low3], max_chars=200)
        assert "economy_collapsed" in rendered
        assert "omitted" in rendered

    def test_budget_includes_all_when_generous(self):
        """10E: All cells included when budget is large."""
        cells = [
            digest_text("Normal output for the brain.", label=f"item{i}")
            for i in range(5)
        ]
        rendered = render_field_summary(cells, max_chars=10000)
        assert "omitted" not in rendered
        assert "5 artifacts" in rendered

    def test_warnings_always_included(self):
        """10E: Warning cells always included regardless of budget."""
        warning = digest_thread_state(
            discussion_number=1, status="active", energy=0.5,
            human_count=5, response_count=0, unresolved=True,
        )
        low = digest_text("Normal output for the brain to read.", label="low")
        rendered = render_field_summary([warning, low], max_chars=100)
        assert "WARNING" in rendered
        assert "unresponsive" in rendered


# ── Token Budget Estimation ──────────────────────────────────────────


class TestTokenBudget:
    def test_zero_prana_gives_minimum(self):
        from city.brain_digest import estimate_token_budget
        chars = estimate_token_budget(0)
        assert chars >= 800  # _MIN_CHARS

    def test_high_prana_gives_more(self):
        from city.brain_digest import estimate_token_budget
        low = estimate_token_budget(9)
        high = estimate_token_budget(27)
        assert high > low

    def test_capped_at_max(self):
        from city.brain_digest import estimate_token_budget
        chars = estimate_token_budget(1000)  # absurdly high prana
        assert chars <= 12000  # _MAX_CHARS

    def test_scales_with_prana(self):
        from city.brain_digest import estimate_token_budget
        c1 = estimate_token_budget(9, prana_per_call=9)
        c2 = estimate_token_budget(18, prana_per_call=9)
        assert c2 > c1
