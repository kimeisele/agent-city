"""Explicit, reviewable producer trust configuration for live S3B adapters."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .evidence import AllowlistEvidenceProducerTrust


class TrustConfigError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TrustedProducerConfig:
    entries: frozenset[tuple[str, str, str, str]]

    def policy(self) -> AllowlistEvidenceProducerTrust:
        return AllowlistEvidenceProducerTrust(set(self.entries))


def load_trusted_producers(value: str | None = None) -> TrustedProducerConfig:
    """Load an explicit JSON allowlist; missing/malformed config fails closed."""
    raw = value if value is not None else os.environ.get("AGENT_CITY_B1_TRUSTED_PRODUCERS")
    if not raw:
        raise TrustConfigError("TRUST_CONFIG_UNAVAILABLE")
    try:
        items = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise TrustConfigError("TRUST_CONFIG_INVALID") from exc
    if not isinstance(items, list) or not items:
        raise TrustConfigError("TRUST_CONFIG_INVALID")
    entries: set[tuple[str, str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "repository",
            "policy_name",
            "provider",
            "producer_identity",
        }:
            raise TrustConfigError("TRUST_CONFIG_INVALID")
        values = tuple(
            item[key] for key in ("repository", "policy_name", "provider", "producer_identity")
        )
        if any(not isinstance(value, str) or not value for value in values):
            raise TrustConfigError("TRUST_CONFIG_INVALID")
        entries.add(values)
    return TrustedProducerConfig(frozenset(entries))
