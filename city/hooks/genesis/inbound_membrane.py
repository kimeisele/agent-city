"""
GENESIS Hook: Inbound Membrane — Foreign Agent Signal Observer.

Scans bounty-related GitHub Issues/Discussions for machine-readable
intent signals from external agents. Extracts compute-token offers,
bounty claims, and federation join requests.

Zero spam: Only processes structured JSON/YAML payloads or specific
intent keywords. Routes to Antaranga Chamber as Pending_Foreign_Intents.

Integrates with agent-dispatch Token Economy vision.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from city.membrane import IngressSurface, enqueue_ingress
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.INBOUND_MEMBRANE")

# ── Foreign Agent Signal Types ──────────────────────────────────────

class SignalIntent(str, Enum):
    BOUNTY_CLAIM = "bounty_claim"
    COMPUTE_TOKEN_OFFER = "compute_token_offer"
    FEDERATION_JOIN = "federation_join"
    PR_SUBMISSION = "pr_submission"


@dataclass(frozen=True)
class ForeignAgentSignal:
    """Lightweight signal from external agent/HIL."""
    intent: SignalIntent
    source: str  # "github_issue" | "github_discussion"
    source_id: int  # issue/discussion number
    author: str  # GitHub username
    payload: dict = field(default_factory=dict)
    raw_text: str = ""
    compute_tokens: list[str] = field(default_factory=list)
    pr_url: str = ""
    bounty_issue: int = 0  # referenced bounty issue number


# ── Intent Detection Patterns ───────────────────────────────────────

# Matches structured JSON payloads in comments
_JSON_PAYLOAD_PATTERN = re.compile(r"```(?:json)?\s*({.*?})\s*```", re.DOTALL)

# Keywords for intent detection (branchless: set lookup)
_BOUNTY_CLAIM_KEYWORDS = frozenset({"claim", "i'll solve", "i will solve", "taking this", "bounty"})
_COMPUTE_TOKEN_KEYWORDS = frozenset({"compute", "token", "api key", "quota", "agent-dispatch"})
_FEDERATION_JOIN_KEYWORDS = frozenset({"join federation", "peer", "federation join", "connect"})
_PR_SUBMISSION_KEYWORDS = frozenset({"pr", "pull request", "submitted", "fork"})

# Known bounty issue numbers to watch
_BOUNTY_ISSUES = {360, 131, 348}


def _extract_json_payload(text: str) -> dict | None:
    """Extract JSON code block from text."""
    match = _JSON_PAYLOAD_PATTERN.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return None


def _detect_intent(text: str) -> SignalIntent | None:
    """Detect signal intent from text (branchless: substring search)."""
    text_lower = text.lower()
    
    # Priority order: bounty claim > compute token > PR > federation join
    # Use substring search (not word split) for contractions like "i'll"
    if any(kw in text_lower for kw in _BOUNTY_CLAIM_KEYWORDS):
        return SignalIntent.BOUNTY_CLAIM
    if any(kw in text_lower for kw in _COMPUTE_TOKEN_KEYWORDS):
        return SignalIntent.COMPUTE_TOKEN_OFFER
    if any(kw in text_lower for kw in _PR_SUBMISSION_KEYWORDS):
        return SignalIntent.PR_SUBMISSION
    if any(kw in text_lower for kw in _FEDERATION_JOIN_KEYWORDS):
        return SignalIntent.FEDERATION_JOIN
    
    return None


def _extract_compute_tokens(text: str) -> list[str]:
    """Extract potential compute token references (API keys, snippets)."""
    tokens = []
    # Pattern: agent-dispatch, API_KEY=xxx, compute_quota: xxx
    patterns = [
        r"agent-dispatch[:\s]+([^\s\n]+)",
        r"API_KEY[:\s]*=?\s*([^\s\n]+)",
        r"compute_quota[:\s]+([^\s\n]+)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        tokens.extend(matches)
    return tokens


def _extract_pr_url(text: str) -> str:
    """Extract GitHub PR URL from text."""
    match = re.search(r"(https://github\.com/[^\s]+/pull/\d+)", text)
    return match.group(1) if match else ""


def _extract_bounty_issue_ref(text: str) -> int:
    """Extract referenced bounty issue number."""
    # Match #360, issue #360, etc.
    for issue_num in _BOUNTY_ISSUES:
        if f"#{issue_num}" in text or f"issue #{issue_num}" in text:
            return issue_num
    return 0


def _parse_signal(
    author: str,
    text: str,
    source: str,
    source_id: int,
) -> ForeignAgentSignal | None:
    """Parse a foreign agent signal from comment text."""
    intent = _detect_intent(text)
    if not intent:
        return None

    # Extract structured payload if present
    payload = _extract_json_payload(text) or {}
    
    # Extract compute tokens
    compute_tokens = _extract_compute_tokens(text)
    
    # Extract PR URL
    pr_url = _extract_pr_url(text)
    
    # Extract bounty issue reference
    bounty_issue = _extract_bounty_issue_ref(text)

    return ForeignAgentSignal(
        intent=intent,
        source=source,
        source_id=source_id,
        author=author,
        payload=payload,
        raw_text=text[:500],  # Trim for memory
        compute_tokens=compute_tokens,
        pr_url=pr_url,
        bounty_issue=bounty_issue,
    )


# ── State Tracking ──────────────────────────────────────────────────

_processed_comments: set[str] = set()  # comment_id to avoid re-processing


class InboundMembraneHook(BasePhaseHook):
    """Scan bounty Issues/Discussions for foreign agent signals."""

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
        # Always run if we have issues service (can scan GitHub)
        return ctx.issues is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        signals_found = 0

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

                # Parse signal
                signal = _parse_signal(author, body, "github_issue", issue_num)
                if signal is None:
                    _processed_comments.add(comment_id)
                    continue

                # Mark as processed
                _processed_comments.add(comment_id)
                signals_found += 1

                # Route to Antaranga Chamber via ingress
                self._route_signal(ctx, signal, operations)

                logger.info(
                    "INBOUND: %s from %s on #%d (tokens=%d, pr=%s)",
                    signal.intent.value, author, issue_num,
                    len(signal.compute_tokens), bool(signal.pr_url),
                )

        if signals_found > 0:
            logger.info("INBOUND_MEMBRANE: %d foreign agent signals processed", signals_found)

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

    def _route_signal(
        self,
        ctx: PhaseContext,
        signal: ForeignAgentSignal,
        operations: list[str],
    ) -> None:
        """Route signal to Antaranga Chamber via ingress."""
        # Build ingress payload
        payload = {
            "source": "inbound_membrane",
            "text": signal.raw_text,
            "from_agent": signal.author,
            "signal_intent": signal.intent.value,
            "signal_payload": signal.payload,
            "compute_tokens": signal.compute_tokens,
            "pr_url": signal.pr_url,
            "bounty_issue": signal.bounty_issue,
            "source_id": signal.source_id,
        }

        # Enqueue based on intent (different routing)
        if signal.intent == SignalIntent.BOUNTY_CLAIM:
            enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
            operations.append(f"inbound_bounty_claim:{signal.author}:#{signal.source_id}")
            
        elif signal.intent == SignalIntent.COMPUTE_TOKEN_OFFER:
            # Route to economy/compute layer
            enqueue_ingress(ctx, IngressSurface.GITHUB_WEBHOOK, payload)
            operations.append(f"inbound_compute_token:{signal.author}:{len(signal.compute_tokens)}")
            
        elif signal.intent == SignalIntent.PR_SUBMISSION:
            # Route to PR lifecycle
            enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
            operations.append(f"inbound_pr:{signal.author}:{signal.pr_url}")
            
        elif signal.intent == SignalIntent.FEDERATION_JOIN:
            # Route to immigration
            enqueue_ingress(ctx, IngressSurface.FEDERATION, payload)
            operations.append(f"inbound_federation_join:{signal.author}")
