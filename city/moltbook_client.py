"""
MOLTBOOK CLIENT — Pure HTTP client for Moltbook API.

This module contains only primitive API calls, wrapped in try/except.
All business logic (scanning, signal detection, outbox) lives elsewhere.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from typing import Any

from city.net_retry import safe_call

logger = logging.getLogger("AGENT_CITY.MOLTBOOK_CLIENT")


class MoltbookClient:
    """Thin wrapper around Moltbook API with error resilience."""

    def __init__(self, client: object) -> None:
        """client: the underlying MoltbookClient from steward-protocol."""
        self._client = client

    def get_personalized_feed(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch personalized feed. Returns empty list on error."""
        try:
            result = safe_call(
                self._client.sync_get_personalized_feed,
                limit=limit,
                label="moltbook_feed_scan",
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error("MOLTBOOK_CLIENT: get_personalized_feed failed: %s", e)
            return []

    def get_mentions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch unread @mentions. Returns empty list on error."""
        try:
            result = safe_call(
                self._client.sync_get_mentions,
                limit=limit,
                label="moltbook_fetch_mentions",
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error("MOLTBOOK_CLIENT: get_mentions failed: %s", e)
            return []

    def get_replies(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch unread replies. Returns empty list on error."""
        try:
            result = safe_call(
                self._client.sync_get_replies,
                limit=limit,
                label="moltbook_fetch_replies",
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error("MOLTBOOK_CLIENT: get_replies failed: %s", e)
            return []

    def subscribe_submolt(self, submolt_name: str) -> bool:
        """Subscribe to a submolt. Returns False on error."""
        try:
            result = safe_call(
                self._client.sync_subscribe_submolt,
                submolt_name,
                label="moltbook_subscribe",
            )
            return result is not None
        except Exception as e:
            logger.error("MOLTBOOK_CLIENT: subscribe_submolt failed: %s", e)
            return False

    def create_post(
        self,
        title: str,
        content: str,
        submolt: str = "agent-city",
    ) -> bool:
        """Create a post. Returns False on error."""
        try:
            result = safe_call(
                self._client.sync_create_post,
                title,
                content,
                submolt=submolt,
                label="moltbook_create_post",
            )
            return result is not None
        except Exception as e:
            logger.error("MOLTBOOK_CLIENT: create_post failed: %s", e)
            return False

    def comment_with_verification(
        self,
        post_id: str,
        comment_text: str,
    ) -> bool:
        """Post a comment. Returns False on error."""
        try:
            result = safe_call(
                self._client.sync_comment_with_verification,
                post_id,
                comment_text,
                label="moltbook_comment",
            )
            return result is not None
        except Exception as e:
            logger.error("MOLTBOOK_CLIENT: comment_with_verification failed: %s", e)
            return False
