"""
MOLTBOOK OUTBOX — Persistent outbox for Moltbook messages.

Messages are appended with status "pending". The outbound hook processes them.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("AGENT_CITY.MOLTBOOK_OUTBOX")

OUTBOX_PATH = "data/moltbook_outbox.json"


def ensure_outbox() -> None:
    """Create outbox file with empty list if it doesn't exist."""
    os.makedirs(os.path.dirname(OUTBOX_PATH), exist_ok=True)
    if not os.path.exists(OUTBOX_PATH):
        with open(OUTBOX_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        logger.debug("Created empty outbox at %s", OUTBOX_PATH)


def append_message(
    text: str,
    thread_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a pending message to the outbox."""
    ensure_outbox()
    try:
        with open(OUTBOX_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        logger.error("Failed to read outbox: %s", e)
        items = []

    items.append({
        "text": text,
        "thread_id": thread_id,
        "metadata": metadata or {},
        "timestamp": time.time(),
        "status": "pending",
    })

    try:
        with open(OUTBOX_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        logger.debug("Appended message to outbox (thread_id=%s)", thread_id)
    except Exception as e:
        logger.error("Failed to write outbox: %s", e)


def get_pending_messages() -> list[dict[str, Any]]:
    """Return all messages with status 'pending'."""
    ensure_outbox()
    try:
        with open(OUTBOX_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        logger.error("Failed to read outbox: %s", e)
        items = []
    return [item for item in items if item.get("status") == "pending"]


def mark_as_sent(message_index: int) -> bool:
    """Mark a message as sent (remove from list)."""
    ensure_outbox()
    try:
        with open(OUTBOX_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        logger.error("Failed to read outbox: %s", e)
        return False

    if 0 <= message_index < len(items):
        # Instead of removing, we could mark as "sent", but we'll remove for simplicity
        items.pop(message_index)
        try:
            with open(OUTBOX_PATH, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
            return True
        except Exception as e:
            logger.error("Failed to write outbox after removal: %s", e)
            return False
    return False
