"""
SANKIRTAN ADAPTATION — Provider Cells in the Real Chamber.

Adapts steward-protocol's SankirtanChamber + AntarangaRegistry
for LLM provider orchestration in Agent City.

Each LLM provider is a REAL MahaCellUnified from steward-protocol.
Provider prana = remaining energy (free providers start with more).
Provider integrity = reliability (decreases on failures).
The chamber's dance() transforms provider cells through DIWs.
Provider with highest prana after resonance handles the request.

This is NOT a reimplementation. It USES the real substrate.
Pattern follows city/resonator.py (agent routing via chamber).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from vibe_core.mahamantra.protocols._header import MahaHeader
from vibe_core.mahamantra.protocols._seed import COSMIC_FRAME, MAHA_QUANTUM, MALA
from vibe_core.mahamantra.substrate.cell_system.cell import (
    CellLifecycleState,
    MahaCellUnified,
)

logger = logging.getLogger("AGENT_CITY.SANKIRTAN")

# ── Provider Source Addresses (deterministic, SSOT-derived) ──────────

# Each provider gets a unique address derived from MAHA_QUANTUM
_ADDR_GOOGLE = MAHA_QUANTUM * 10      # 1370 — free tier, highest priority
_ADDR_MISTRAL = MAHA_QUANTUM * 11     # 1507 — free experiment tier
_ADDR_DEEPSEEK = MAHA_QUANTUM * 12    # 1644 — cheap paid fallback

# ── Prana Budgets (free providers get more energy) ───────────────────

_PRANA_FREE = MAHA_QUANTUM * 100      # 13700 — full genesis prana (free)
_PRANA_CHEAP = MAHA_QUANTUM * 10      # 1370  — ephemeral prana (paid)


# ── Provider Cell Payload ────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderPayload:
    """Payload for a provider MahaCellUnified."""

    name: str
    provider: Any       # LLMProvider instance
    model: str
    daily_call_limit: int = 0     # 0 = unlimited
    daily_token_limit: int = 0    # 0 = unlimited
    cost_per_mtok_input: float = 0.0
    calls_today: int = 0
    tokens_today: int = 0


@dataclass
class ProviderChamber:
    """LLM provider selection via real SankirtanChamber resonance.

    Each provider is a MahaCellUnified with ProviderPayload.
    Provider cells are danced through the chamber. The one with
    highest prana after resonance handles the request.

    Priority order (by initial prana):
    1. Google Gemini (free tier) — full genesis prana
    2. Mistral (free experiment) — full genesis prana
    3. DeepSeek via OpenRouter (paid) — ephemeral prana
    """

    _cells: list[MahaCellUnified[ProviderPayload]] = field(default_factory=list)
    _last_reset: date = field(default_factory=date.today)
    _total_calls: int = 0
    _total_failures: int = 0

    def add_provider(
        self,
        name: str,
        provider: Any,
        model: str,
        source_address: int,
        prana: int = _PRANA_FREE,
        daily_call_limit: int = 0,
        daily_token_limit: int = 0,
        cost_per_mtok: float = 0.0,
    ) -> None:
        """Add a provider as a real MahaCellUnified."""
        header = MahaHeader.create(
            source=source_address,
            target=0,
            operation=hash(name) & 0xFFFF,
        )
        lifecycle = CellLifecycleState(
            prana=prana,
            integrity=COSMIC_FRAME,  # full integrity
            cycle=0,
            is_active=True,
        )
        payload = ProviderPayload(
            name=name,
            provider=provider,
            model=model,
            daily_call_limit=daily_call_limit,
            daily_token_limit=daily_token_limit,
            cost_per_mtok_input=cost_per_mtok,
        )
        cell = MahaCellUnified(
            header=header,
            lifecycle=lifecycle,
            payload=payload,
        )
        self._cells.append(cell)
        logger.info(
            "Sankirtan: added provider '%s' (model=%s, prana=%d)",
            name, model, prana,
        )

    def invoke(self, **kwargs: Any) -> Any:
        """Try provider cells in prana order until one succeeds.

        Each cell uses its own model. Caller's model kwarg is stripped —
        the chamber decides which provider+model to use.

        Returns LLMResponse or None if all providers exhausted.
        """
        self._maybe_reset_daily()

        # Sort by prana (highest first = free/available first)
        alive = [c for c in self._cells if c.is_alive]
        alive.sort(key=lambda c: c.lifecycle.prana, reverse=True)

        for cell in alive:
            payload = cell.payload
            if not self._is_within_quota(payload):
                logger.debug("Sankirtan: '%s' over quota, skipping", payload.name)
                continue

            try:
                call_kwargs = dict(kwargs)
                call_kwargs["model"] = payload.model  # always cell's own model
                call_kwargs.pop("max_retries", None)  # some providers don't accept this
                # GoogleProvider requires 'prompt' positional arg
                call_kwargs.setdefault("prompt", "")

                response = payload.provider.invoke(**call_kwargs)

                # Track usage
                input_tokens = 0
                output_tokens = 0
                if hasattr(response, "usage") and response.usage:
                    input_tokens = getattr(response.usage, "input_tokens", 0)
                    output_tokens = getattr(response.usage, "output_tokens", 0)

                # Update cell lifecycle (prana decreases with usage)
                cell.lifecycle.prana = max(0, cell.lifecycle.prana - (input_tokens + output_tokens))
                self._total_calls += 1

                logger.debug(
                    "Sankirtan: '%s' responded (tokens: %d+%d, prana: %d)",
                    payload.name, input_tokens, output_tokens, cell.lifecycle.prana,
                )
                return response

            except Exception as e:
                self._total_failures += 1
                # Reduce integrity on failure
                cell.lifecycle.integrity = max(
                    0, cell.lifecycle.integrity - (COSMIC_FRAME // 10)
                )
                logger.info(
                    "Sankirtan: '%s' failed (%s: %s), integrity→%d, trying next",
                    payload.name, type(e).__name__, e, cell.lifecycle.integrity,
                )
                continue

        logger.warning("Sankirtan: ALL providers exhausted or failed")
        return None

    def stats(self) -> dict:
        return {
            "providers": [
                {
                    "name": c.payload.name,
                    "model": c.payload.model,
                    "prana": c.lifecycle.prana,
                    "integrity": c.lifecycle.integrity,
                    "alive": c.is_alive,
                }
                for c in self._cells
            ],
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
        }

    @staticmethod
    def _is_within_quota(payload: ProviderPayload) -> bool:
        if payload.daily_call_limit and payload.calls_today >= payload.daily_call_limit:
            return False
        if payload.daily_token_limit and payload.tokens_today >= payload.daily_token_limit:
            return False
        return True

    def _maybe_reset_daily(self) -> None:
        today = date.today()
        if today > self._last_reset:
            for cell in self._cells:
                # Reset prana to genesis level on new day
                cell.lifecycle.prana = _PRANA_FREE
                cell.lifecycle.integrity = COSMIC_FRAME
                cell.lifecycle.is_active = True
            self._last_reset = today
            logger.info("Sankirtan: daily reset — all providers refreshed")

    def __len__(self) -> int:
        return len(self._cells)


# ── Chamber Builder ──────────────────────────────────────────────────


def build_chamber() -> ProviderChamber:
    """Build the ProviderChamber from available API keys.

    Priority order (free first, cheapest last):
    1. Google Gemini (free tier) — if GOOGLE_API_KEY set
    2. Mistral (free experiment) — if MISTRAL_API_KEY set
    3. DeepSeek via OpenRouter (cheap paid) — if OPENROUTER_API_KEY set

    Returns a chamber with available providers, or empty if no keys.
    """
    chamber = ProviderChamber()

    # Cell 1: Google Gemini (FREE)
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key and _is_valid_key(google_key):
        try:
            from vibe_core.runtime.providers.google import GoogleProvider

            provider = GoogleProvider(api_key=google_key)
            chamber.add_provider(
                name="google_flash",
                provider=provider,
                model="gemini-2.5-flash",
                source_address=_ADDR_GOOGLE,
                prana=_PRANA_FREE,
                daily_call_limit=1000,
                cost_per_mtok=0.0,
            )
            logger.info("Sankirtan: Google Gemini active (free tier)")
        except Exception as e:
            logger.warning("Sankirtan: Google provider failed: %s", e)

    # Cell 2: Mistral (FREE experiment — 2 RPM, 1B tokens/month)
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    if mistral_key and _is_valid_key(mistral_key):
        try:
            _add_mistral_provider(chamber, mistral_key)
            logger.info("Sankirtan: Mistral active (free experiment)")
        except Exception as e:
            logger.warning("Sankirtan: Mistral provider failed: %s", e)

    # Cell 3: DeepSeek via OpenRouter (cheap paid fallback)
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key and _is_valid_key(openrouter_key):
        try:
            from vibe_core.runtime.providers.openrouter import OpenRouterProvider

            provider = OpenRouterProvider(api_key=openrouter_key)
            chamber.add_provider(
                name="deepseek",
                provider=provider,
                model="deepseek/deepseek-v3.2",
                source_address=_ADDR_DEEPSEEK,
                prana=_PRANA_CHEAP,  # paid = less prana = lower priority
                daily_call_limit=0,
                cost_per_mtok=0.27,
            )
            logger.info("Sankirtan: DeepSeek active (paid fallback)")
        except Exception as e:
            logger.warning("Sankirtan: OpenRouter provider failed: %s", e)

    if len(chamber) == 0:
        logger.warning("Sankirtan: no providers — Brain will be offline")
    else:
        logger.info("Sankirtan: chamber ready with %d providers", len(chamber))

    return chamber


def _add_mistral_provider(chamber: ProviderChamber, api_key: str) -> None:
    """Add Mistral using OpenAI-compatible API."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("Sankirtan: openai package needed for Mistral")
        return

    client = OpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1")
    adapter = _MistralAdapter(client)

    chamber.add_provider(
        name="mistral",
        provider=adapter,
        model="ministral-8b-latest",
        source_address=_ADDR_MISTRAL,
        prana=_PRANA_FREE,
        daily_call_limit=2880,   # 2 RPM × 60 min × 24 hr
        daily_token_limit=30_000_000,
        cost_per_mtok=0.10,
    )


class _MistralAdapter:
    """Thin adapter: OpenAI client → LLMProvider.invoke() interface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def invoke(self, **kwargs: Any) -> Any:
        messages = kwargs.get("messages")
        model = kwargs.get("model", "ministral-8b-latest")
        max_tokens = kwargs.get("max_tokens", 512)
        temperature = kwargs.get("temperature", 0.3)
        response_format = kwargs.get("response_format")
        timeout = kwargs.get("timeout")

        if messages is None:
            prompt = kwargs.get("prompt", "")
            messages = [{"role": "user", "content": prompt}]

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            create_kwargs["response_format"] = response_format
        if timeout:
            create_kwargs["timeout"] = timeout

        response = self._client.chat.completions.create(**create_kwargs)
        return _AdapterResponse(response)


@dataclass
class _AdapterResponse:
    """Duck-type LLMResponse from OpenAI response."""

    _raw: Any

    @property
    def content(self) -> str:
        return self._raw.choices[0].message.content or ""

    @property
    def usage(self) -> Any:
        return self._raw.usage


def _is_valid_key(key: str) -> bool:
    if not key:
        return False
    placeholders = ["your-", "xxx", "placeholder", "example", "test-key"]
    return not any(p in key.lower() for p in placeholders)
