"""
HeartbeatObserver — Self-Observation via GitHub Actions API.
=============================================================

The system reads its OWN recent heartbeat runs and Discussion activity
to build a live picture of its operational state. This is the difference
between a cron job and an AGI infrastructure node.

What it observes:
  1. Recent workflow runs (success/failure rate, timing, gaps)
  2. Discussion activity (last post time, comment velocity)
  3. Operational anomalies (runs failing, posts stopped, brain offline)

The observer produces a HeartbeatDiagnosis dataclass that hooks can
consume for self-repair decisions.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.HEARTBEAT_OBSERVER")

_GH_TIMEOUT_S = 15


# ── Diagnosis ────────────────────────────────────────────────────────


@dataclass
class RunInfo:
    """Single workflow run summary."""

    run_id: str
    status: str  # "success", "failure", "cancelled"
    elapsed_s: float
    age_s: float  # seconds since run started
    title: str = ""


@dataclass
class DiscussionActivity:
    """Activity snapshot for a single discussion."""

    number: int
    title: str
    comment_count: int
    last_update: str  # ISO timestamp


@dataclass
class HeartbeatDiagnosis:
    """Self-observation result. Built from live GitHub API data."""

    # Workflow runs
    recent_runs: list[RunInfo] = field(default_factory=list)
    success_rate: float = 1.0
    last_success_age_s: float = 0.0
    last_failure_age_s: float = -1.0  # -1 = no recent failure
    avg_elapsed_s: float = 0.0

    # Discussion activity
    discussions: list[DiscussionActivity] = field(default_factory=list)
    total_comments: int = 0
    last_discussion_update: str = ""

    # Anomalies detected
    anomalies: list[str] = field(default_factory=list)

    # Metadata
    observed_at: float = 0.0
    observer_error: str = ""

    @property
    def healthy(self) -> bool:
        return len(self.anomalies) == 0

    def summary(self) -> str:
        """One-line summary for logs."""
        runs = len(self.recent_runs)
        rate = f"{self.success_rate:.0%}"
        anomaly_str = f", anomalies={len(self.anomalies)}" if self.anomalies else ""
        return f"runs={runs} success={rate} discussions={len(self.discussions)}{anomaly_str}"


# ── Observer ─────────────────────────────────────────────────────────


@dataclass
class HeartbeatObserver:
    """Reads the system's own GitHub Actions runs + Discussions.

    Pure observation — no side effects, no posts, no mutations.
    Produces a HeartbeatDiagnosis for downstream hooks to act on.
    """

    _owner: str = ""
    _repo: str = ""
    _workflow: str = "agent-city-heartbeat.yml"
    _run_limit: int = 10
    _discussion_limit: int = 5

    # Anomaly thresholds
    _max_gap_minutes: float = 45.0  # 3× the 15-min schedule = something is wrong
    _min_success_rate: float = 0.7
    _stale_discussion_hours: float = 6.0

    def observe(self) -> HeartbeatDiagnosis:
        """Run full observation cycle. Returns diagnosis."""
        diag = HeartbeatDiagnosis(observed_at=time.time())

        if not self._owner or not self._repo:
            diag.observer_error = "owner/repo not configured"
            return diag

        # 1. Observe workflow runs
        try:
            self._observe_runs(diag)
        except Exception as e:
            diag.observer_error = f"runs: {e}"
            logger.warning("HeartbeatObserver: run observation failed: %s", e)

        # 2. Observe discussions
        try:
            self._observe_discussions(diag)
        except Exception as e:
            if not diag.observer_error:
                diag.observer_error = f"discussions: {e}"
            logger.warning("HeartbeatObserver: discussion observation failed: %s", e)

        # 3. Detect anomalies
        self._detect_anomalies(diag)

        logger.info("HeartbeatObserver: %s", diag.summary())
        return diag

    def _observe_runs(self, diag: HeartbeatDiagnosis) -> None:
        """Fetch recent workflow runs via gh CLI."""
        result = subprocess.run(
            [
                "gh", "run", "list",
                f"--workflow={self._workflow}",
                f"--limit={self._run_limit}",
                "--json=databaseId,status,conclusion,updatedAt,name",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_S,
            cwd=".",
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh run list failed: {result.stderr[:200]}")

        runs_data = json.loads(result.stdout)
        now = time.time()

        success_count = 0
        elapsed_total = 0.0

        for run in runs_data:
            conclusion = run.get("conclusion", "unknown")
            status = run.get("status", "unknown")

            # Map conclusion to simple status
            if conclusion == "success":
                simple_status = "success"
                success_count += 1
            elif conclusion in ("failure", "startup_failure"):
                simple_status = "failure"
            elif status == "in_progress":
                simple_status = "running"
            else:
                simple_status = conclusion or status

            # Parse age from updatedAt
            age_s = 0.0
            updated = run.get("updatedAt", "")
            if updated:
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    age_s = now - dt.timestamp()
                except Exception:
                    pass

            info = RunInfo(
                run_id=str(run.get("databaseId", "")),
                status=simple_status,
                elapsed_s=0,  # gh run list doesn't give elapsed directly
                age_s=age_s,
                title=run.get("name", ""),
            )
            diag.recent_runs.append(info)

        total = len(diag.recent_runs)
        if total > 0:
            diag.success_rate = success_count / total
            diag.avg_elapsed_s = elapsed_total / total if elapsed_total else 0

        # Find last success and last failure ages
        for run in diag.recent_runs:
            if run.status == "success":
                diag.last_success_age_s = run.age_s
                break
        for run in diag.recent_runs:
            if run.status == "failure":
                diag.last_failure_age_s = run.age_s
                break

    def _observe_discussions(self, diag: HeartbeatDiagnosis) -> None:
        """Fetch recent discussion activity via gh CLI GraphQL."""
        query = (
            'query($owner:String!, $repo:String!, $limit:Int!) {'
            '  repository(owner:$owner, name:$repo) {'
            '    discussions(first:$limit, orderBy:{field:UPDATED_AT, direction:DESC}) {'
            '      nodes { number title updatedAt comments { totalCount } }'
            '    }'
            '  }'
            '}'
        )

        result = subprocess.run(
            [
                "gh", "api", "graphql",
                "-f", f"query={query}",
                "-f", f"owner={self._owner}",
                "-f", f"repo={self._repo}",
                "-F", f"limit={self._discussion_limit}",
            ],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_S,
            cwd=".",
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh api graphql failed: {result.stderr[:200]}")

        data = json.loads(result.stdout)
        nodes = (
            data.get("data", {})
            .get("repository", {})
            .get("discussions", {})
            .get("nodes", [])
        )

        for node in nodes:
            activity = DiscussionActivity(
                number=node.get("number", 0),
                title=node.get("title", ""),
                comment_count=node.get("comments", {}).get("totalCount", 0),
                last_update=node.get("updatedAt", ""),
            )
            diag.discussions.append(activity)
            diag.total_comments += activity.comment_count

        if diag.discussions:
            diag.last_discussion_update = diag.discussions[0].last_update

    def _detect_anomalies(self, diag: HeartbeatDiagnosis) -> None:
        """Analyze observation data for anomalies."""

        # A1: Success rate too low
        if diag.recent_runs and diag.success_rate < self._min_success_rate:
            failures = [r for r in diag.recent_runs if r.status == "failure"]
            diag.anomalies.append(
                f"heartbeat_failing: {len(failures)}/{len(diag.recent_runs)} "
                f"runs failed (rate={diag.success_rate:.0%})"
            )

        # A2: Gap between runs (last success too old)
        if diag.last_success_age_s > self._max_gap_minutes * 60:
            mins = diag.last_success_age_s / 60
            diag.anomalies.append(
                f"heartbeat_gap: last success was {mins:.0f}min ago "
                f"(threshold={self._max_gap_minutes:.0f}min)"
            )

        # A3: Consecutive failures (last 3+ runs all failed)
        if len(diag.recent_runs) >= 3:
            last_3 = [r.status for r in diag.recent_runs[:3]]
            if all(s == "failure" for s in last_3):
                diag.anomalies.append(
                    "heartbeat_crash_loop: 3+ consecutive failures"
                )

        # A4: Discussion activity stale
        if diag.last_discussion_update:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(
                    diag.last_discussion_update.replace("Z", "+00:00")
                )
                hours_since = (time.time() - dt.timestamp()) / 3600
                if hours_since > self._stale_discussion_hours:
                    diag.anomalies.append(
                        f"discussions_stale: no updates in {hours_since:.1f}h "
                        f"(threshold={self._stale_discussion_hours}h)"
                    )
            except Exception:
                pass

    def stats(self) -> dict:
        """Observer configuration stats."""
        return {
            "owner": self._owner,
            "repo": self._repo,
            "workflow": self._workflow,
            "run_limit": self._run_limit,
            "discussion_limit": self._discussion_limit,
        }
