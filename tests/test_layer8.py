"""Layer 8 Tests — Autonomous System Verification & Chaos Engineering.

Linked to GitHub Issue #15.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from city.daemon import DaemonService, SADHANA
from city.gateway import CityGateway
from city.mayor import Mayor
from city.network import CityNetwork
from city.ouroboros import OuroborosGeneSystem
from city.pokedex import Pokedex
from vibe_core.cartridges.system.civic.tools.economy import CivicBank


def test_ouroboros_chaos_engineering():
    """GREEN TEST: Ouroboros Gene System injects runtime chaos."""
    genes = OuroborosGeneSystem()
    
    # Run the chaos engine a few times
    for _ in range(5):
        genes.inject_chaos()
        
    stats = genes.stats()
    assert "entropy_load" in stats
    assert "mutation_vector" in stats
    assert stats["enabled"] is True
    assert stats["mantra_shield"] <= 100


def test_daemon_heartbeat_frequency():
    """GREEN TEST: DaemonService maintains long-running heartbeat with entropy-based frequency."""
    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
        )

        # Set 10Hz to make the test extremely fast
        daemon = DaemonService(mayor=mayor, frequency_hz=10.0)
        
        # Non-blocking start
        daemon.start(block=False)
        time.sleep(0.3)  # Let it run for ~3 cycles
        daemon.stop()
        
        # Mayor should have advanced its heartbeat
        assert mayor._heartbeat_count >= 1
    finally:
        shutil.rmtree(tmp)


