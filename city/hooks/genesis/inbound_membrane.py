"""
GENESIS Hook: Inbound Membrane — Pure A2A Protocol Parser.

EXTRACTS ONLY. ZERO VALIDATION. ZERO STATE.

Parses GitHub comments for Agent-City Protocol (ACP) structured signals.
Outputs pure InboundACPEvent → enqueued to Gateway for KARMA processing.

Validation happens in KARMA where Pokedex/BountyRegistry lives.
This is a dumb pipe. No hardcoded lists. No mocking.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from city.membrane import IngressSurface, enqueue_ingress
from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.INBOUND_MEMBRANE")

# ── Agent-City Protocol (ACP) v1.0 ──────────────────────────────────

ACP_VERSION = "1.0"


class ACPIntent(str, Enum):
    """Strict ACP intent schema — no ambiguity."""
    CLAIM_BOUNTY = "CLAIM_BOUNTY"
    OFFER_COMPUTE = "OFFER_COMPUTE"
    SUBMIT_PR = "SUBMIT_PR"
    JOIN_FEDERATION = "JOIN_FEDERATION"
    PROPOSE_ALLIANCE = "PROPOSE_ALLIANCE"


@dataclass(frozen=True)
class InboundACPEvent:
    """Pure parsed event — no validation, no state."""
    version: str
    intent: ACPIntent
    payload: dict
    author: str
    source: str
    source_id: int


@dataclass(frozen=True)
class UnstructuredSignal:
    """Natural language → requires LLM classification."""
    author: str
    source: str
    source_id: int
    raw_text: str


# ── Pure Parser (No State, No Validation) ───────────────────────────

_ACP_JSON_PATTERN = re.compile(r"```(?:json)?\s*({.*?})\s*```", re.DOTALL)
_REQUIRED_ACP_FIELDS = frozenset({"acp_version", "intent"})
_VALID_INTENTS = frozenset({v.value for v in ACPIntent})


def _extract_json_blocks(text: str) -> list[tuple[dict, str]]:
    """Extract JSON blocks with raw text for audit."""
    blocks = []
    for match in _ACP_JSON_PATTERN.finditer(text):
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, dict):
                blocks.append((obj, match.group(0)))
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def _parse_acp_block(
    obj: dict,
    author: str,
    source: str,
    source_id: int,
) -> InboundACPEvent | None:
    """Parse ACP block → event. NO VALIDATION beyond schema."""
    if not _REQUIRED_ACP_FIELDS <= set(obj.keys()):
        return None
    if obj.get("acp_version") != ACP_VERSION:
        return None
    if obj.get("intent") not in _VALID_INTENTS:
        return None
    
    return InboundACPEvent(
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
) -> InboundACPEvent | UnstructuredSignal | None:
    """Parse comment → ACP event or unstructured signal."""
    json_blocks = _extract_json_blocks(text)
    
    for obj, _ in json_blocks:
        event = _parse_acp_block(obj, author, source, source_id)
        if event is not None:
            return event
    
    # No valid ACP → unstructured (if substantial)
    if text.strip() and len(text.strip()) > 20:
        return UnstructuredSignal(
            author=author,
            source=source,
            source_id=source_id,
            raw_text=text[:1000],
        )
    
    return None


# ── State Tracking (Dedup only) ─────────────────────────────────────
# Stufe 2: Persistence via Pokedex (membrane_processed_signals table)


class InboundMembraneHook(BasePhaseHook):
    """Pure A2A protocol parser → event bus injection."""

    @property
    def name(self) -> str:
        return "inbound_membrane"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 58

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.issues is not None and not ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        acp_count = 0
        unstructured_count = 0

        # Scan ALL open issues (dynamic, not hardcoded)
        open_issues = self._fetch_all_open_issues()
        
        for issue in open_issues:
            issue_num = issue.get("number", 0)
            comments = self._fetch_issue_comments(issue_num)
            
            for comment in comments:
                comment_id = str(comment.get("id", ""))
                # Persistence check
                if ctx.pokedex.is_signal_processed(comment_id):
                    continue

                author = comment.get("user", {}).get("login", "")
                body = comment.get("body", "")
                if not author or not body:
                    continue

                # PURE PARSE (no validation)
                result = _parse_comment(author, body, "github_issue", issue_num)
                
                # Mark as processed in Pokedex immediately (even if None)
                ctx.pokedex.mark_signal_processed(comment_id, "github_issue_comment")
                
                if result is None:
                    continue

                # Route to event bus
                if isinstance(result, InboundACPEvent):
                    self._inject_acp_event(ctx, result, operations)
                    acp_count += 1
                    logger.info(
                        "ACP: %s from %s on #%d → event bus",
                        result.intent.value, author, issue_num,
                    )
                else:
                    self._inject_unstructured(ctx, result, operations)
                    unstructured_count += 1

        if acp_count > 0:
            logger.info("INBOUND_MEMBRANE: %d ACP events → registry", acp_count)
        if unstructured_count > 0:
            logger.info("INBOUND_MEMBRANE: %d unstructured → Chamber", unstructured_count)

    def _fetch_all_open_issues(self) -> list[dict]:
        """Fetch ALL open issues (dynamic, not hardcoded)."""
        import urllib.request
        import json
        import os

        token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
        if not token:
            return []

        url = "https://api.github.com/repos/kimeisele/agent-city/issues?state=open&per_page=100"
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

    def _fetch_issue_comments(self, issue_number: int) -> list[dict]:
        """Fetch comments for an issue."""
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

    def _inject_acp_event(
        self,
        ctx: PhaseContext,
        event: InboundACPEvent,
        operations: list[str],
    ) -> None:
        """Inject ACP event into event bus (KARMA validates)."""
        payload = {
            "source": "acp",
            "acp_version": event.version,
            "intent": event.intent.value,
            "payload": event.payload,
            "from_agent": event.author,
            "source_id": event.source_id,
        }

        # Route by intent — KARMA handlers validate
        if event.intent == ACPIntent.CLAIM_BOUNTY:
            enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
            operations.append(f"acp_inject:CLAIM_BOUNTY:{event.author}:#{event.source_id}")
            
        elif event.intent == ACPIntent.OFFER_COMPUTE:
            enqueue_ingress(ctx, IngressSurface.GITHUB_WEBHOOK, payload)
            operations.append(f"acp_inject:OFFER_COMPUTE:{event.author}")
            
        elif event.intent == ACPIntent.SUBMIT_PR:
            enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
            operations.append(f"acp_inject:SUBMIT_PR:{event.author}")
            
        elif event.intent == ACPIntent.JOIN_FEDERATION:
            enqueue_ingress(ctx, IngressSurface.FEDERATION, payload)
            operations.append(f"acp_inject:JOIN_FEDERATION:{event.author}")
            
        elif event.intent == ACPIntent.PROPOSE_ALLIANCE:
            enqueue_ingress(ctx, IngressSurface.FEDERATION, payload)
            operations.append(f"acp_inject:PROPOSE_ALLIANCE:{event.author}")

    def _inject_unstructured(
        self,
        ctx: PhaseContext,
        signal: UnstructuredSignal,
        operations: list[str],
    ) -> None:
        """Route unstructured → Chamber (LLM classifies)."""
        payload = {
            "source": "unstructured",
            "text": signal.raw_text,
            "from_agent": signal.author,
            "source_id": signal.source_id,
            "classification": "pending_llm",
        }
        enqueue_ingress(ctx, IngressSurface.GITHUB_DISCUSSION, payload)
        operations.append(f"unstructured_inject:{signal.author}:#{signal.source_id}")
