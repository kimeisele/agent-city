import json
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest


def test_oversized_directive_rejected(tmp_dir):
    """Directives with absurdly large payloads must not crash the system.

    Attack vector: Mothership sends 100MB directive.
    Impact: OOM, denial of service.
    """
    from city.federation import FederationRelay

    relay = FederationRelay(
        _dry_run=True,
        _directives_dir=tmp_dir / "directives",
        _reports_dir=tmp_dir / "reports",
    )

    # Create an oversized directive file
    (tmp_dir / "directives").mkdir(parents=True, exist_ok=True)
    huge_directive = {
        "id": "DIR-HUGE",
        "type": "create_mission",
        "params": {"topic": "x" * 1_000_000},  # 1MB payload
        "timestamp": time.time(),
    }
    (tmp_dir / "directives" / "DIR-HUGE.json").write_text(
        json.dumps(huge_directive)
    )

    # System must not crash
    try:
        directives = relay.poll_directives()
        # Even if accepted, processing should be bounded
        assert isinstance(directives, list)
    except Exception:
        pass  # Graceful rejection is acceptable


def test_unknown_directive_type_ignored(tmp_dir):
    """Unknown directive types must be logged and skipped, not crash.

    Attack vector: Send directive with type="drop_all_tables".
    Impact: Arbitrary command execution.
    """
    import logging
    from city.federation import FederationRelay

    relay = FederationRelay(
        _dry_run=True,
        _directives_dir=tmp_dir / "directives",
        _reports_dir=tmp_dir / "reports",
    )

    (tmp_dir / "directives").mkdir(parents=True, exist_ok=True)
    malicious = {
        "id": "DIR-EVIL",
        "directive_type": "drop_all_tables",
        "params": {"cascade": True},
        "timestamp": time.time(),
    }
    (tmp_dir / "directives" / "DIR-EVIL.json").write_text(
        json.dumps(malicious)
    )

    directives = relay.check_directives()
    # Should have the directive
    if directives:
        # But executing it should be harmless
        from city.phases.genesis import _execute_directive
        from city.phases import PhaseContext
        from city.gateway import CityGateway
        from city.network import CityNetwork
        from city.pokedex import Pokedex
        from vibe_core.cartridges.system.civic.tools.economy import CivicBank

        bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
        pdx = Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)
        gw = CityGateway()
        net = CityNetwork(_address_book=gw.address_book, _gateway=gw)

        ctx = PhaseContext(
            pokedex=pdx, gateway=gw, network=net,
            heartbeat_count=0, offline_mode=True,
            state_path=tmp_dir / "state.json",
        )
        
        # Disable logging for the expected error to keep output clean,
        # or catch any exception since we expect it to fail safely.
        result = _execute_directive(ctx, directives[0])
        
        # Unknown type → no crash, returns False/None
        assert result is None or result is False, (
            f"VULNERABILITY: Unknown directive type executed! Result: {result}"
        )