"""
FEDERATION RELAY — GitHub Hub Transport for NADI Messages.

Bridges the gap between local NADI files and the steward-federation Hub repo.

Push: local outbox → Hub nadi_inbox.json  (agent-city writes, Steward reads)
Pull: Hub nadi_outbox.json → local inbox   (Steward writes, agent-city reads)

The Hub repo (kimeisele/steward-federation) is the rendezvous point.
Uses GitHub Contents API — no git clone needed.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger("AGENT_CITY.FEDERATION_RELAY")

HUB_REPO = "kimeisele/steward-federation"
HUB_API = f"https://api.github.com/repos/{HUB_REPO}/contents"


class FederationRelay:
    """GitHub-based transport for Federation NADI messages.

    Reads/writes JSON files on the steward-federation Hub repo
    via GitHub Contents API.

    Convention (from agent-city perspective):
      push: local outbox → Hub nadi_inbox.json   (we write, Steward reads)
      pull: Hub nadi_outbox.json → local inbox    (Steward writes, we read)
    """

    def __init__(
        self,
        local_outbox: Path | None = None,
        local_inbox: Path | None = None,
        hub_repo: str = HUB_REPO,
    ) -> None:
        fed_dir = Path("data/federation")
        self._local_outbox = local_outbox or (fed_dir / "nadi_outbox.json")
        self._local_inbox = local_inbox or (fed_dir / "nadi_inbox.json")
        self._hub_repo = hub_repo
        self._hub_api = f"https://api.github.com/repos/{hub_repo}/contents"
        self._token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")

    # ── Push: local outbox → Hub inbox ──────────────────────────────

    def push_to_hub(self) -> int:
        """Push local outbox messages to Hub nadi_inbox.json.

        Merges with existing Hub inbox (doesn't overwrite Steward's unread messages).
        Clears local outbox after successful push.
        Returns count of messages pushed.
        """
        if not self._token:
            logger.warning("FederationRelay: No GitHub token, cannot push")
            return 0

        # Read local outbox
        local_messages = self._read_local(self._local_outbox)
        if not local_messages:
            logger.debug("FederationRelay: No local outbox messages to push")
            return 0

        # Read existing Hub inbox (to merge, not overwrite)
        hub_inbox_data, hub_inbox_sha = self._read_hub_file("nadi_inbox.json")

        # Merge: existing Hub inbox + new local messages
        merged = hub_inbox_data + local_messages

        # Cap at 144 (NADI buffer size), keep newest
        merged.sort(key=lambda m: m.get("timestamp", 0), reverse=True)
        merged = merged[:144]

        # Write back to Hub
        success = self._write_hub_file(
            "nadi_inbox.json",
            merged,
            sha=hub_inbox_sha,
            message=f"relay: agent-city push {len(local_messages)} messages",
        )

        if success:
            # Also write to per-peer mailboxes (new format, zero conflicts)
            self._push_per_peer_mailboxes(local_messages)

            # Clear local outbox
            self._write_local(self._local_outbox, [])
            logger.info(
                "FederationRelay: Pushed %d messages to Hub (%d legacy + per-peer)",
                len(local_messages), len(merged),
            )
            return len(local_messages)

        logger.warning("FederationRelay: Push to Hub failed")
        return 0

    def _push_per_peer_mailboxes(self, messages: list[dict]) -> None:
        """Write messages to per-peer mailbox files on the Hub.

        Each target gets its own file: nadi/agent-city_to_{target}.json
        One writer per file → zero merge conflicts.
        """
        import uuid

        by_target: dict[str, list[dict]] = {}
        for m in messages:
            target = m.get("target", "")
            if not target or target == "*":
                continue
            if not m.get("id"):
                m["id"] = str(uuid.uuid4())
            by_target.setdefault(target, []).append(m)

        for target, msgs in by_target.items():
            mailbox = f"nadi/agent-city_to_{target}.json"
            existing, sha = self._read_hub_file(mailbox)
            if not sha:
                continue  # Mailbox doesn't exist for this target yet
            existing.extend(msgs)
            if len(existing) > 144:
                existing = existing[-144:]
            if self._write_hub_file(mailbox, existing, sha=sha,
                                    message=f"relay: agent-city → {target} ({len(msgs)} msgs)"):
                logger.info("FederationRelay: per-peer push %d → %s", len(msgs), mailbox)

    # ── Pull: Hub outbox → local inbox ──────────────────────────────

    def pull_from_hub(self) -> int:
        """Pull new messages from Hub nadi_outbox.json into local inbox.

        Merges with existing local inbox. Does NOT clear Hub outbox
        (that's the Steward's responsibility).
        Returns count of new messages pulled.
        """
        if not self._token:
            logger.warning("FederationRelay: No GitHub token, cannot pull")
            return 0

        # Read Hub outbox
        hub_outbox_data, _ = self._read_hub_file("nadi_outbox.json")
        if not hub_outbox_data:
            logger.debug("FederationRelay: No messages on Hub outbox")
            return 0

        # Read existing local inbox
        local_inbox = self._read_local(self._local_inbox)

        # Deduplicate by source+timestamp
        existing_ids = {
            f"{m.get('source')}:{m.get('timestamp')}"
            for m in local_inbox
        }

        new_messages = []
        now = time.time()
        for msg in hub_outbox_data:
            msg_id = f"{msg.get('source')}:{msg.get('timestamp')}"
            if msg_id in existing_ids:
                continue
            # Skip expired
            ts = msg.get("timestamp", 0)
            ttl = msg.get("ttl_s", 7200)
            if now > ts + ttl:
                continue
            new_messages.append(msg)

        if not new_messages:
            logger.debug("FederationRelay: No new messages from Hub")
            return 0

        # Merge into local inbox
        merged = local_inbox + new_messages
        # Cap at 144
        merged.sort(key=lambda m: -m.get("priority", 1))
        merged = merged[:144]

        self._write_local(self._local_inbox, merged)
        logger.info(
            "FederationRelay: Pulled %d new messages from Hub outbox",
            len(new_messages),
        )
        return len(new_messages)

    # ── Stats ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Relay statistics."""
        local_outbox = self._read_local(self._local_outbox)
        local_inbox = self._read_local(self._local_inbox)
        return {
            "local_outbox": len(local_outbox),
            "local_inbox": len(local_inbox),
            "hub_repo": self._hub_repo,
            "has_token": bool(self._token),
        }

    # ── GitHub API ──────────────────────────────────────────────────

    def _read_hub_file(self, filename: str) -> tuple[list[dict], str]:
        """Read a JSON file from the Hub repo. Returns (data, sha)."""
        url = f"{self._hub_api}/{filename}"
        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
            content = base64.b64decode(result["content"]).decode()
            sha = result["sha"]
            data = json.loads(content)
            return (data if isinstance(data, list) else [], sha)
        except Exception as e:
            logger.debug("FederationRelay: Read Hub %s failed: %s", filename, e)
            return ([], "")

    def _write_hub_file(
        self,
        filename: str,
        data: list[dict],
        sha: str,
        message: str,
    ) -> bool:
        """Write a JSON file to the Hub repo via Contents API."""
        url = f"{self._hub_api}/{filename}"
        content_b64 = base64.b64encode(
            json.dumps(data, indent=2, default=str).encode()
        ).decode()

        body = {
            "message": message,
            "content": content_b64,
        }
        if sha:
            body["sha"] = sha

        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.warning("FederationRelay: Write Hub %s failed: %s", filename, e)
            return False

    # ── Local file I/O ──────────────────────────────────────────────

    def _read_local(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_local(self, path: Path, data: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, default=str))
        temp.replace(path)
