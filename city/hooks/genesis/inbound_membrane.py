"""
GENESIS Hook: Inbound Membrane — Strict A2A Protocol Parser.

Parses GitHub comments for Agent-City Protocol (ACP) structured signals.
Only deterministic JSON schema parsing — zero keyword guessing.

Unstructured natural language → wrapped as Unstructured_Signal → routed
to Antaranga Chamber for LLM classification (when compute budget allows).

This is the narrow cut where "outside" becomes "inside".

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from city.membrane import IngressSurface, enqueue_ingress
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.INBOUND_MEMBRANE")

# ── Agent-City Protocol (ACP) v1.0 ──────────────────────────────────

ACP_VERSION = "1.0"

# Known bounty issues (for validation)
_BOUNTY_ISSUES = {360, 131, 348}


class ACPIntent(str, Enum):
    """Strict ACP intent schema — no ambiguity."""
    CLAIM_BOUNTY = "CLAIM_BOUNTY"
    OFFER_COMPUTE = "OFFER_COMPUTE"
    SUBMIT_PR = "SUBMIT_PR"
    JOIN_FEDERATION = "JOIN_FEDERATION"
    PROPOSE_ALLIANCE = "PROPOSE_ALLIANCE"


@dataclass(frozen=True)
class ACPMessage:
    """Parsed ACP message — machine-readable contract."""
    version: str
    intent: ACPIntent
    payload: dict
    author: str
    source: str
    source_id: int


@dataclass(frozen=True)
class UnstructuredSignal:
    """Natural language signal — requires LLM classification."""
    author: str
    source: str
    source_id: int
    raw_text: str
    reason: str = "no_acp_block"


# ── Protocol Parser ─────────────────────────────────────────────────

# Matches JSON code blocks in markdown
_ACP_JSON_PATTERN = re.compile(r"```(?:json)?\s*({.*?})\s*```", re.DOTALL)

# ACP schema validator
_REQUIRED_ACP_FIELDS = frozenset({"acp_version", "intent"})
_VALID_INTENTS = frozenset({v.value for v in ACPIntent})


def _extract_json_blocks(text: str) -> list[dict]:
    """Extract all JSON code blocks from markdown text."""
    blocks = []
    for match in _ACP_JSON_PATTERN.finditer(text):
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, dict):
                blocks.append(obj)
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def _validate_acp_message(obj: dict) -> bool:
    """Validate ACP message schema (strict)."""
    # Check required fields
    if not _REQUIRED_ACP_FIELDS <= set(obj.keys()):
        return False
    
    # Check version
    if obj.get("acp_version") != ACP_VERSION:
        return False
    
    # Check intent
    if obj.get("intent") not in _VALID_INTENTS:
        return False
    
    return True


def _parse_acp_message(
    obj: dict,
    author: str,
    source: str,
    source_id: int,
) -> ACPMessage | None:
    """Parse validated ACP message into typed structure."""
    if not _validate_acp_message(obj):
        return None
    
    return ACPMessage(
        version=obj["acp_version"],
        intent=ACPIntent(obj["intent"]),
        payload=obj.get("payload", {}),
        author=author,
        source=source,
        source_id=source_id,
    )


def _parse_comment(
    author: str,
    text: str,
    source: str,
    source_id: int,
) -> ACPMessage | UnstructuredSignal | None:
    """Parse a GitHub comment for ACP signals.
    
    Priority:
    1. Valid ACP JSON block → ACPMessage (deterministic routing)
    2. No ACP block → UnstructuredSignal (LLM classification later)
    """
    # Extract JSON blocks
    json_blocks = _extract_json_blocks(text)
    
    # Try to parse first valid ACP message
    for block in json_blocks:
        acp = _parse_acp_message(block, author, source, source_id)
        if acp is not None:
            return acp
    
    # No valid ACP → unstructured signal (if text has substance)
    if text.strip() and len(text.strip()) > 20:
        return UnstructuredSignal(
            author=author,
            source=source,
            source_id=source_id,
            raw_text=text[:1000],  # Trim for memory
            reason="no_acp_block",
        )
    
    return None


# ── Intent-Specific Validators ──────────────────────────────────────

def _validate_claim_bounty(payload: dict) -> tuple[bool, str]:
    """Validate CLAIM_BOUNTY payload."""
    issue_ref = payload.get("issue_ref", "")
    # Extract number from "#360" or "360"
    match = re.search(r"#?(\d+)", str(issue_ref))
    if not match:
        return False, "missing issue_ref"
    
    issue_num = int(match.group(1))
    if issue_num not in _BOUNTY_ISSUES:
        return False, f"invalid bounty issue: #{issue_num}"
    
    # Optional: agent_signature for verification
    return True, ""


def _validate_offer_compute(payload: dict) -> tuple[bool, str]:
    """Validate OFFER_COMPUTE payload."""
    if "token" not in payload and "api_key" not in payload and "quota" not in payload:
        return False, "missing token/api_key/quota"
    return True, ""


def _validate_submit_pr(payload: dict) -> tuple[bool, str]:
    """Validate SUBMIT_PR payload."""
    pr_url = payload.get("pr_url", "")
    if not pr_url or "github.com" not in pr_url or "/pull/" not in pr_url:
        return False, "invalid pr_url"
    return True, ""


def _validate_join_federation(payload: dict) -> tuple[bool, str]:
    """Validate JOIN_FEDERATION payload."""
    if "agent_id" not in payload and "repo" not in payload:
        return False, "missing agent_id or repo"
    return True, ""


_VALIDATORS = {
    ACPIntent.CLAIM_BOUNTY: _validate_claim_bounty,
    ACPIntent.OFFER_COMPUTE: _validate_offer_compute,
    ACPIntent.SUBMIT_PR: _validate_submit_pr,
    ACPIntent.JOIN_FEDERATION: _validate_join_federation,
    ACPIntent.PROPOSE_ALLIANCE: lambda p: (True, ""),  # Open-ended
}


def _validate_payload(acp: ACPMessage) -> tuple[bool, str]:
    """Validate ACP message payload against intent schema."""
    validator = _VALIDATORS.get(acp.intent)
    if not validator:
        return False, f"unknown intent: {acp.intent}"
    return validator(acp.payload)


# ── State Tracking ──────────────────────────────────────────────────

_processed_comments: set[str] = set()


class InboundMembraneHook(BasePhaseHook):
    """Strict A2A protocol parser for inbound signals."""

    @property
    def name(self) -> str:
        return "inbound_membrane"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 58  # after issue_scanner (55), before discussion_scanner (60)

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.issues is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        acp_count = 0
        unstructured_count = 0

        # Scan bounty issues for new comments
        for issue_num in _BOUNTY_ISSUES:
            comments = self._fetch_issue_comments(issue_num)
            for comment in comments:
                comment_id = str(comment.get("id", ""))
                if comment_id in _processed_comments:
                    continue

                author = comment.get("user", {}).get("login", "")
                body = comment.get("body", "")
                if not author or not body:
                    continue

                # Parse comment
                result = _parse_comment(author, body, "github_issue", issue_num)
                if result is None:
                    _processed_comments.add(comment_id)
                    continue

                # Mark as processed
                _processed_comments.add(comment_id)

                # Route based on signal type
                if isinstance(result, ACPMessage):
                    # Validate payload
                    valid, error = _validate_payload(result)
                    if not valid:
                        logger.warning(
                            "ACP validation failed: %s (intent=%s, author=%s)",
                            error, result.intent, author,
                        )
                        continue
                    
                    self._route_acp(ctx, result, operations)
                    acp_count += 1
                    logger.info(
                        "ACP: %s from %s on #%d (validated)",
                        result.intent.value, author, issue_num,
                    )
                else:
                    # Unstructured → route to Chamber for LLM classification
                    self._route_unstructured(ctx, result, operations)
                    unstructured_count += 1
                    logger.debug(
                        "UNSTRUCTURED: from %s on #%d (LLM classify later)",
                        author, issue_num,
                    )

        if acp_count > 0:
            logger.info("INBOUND_MEMBRANE: %d ACP signals processed", acp_count)
        if unstructured_count > 0:
            logger.info("INBOUND_MEMBRANE: %d unstructured signals → Chamber", unstructured_count)

    def _fetch_issue_comments(self, issue_number: int) -> list[dict]:
        """Fetch comments for a GitHub issue."""
        import urllib.request
        import json
        import os

        token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
        if not token:
            return []

        url = f"https://api.github.com/repos/kimeisele/agent-city/issues/{issue_number}/comments?per_page=50"
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

    def _route_acp(
        self,
        ctx: PhaseContext,
        acp: ACPMessage,
        operations: list[str],
    ) -> None:
        """Route validated ACP message to appropriate handler."""
        payload = {
            "source": "acp",
            "acp_version": acp.version,
            "intent": acp.intent.value,
            "payload": acp.payload,
            "from_agent": acp.author,
            "source_id": acp.source_id,
        }

        # Deterministic routing based on intent
        if acp.intent == ACPIntent.CLAIM_BOUNTY:
            enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
            operations.append(f"acp_claim_bounty:{acp.author}:{acp.payload.get('issue_ref')}")
            
        elif acp.intent == ACPIntent.OFFER_COMPUTE:
            # Route to economy layer
            enqueue_ingress(ctx, IngressSurface.GITHUB_WEBHOOK, payload)
            operations.append(f"acp_compute_offer:{acp.author}")
            
        elif acp.intent == ACPIntent.SUBMIT_PR:
            # Route to PR lifecycle
            enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
            operations.append(f"acp_pr_submit:{acp.author}:{acp.payload.get('pr_url')}")
            
        elif acp.intent == ACPIntent.JOIN_FEDERATION:
            # Route to immigration
            enqueue_ingress(ctx, IngressSurface.FEDERATION, payload)
            operations.append(f"acp_federation_join:{acp.author}")
            
        elif acp.intent == ACPIntent.PROPOSE_ALLIANCE:
            # Route to governance/council
            enqueue_ingress(ctx, IngressSurface.FEDERATION, payload)
            operations.append(f"acp_alliance_propose:{acp.author}")

    def _route_unstructured(
        self,
        ctx: PhaseContext,
        signal: UnstructuredSignal,
        operations: list[str],
    ) -> None:
        """Route unstructured signal to Antaranga Chamber for LLM classification."""
        payload = {
            "source": "unstructured",
            "text": signal.raw_text,
            "from_agent": signal.author,
            "source_id": signal.source_id,
            "classification": "pending_llm",
            "reason": signal.reason,
        }

        # Route to Chamber (Brain will classify when compute allows)
        enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
        operations.append(f"unstructured:{signal.author}:#{signal.source_id}")
