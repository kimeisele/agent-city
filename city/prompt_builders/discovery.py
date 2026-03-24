"""
DISCOVERY BUILDER — Evaluate Federation Fit.
==============================================

Step 3: Semantic Peer Discovery.
Asks the Brain to evaluate if a repository is a viable federation candidate
based on its README and description.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.prompt_registry import PromptContext


class FederationFit(StrEnum):
    """Classification of a repository's fit for the federation."""

    FIT = "FIT"
    REJECTED = "REJECTED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class DiscoveryBuilder:
    """Builder for discovery thought kind."""

    @property
    def kind(self) -> str:
        return "discovery"

    def build_payload(self, ctx: PromptContext) -> list[str]:
        """Build payload from discovery data."""
        return [
            f"REPOSITORY: {ctx.discovery_repo}",
            f"DESCRIPTION: {ctx.discovery_description}",
            "",
            "README SNIPPET (TRUNCATED):",
            ctx.discovery_readme or "(No README content available)",
        ]

    def build_schema(self) -> str:
        """Instruction for LLM on how to evaluate fit."""
        return (
            "Classify the repository into a strict Enum: FIT, REJECTED, or NEEDS_HUMAN_REVIEW. "
            "Set 'action_hint' to 'invite' if FIT, 'reject' if REJECTED, 'review' if NEEDS_HUMAN_REVIEW. "
            "Look for autonomous agent architecture, API-first design, multi-agent protocol mentions, "
            "or active A2A (Agent-to-Agent) development. "
            "Standard web applications, general-purpose libraries without agentic focus, tutorials, "
            "and simple forks MUST be REJECTED."
        )

    def build_user_message(self, ctx: PromptContext) -> str:
        """User message for the discovery evaluation."""
        return (
            f"Evaluate the federation fit for repository '{ctx.discovery_repo}'. "
            "Provide your reasoning in the 'comprehension' field and set the 'intent' to 'observe'."
        )
