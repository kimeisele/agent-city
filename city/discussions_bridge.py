"""
DISCUSSIONS BRIDGE — GitHub Discussions as City Social Layer.

CityService for managing Agent City's GitHub Discussions presence.
Bidirectional: scans discussions for community signals, posts city
reports + mission results as structured content.

Uses `gh api graphql` (same pattern as CityIssueManager._gh_run).

GAD-000 compliant:
- Discoverable: capabilities() lists all operations
- Observable: stats() + structured logging
- Parseable: structured dict returns
- Composable: each operation independent
- Idempotent: seen_ids dedup

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

from config import get_config

logger = logging.getLogger("AGENT_CITY.DISCUSSIONS")

_cfg = get_config().get("discussions", {})
_GH_TIMEOUT_S = _cfg.get("gh_timeout_s", 30)
_SCAN_LIMIT = _cfg.get("scan_limit", 10)
_REPORT_EVERY_N = _cfg.get("report_every_n_moksha", 4)

# ── GraphQL Queries ─────────────────────────────────────────────────

GQL_LIST_DISCUSSIONS = """
query($owner:String!, $repo:String!, $limit:Int!) {
  repository(owner:$owner, name:$repo) {
    discussions(first:$limit, orderBy:{field:CREATED_AT, direction:DESC}) {
      nodes {
        number title createdAt
        author { login }
        comments(first:5) {
          nodes { id body author { login } createdAt }
        }
      }
    }
  }
}"""

GQL_GET_DISCUSSION = """
query($owner:String!, $repo:String!, $number:Int!) {
  repository(owner:$owner, name:$repo) {
    discussion(number:$number) {
      id number title body
      comments(first:20) {
        nodes { id body author { login } }
      }
    }
  }
}"""

GQL_CREATE_DISCUSSION = """
mutation($repoId:ID!, $catId:ID!, $title:String!, $body:String!) {
  createDiscussion(input:{repositoryId:$repoId, categoryId:$catId, title:$title, body:$body}) {
    discussion { number url }
  }
}"""

GQL_ADD_COMMENT = """
mutation($discussionId:ID!, $body:String!) {
  addDiscussionComment(input:{discussionId:$discussionId, body:$body}) {
    comment { id }
  }
}"""


# ── GraphQL Helper ──────────────────────────────────────────────────


def _gh_graphql(query: str, variables: dict | None = None) -> dict | None:
    """Run a GraphQL query via gh CLI. Returns parsed JSON or None.

    Uses -f for string variables, -F for integer variables.
    Adapted from city/issues.py:_gh_run().
    """
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            if isinstance(v, int):
                args.extend(["-F", f"{k}={v}"])
            else:
                args.extend(["-f", f"{k}={v}"])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_S,
        )
        if result.returncode != 0:
            logger.warning("gh graphql failed: %s", result.stderr.strip()[:200])
            return None
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("gh CLI unavailable or timed out: %s", e)
        return None
    except json.JSONDecodeError as e:
        logger.warning("gh graphql: invalid JSON response: %s", e)
        return None


# ── Service ─────────────────────────────────────────────────────────


@dataclass
class DiscussionsBridge:
    """Agent City's GitHub Discussions bridge.

    Wired as CityService via ServiceFactory.
    GAD-000: Discoverable, Observable, Parseable, Composable, Idempotent.
    """

    _repo_id: str
    _owner: str
    _repo: str
    _categories: dict = field(default_factory=dict)

    # Persistent state
    _seen_discussion_numbers: set[int] = field(default_factory=set)
    _seen_comment_ids: set[str] = field(default_factory=set)
    _last_report_hb: int = 0
    _ops: dict = field(default_factory=lambda: {
        "scans": 0, "posts": 0, "comments": 0,
    })

    # ── GAD-000: Discoverable ───────────────────────────────────────

    @staticmethod
    def capabilities() -> list[dict]:
        return [
            {"op": "scan", "phase": "GENESIS", "idempotent": True},
            {"op": "create_discussion", "phase": "KARMA", "idempotent": False},
            {"op": "comment", "phase": "KARMA", "idempotent": False},
            {"op": "post_city_report", "phase": "MOKSHA", "idempotent": True},
            {"op": "cross_post", "phase": "MOKSHA", "idempotent": True},
        ]

    # ── Phase Handlers ──────────────────────────────────────────────

    def scan(self, limit: int | None = None) -> list[dict]:
        """GENESIS: List recent discussions, return new threads + unseen comments.

        Returns list of {number, title, author, new_comments: [...]}.
        Idempotent: already-seen discussions/comments are skipped.
        """
        if limit is None:
            limit = _SCAN_LIMIT

        data = _gh_graphql(
            GQL_LIST_DISCUSSIONS,
            {"owner": self._owner, "repo": self._repo, "limit": limit},
        )
        if data is None:
            return []

        nodes = (
            data.get("data", {})
            .get("repository", {})
            .get("discussions", {})
            .get("nodes", [])
        )

        self._ops["scans"] += 1
        signals: list[dict] = []

        for node in nodes:
            number = node.get("number", 0)
            if not number:
                continue

            author = (node.get("author") or {}).get("login", "")
            comments = (node.get("comments") or {}).get("nodes", [])

            # Collect unseen comments
            new_comments: list[dict] = []
            for c in comments:
                cid = c.get("id", "")
                if cid and cid not in self._seen_comment_ids:
                    self._seen_comment_ids.add(cid)
                    new_comments.append({
                        "id": cid,
                        "body": c.get("body", ""),
                        "author": (c.get("author") or {}).get("login", ""),
                    })

            is_new = number not in self._seen_discussion_numbers
            self._seen_discussion_numbers.add(number)

            if is_new or new_comments:
                signals.append({
                    "number": number,
                    "title": node.get("title", ""),
                    "author": author,
                    "is_new": is_new,
                    "new_comments": new_comments,
                })

        if signals:
            logger.info(
                "DISCUSSIONS: scanned %d threads, %d with new activity",
                len(nodes), len(signals),
            )
        return signals

    def comment(self, discussion_number: int, body: str) -> bool:
        """KARMA: Add comment to a discussion by number.

        Requires fetching the discussion's node ID first (GraphQL mutation
        needs the opaque ID, not the number).
        """
        # Get discussion node ID
        data = _gh_graphql(
            GQL_GET_DISCUSSION,
            {"owner": self._owner, "repo": self._repo, "number": discussion_number},
        )
        if data is None:
            return False

        disc = (
            data.get("data", {})
            .get("repository", {})
            .get("discussion")
        )
        if disc is None:
            logger.warning("DISCUSSIONS: discussion #%d not found", discussion_number)
            return False

        disc_id = disc.get("id", "")
        if not disc_id:
            return False

        result = _gh_graphql(
            GQL_ADD_COMMENT,
            {"discussionId": disc_id, "body": body},
        )
        if result is None:
            return False

        comment_id = (
            result.get("data", {})
            .get("addDiscussionComment", {})
            .get("comment", {})
            .get("id", "")
        )
        if comment_id:
            self._seen_comment_ids.add(comment_id)
            self._ops["comments"] += 1
            logger.info("DISCUSSIONS: commented on #%d", discussion_number)
            return True

        return False

    def create_discussion(
        self, title: str, body: str, category: str = "General",
    ) -> int | None:
        """Create a new discussion thread. Returns discussion number or None."""
        cat_id = self._categories.get(category)
        if not cat_id:
            logger.warning(
                "DISCUSSIONS: unknown category '%s' (available: %s)",
                category, list(self._categories.keys()),
            )
            return None

        result = _gh_graphql(
            GQL_CREATE_DISCUSSION,
            {"repoId": self._repo_id, "catId": cat_id, "title": title, "body": body},
        )
        if result is None:
            return None

        disc = (
            result.get("data", {})
            .get("createDiscussion", {})
            .get("discussion", {})
        )
        number = disc.get("number")
        if number:
            self._seen_discussion_numbers.add(number)
            self._ops["posts"] += 1
            logger.info("DISCUSSIONS: created #%d — %s", number, title[:60])
        return number

    def post_city_report(self, heartbeat: int, reflection: dict) -> bool:
        """MOKSHA: Post city report as Announcement discussion.

        Rate-limited: 1 report per N MOKSHA cycles (config: report_every_n_moksha).
        """
        if heartbeat <= self._last_report_hb:
            return False

        moksha_gap = heartbeat - self._last_report_hb
        if self._last_report_hb > 0 and moksha_gap < _REPORT_EVERY_N:
            return False

        stats = reflection.get("city_stats", {})
        title = f"City Report \u2014 Heartbeat #{heartbeat}"
        lines = [
            f"**Population**: {stats.get('total', 0)} agents "
            f"({stats.get('alive', 0)} alive)",
            f"**Chain integrity**: {'valid' if reflection.get('chain_valid') else 'BROKEN'}",
        ]

        # Council
        council_seats = 0
        proposals = 0
        if "spawner_stats" in reflection:
            council_seats = reflection.get("spawner_stats", {}).get("council_seats", 0)
        lines.append(f"**Council**: {council_seats} seats, {proposals} open proposals")

        # Missions
        terminal = reflection.get("mission_results_terminal", [])
        if terminal:
            lines.append(f"\n**Missions completed this cycle**: {len(terminal)}")
            for m in terminal[:5]:
                lines.append(f"- {m.get('name', '?')}: {m.get('status', '?')}")

        # Immune
        immune = reflection.get("immune_stats", {})
        if immune:
            lines.append(
                f"\n**Immune**: {immune.get('heals_attempted', 0)} heals attempted, "
                f"{immune.get('heals_succeeded', 0)} succeeded"
            )

        body = "\n".join(lines)
        number = self.create_discussion(title, body, category="Announcements")
        if number is not None:
            self._last_report_hb = heartbeat
            return True
        return False

    def cross_post_mission_results(self, results: list[dict]) -> int:
        """MOKSHA: Cross-post terminal mission results to 'Show and tell'.

        Returns count of discussions created.
        """
        posted = 0
        for mission in results:
            name = mission.get("name", "Unknown")
            status = mission.get("status", "?")
            owner = mission.get("owner", "unknown")

            title = f"[Mission Result] {name}"
            lines = [
                f"**Status**: {status}",
                f"**Owner**: {owner}",
            ]
            pr_url = mission.get("pr_url")
            if pr_url:
                lines.append(f"**PR**: {pr_url}")

            body = "\n".join(lines)
            number = self.create_discussion(title, body, category="Show and tell")
            if number is not None:
                posted += 1

        return posted

    # ── Persistence ─────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Serialize state for persistence across ephemeral restarts."""
        return {
            "seen_discussion_numbers": sorted(self._seen_discussion_numbers),
            "seen_comment_ids": sorted(self._seen_comment_ids)[-500:],
            "last_report_hb": self._last_report_hb,
            "ops": dict(self._ops),
        }

    def restore(self, data: dict) -> None:
        """Restore from persisted snapshot."""
        self._seen_discussion_numbers = set(data.get("seen_discussion_numbers", []))
        self._seen_comment_ids = set(data.get("seen_comment_ids", []))
        self._last_report_hb = data.get("last_report_hb", 0)
        ops = data.get("ops", {})
        self._ops = {
            "scans": ops.get("scans", 0),
            "posts": ops.get("posts", 0),
            "comments": ops.get("comments", 0),
        }
        logger.info(
            "RESTORED: %d discussions seen, %d comments seen, %d ops",
            len(self._seen_discussion_numbers),
            len(self._seen_comment_ids),
            sum(self._ops.values()),
        )

    # ── GAD-000: Observable ─────────────────────────────────────────

    def stats(self) -> dict:
        """Complete service state for diagnostics and reflection."""
        return {
            "discussions_seen": len(self._seen_discussion_numbers),
            "comments_seen": len(self._seen_comment_ids),
            "last_report_hb": self._last_report_hb,
            "ops": dict(self._ops),
        }
