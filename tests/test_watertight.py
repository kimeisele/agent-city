import pytest
import threading
import time
from city.pokedex import Pokedex
from city.jiva import derive_jiva

def test_pokedex_concurrency(tmp_path):
    """Stress test: Parallel agent registration should not crash or corrupt the DB."""
    db_path = tmp_path / "test_concurrency.db"
    pokedex = Pokedex(db_path=db_path)
    
    agent_names = [f"Agent_{i}" for i in range(20)]
    errors = []

    def register_worker(name):
        try:
            # Registration involves multiple DB calls (discover -> register)
            pokedex.register(name)
        except Exception as e:
            errors.append(f"Error in {name}: {e}")

    threads = [threading.Thread(target=register_worker, args=(n,)) for n in agent_names]
    
    # Start all threads simultaneously
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify results
    assert len(errors) == 0, f"Concurrency errors: {errors}"
    
    for name in agent_names:
        agent = pokedex.get(name)
        assert agent is not None
        assert agent["status"] == "citizen"

def test_gpg_leak_prevention(tmp_path):
    """VERIFY: GPG Private material is NEVER stored in the database."""
    db_path = tmp_path / "test_sec.db"
    pokedex = Pokedex(db_path=db_path)
    
    pokedex.register("SecAgent")
    
    # Direct SQL check
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM agents WHERE name = 'SecAgent'").fetchone()
    
    # Check for sensitive strings
    for key in row.keys():
        val = str(row[key])
        assert "PRIVATE KEY" not in val, f"Leak found in column {key}!"
        assert "passphrase" not in val.lower()
    
    conn.close()
