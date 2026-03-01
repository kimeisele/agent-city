"""
Config loader — SSOT for Agent City constants.

get_config() returns a dict from config/city.yaml.
Falls back to hardcoded defaults if YAML missing.
"""

from __future__ import annotations

import os
from pathlib import Path

_config: dict | None = None
_config_mtime: float = 0.0

_CONFIG_PATH = Path(__file__).parent / "city.yaml"

_DEFAULTS: dict = {
    "mayor": {
        "audit_cooldown_s": 900,
        "event_buffer_max": 200,
        "event_buffer_trim": 100,
        "state_path": "data/mayor_state.json",
        "feed_scan_limit": 20,
    },
    "economy": {"genesis_grant": 100, "zone_tax_percent": 10},
    "governance": {"democratic_threshold": 0.5, "supermajority_threshold": 0.67},
    "issues": {
        "low_prana_threshold": 1000,
        "comment_energy_multiplier": 5,
        "list_limit": 100,
        "gh_timeout_s": 30,
    },
    "contracts": {"ruff_timeout_s": 60, "pytest_timeout_s": 120, "max_violation_lines": 10},
    "executor": {
        "git_author_name": "Mayor Agent",
        "git_author_email": "mayor@agent-city.dev",
        "subprocess_timeout_s": 30,
        "ruff_timeout_s": 60,
    },
    "federation": {
        "mothership_repo": "kimeisele/steward-protocol",
        "dispatch_timeout_s": 30,
        "report_log_max": 50,
        "report_log_trim": 25,
    },
    "network": {"message_log_limit": 1000},
    "database": {"default_path": "data/city.db", "economy_path": "data/economy.db"},
}


def get_config() -> dict:
    """Return city config dict. Reloads if file changed (dev mode)."""
    global _config, _config_mtime

    if _CONFIG_PATH.exists():
        mtime = os.path.getmtime(_CONFIG_PATH)
        if _config is None or mtime != _config_mtime:
            try:
                import yaml

                _config = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
                _config_mtime = mtime
            except Exception:
                _config = dict(_DEFAULTS)
                _config_mtime = mtime
    elif _config is None:
        _config = dict(_DEFAULTS)

    return _config
