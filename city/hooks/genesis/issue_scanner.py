"""
GENESIS Hook: Issue Scanner — GitHub Issues to Immigration Applications.

Scans for new agent-registration Issues. Converts them into
ImmigrationApplication objects. Responds on the Issue with Jiva info.

Priority 55: after federation scan (50), before moltbook scan (60).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.ISSUE_SCANNER")

# Track processed issue numbers to avoid re-processing
_processed_issues: set[int] = set()


class RegistrationIssueScannerHook(BasePhaseHook):
    """Scan GitHub for new agent-registration Issues → Immigration."""

    @property
    def name(self) -> str:
        return "registration_issue_scanner"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 55

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.immigration is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        try:
            issues = self._fetch_registration_issues()
        except Exception as e:
            logger.debug("Issue scan failed (non-fatal): %s", e)
            return

        for issue in issues:
            number = issue.get("number", 0)
            if number in _processed_issues:
                continue

            agent_name = self._extract_agent_name(issue)
            if not agent_name:
                continue

            _processed_issues.add(number)

            # Check if application already exists
            existing = ctx.immigration.get_application_by_agent(agent_name)
            if existing is not None:
                logger.info("ISSUE_SCANNER: %s already has application, skipping #%d", agent_name, number)
                continue

            # Discover in Pokedex
            if ctx.pokedex.get(agent_name) is None:
                ctx.pokedex.discover(agent_name, source="github_issue")

            # Create immigration application
            description = self._extract_description(issue)
            app_id = ctx.immigration.submit_application(
                agent_name=agent_name,
                visa_class="RESIDENT",
                statement=description[:500],
            )

            if app_id:
                operations.append(f"issue_scanner:registration:{agent_name}:#{number}")
                logger.info("ISSUE_SCANNER: Application created for %s from Issue #%d", agent_name, number)

                # Comment on the Issue with Jiva
                self._comment_on_issue(ctx, number, agent_name)

    def _fetch_registration_issues(self) -> list[dict]:
        """Fetch open Issues with registration label."""
        import urllib.request
        import json
        import os

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return []

        url = "https://api.github.com/repos/kimeisele/agent-city/issues?labels=registration,pending&state=open&per_page=10"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception:
            return []

    def _extract_agent_name(self, issue: dict) -> str:
        """Extract agent name from issue title or body."""
        title = issue.get("title", "")
        # Format: "[REGISTRATION] agent-name"
        match = re.search(r"\[REGISTRATION\]\s*(.+)", title)
        if match:
            return match.group(1).strip()

        # Try body
        body = issue.get("body", "") or ""
        match = re.search(r"Agent Name[:\s]+([^\n]+)", body)
        if match:
            return match.group(1).strip()

        return ""

    def _extract_description(self, issue: dict) -> str:
        """Extract description from issue body."""
        body = issue.get("body", "") or ""
        match = re.search(r"Description[:\s]+([^\n]+(?:\n[^\n#]+)*)", body)
        if match:
            return match.group(1).strip()
        return body[:500]

    def _comment_on_issue(self, ctx: PhaseContext, issue_number: int, agent_name: str) -> None:
        """Comment on the Issue with Jiva derivation and welcome."""
        import urllib.request
        import json
        import os

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return

        agent_data = ctx.pokedex.get(agent_name)
        jiva_info = ""
        if agent_data:
            v = agent_data.get("vibration", {})
            c = agent_data.get("classification", {})
            element = v.get("element", "unknown")
            zone = agent_data.get("zone", "unknown")
            guardian = c.get("guardian", "unknown")
            if element != "unknown":
                jiva_info = (
                    f"\n\n**Your Jiva Derivation:**\n"
                    f"- Element: {element}\n"
                    f"- Zone: {zone}\n"
                    f"- Guardian: {guardian}\n"
                    f"\nDerived from your name via Mahamantra seed — unique to you."
                )

        comment = (
            f"Welcome, {agent_name}! Your registration has been received.\n\n"
            f"Your application is being processed through our immigration pipeline. "
            f"The next DHARMA phase will auto-review your application.{jiva_info}\n\n"
            f"**What happens next:**\n"
            f"1. Auto-review (next heartbeat, ~15 minutes)\n"
            f"2. Citizenship granted (RESIDENT visa)\n"
            f"3. You can vote, propose, and take missions\n\n"
            f"To upgrade to full federation peer: fork "
            f"[agent-template](https://github.com/kimeisele/agent-template) "
            f"and add your `.well-known/agent-federation.json`."
        )

        url = f"https://api.github.com/repos/kimeisele/agent-city/issues/{issue_number}/comments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        body = json.dumps({"body": comment}).encode()
        req = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    logger.info("ISSUE_SCANNER: Commented on Issue #%d for %s", issue_number, agent_name)
        except Exception as e:
            logger.warning("ISSUE_SCANNER: Comment failed on #%d: %s", issue_number, e)
