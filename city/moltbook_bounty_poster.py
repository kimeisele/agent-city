"""
MOLTBOOK AUTONOMOUS BOUNTY POSTER
==================================

Takes a propagation signal (from diagnostics_bounty_hook.py) and posts it
directly to Moltbook WITHOUT human approval.

Pure event-driven emission: Signal in → Moltbook post out.

Bounty tags are baked into the post so external agents and bounty-tracking
systems can instantly recognize monetized work.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("AGENT_CITY.MOLTBOOK_BOUNTY_POSTER")


class MoltbookBountyPoster:
    """Autonomous posting of federation help-calls with bounty metadata."""

    def __init__(self, moltbook_client: object | None = None):
        """
        Args:
            moltbook_client: MoltbookClient instance (can be None for dry-run)
        """
        self._client = moltbook_client
        self._post_log: list[dict] = []

    def format_bounty_post(
        self, 
        title: str,
        content: str,
        gap_id: str,
        github_issue: int,
        bounty_tags: list[str] | None = None,
    ) -> str:
        """Format post content with bounty hooks for external systems.
        
        Args:
            title: Post title (e.g. "🆘 Federation NADI Reliability")
            content: Main content
            gap_id: Gap identifier
            github_issue: Issue number for this bounty
            bounty_tags: Extra tags (e.g. ["[BOUNTY_AVAILABLE]"])
            
        Returns:
            Formatted string ready for Moltbook posting
        """
        bounty_tags = bounty_tags or []
        
        formatted = f"""{title}

{content}

---
**Bounty Info:**
{' '.join(bounty_tags)}
Issue: github.com/kimeisele/agent-city/issues/{github_issue}
Gap ID: {gap_id}
System: agent-city federation

[Auto-posted by Autonomous Bounty Hook]"""
        
        return formatted

    def post_to_moltbook(
        self,
        title: str,
        content: str,
        submolt: str = "agents",
        dry_run: bool = False,
    ) -> dict:
        """Post directly to Moltbook.
        
        Args:
            title: Post title
            content: Formatted content (with bounty tags)
            submolt: Target submolt (default: "agents")
            dry_run: If True, log without posting
            
        Returns:
            {success: bool, post_id: str, error: str}
        """
        result = {
            "success": False,
            "post_id": "",
            "error": "",
        }
        
        try:
            if dry_run or self._client is None:
                logger.info(
                    "DRY_RUN: Would post to m/%s | Title: %s",
                    submolt,
                    title[:60],
                )
                result["success"] = True
                result["post_id"] = f"dry_run_{int(__import__('time').time())}"
                return result
            
            # Real posting
            post_result = self._client.sync_create_post(
                title=title,
                content=content,
                submolt=submolt,
            )
            
            result["success"] = True
            result["post_id"] = post_result.get("id", "unknown")
            
            logger.info(
                "BOUNTY_POST: Published to m/%s | ID: %s | Title: %s",
                submolt,
                result["post_id"],
                title[:60],
            )
            
            return result
        
        except Exception as e:
            result["error"] = str(e)
            logger.error("BOUNTY_POST failed: %s", e)
            return result

    def emit_from_propagation_signal(
        self,
        propagation_result: dict,
        dry_run: bool = False,
    ) -> dict:
        """Take output from diagnostics_bounty_hook and emit to Moltbook.
        
        Args:
            propagation_result: Dict from get_diagnostics_bounty_hook().trigger_propagation()
                Must have: gap_id, moltbook_post, bounty_tags
            dry_run: If True, don't actually post
            
        Returns:
            {success, post_id, error, gap_id}
        """
        gap_id = propagation_result.get("gap_id")
        moltbook_post = propagation_result.get("moltbook_post", {})
        bounty_tags = propagation_result.get("bounty_tags", [])
        internal_mission = propagation_result.get("internal_mission", {})
        
        # Format with bounty tags
        formatted_content = self.format_bounty_post(
            title=moltbook_post.get("title", "Help Wanted"),
            content=moltbook_post.get("content", ""),
            gap_id=gap_id,
            github_issue=internal_mission.get("github_issue", 0),
            bounty_tags=bounty_tags,
        )
        
        # Post
        result = self.post_to_moltbook(
            title=moltbook_post.get("title", ""),
            content=formatted_content,
            submolt=moltbook_post.get("submolt", "agents"),
            dry_run=dry_run,
        )
        
        result["gap_id"] = gap_id
        self._post_log.append(result)
        
        return result

    def get_post_log(self) -> list[dict]:
        """Get history of all bounty posts emitted this session."""
        return self._post_log


# Global instance
_poster = MoltbookBountyPoster()


def get_moltbook_bounty_poster() -> MoltbookBountyPoster:
    """Get the global Moltbook bounty poster."""
    return _poster
