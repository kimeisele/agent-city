import sqlite3
import os
import shutil
from pathlib import Path
from city.pokedex import Pokedex
from city.discovery_ledger import DiscoveryLedger
from city.signal_state_ledger import SignalStateLedger
from city.factory import _perform_state_migration

def test_migration():
    # Setup temporary databases
    os.makedirs("data/test", exist_ok=True)
    pokedex_db = "data/test/city.db"
    discovery_db = "data/test/discovery.db"
    signal_db = "data/test/signal_state.db"

    # 1. Manually create legacy tables in Pokedex
    conn = sqlite3.connect(pokedex_db)
    conn.execute("CREATE TABLE discovered_repos (full_name TEXT PRIMARY KEY, url TEXT)")
    conn.execute("INSERT INTO discovered_repos (full_name, url) VALUES ('test/repo', 'http://github.com/test/repo')")
    
    conn.execute("CREATE TABLE processed_signals (signal_id TEXT PRIMARY KEY, source TEXT, processed_at TEXT)")
    conn.execute("INSERT INTO processed_signals (signal_id, source, processed_at) VALUES ('msg_1', 'moltbook', '2026-03-24')")
    
    conn.execute("CREATE TABLE system_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO system_meta (key, value, updated_at) VALUES ('session_id', '12345', '2026-03-24')")
    conn.commit()
    conn.close()

    # 2. Initialize new ledgers
    discovery_ledger = DiscoveryLedger(discovery_db)
    signal_ledger = SignalStateLedger(signal_db)
    
    # Mock a pokedex object with a _conn attribute
    class MockPokedex:
        def __init__(self, path):
            self._conn = sqlite3.connect(path)
            self._conn.row_factory = sqlite3.Row

    mock_pokedex = MockPokedex(pokedex_db)

    # 3. Perform Migration
    print("Running migration...")
    _perform_state_migration(mock_pokedex, discovery_ledger, signal_ledger)

    # 4. Verify results in new ledgers
    print("Verifying discovery data...")
    repos = discovery_ledger.get_unprocessed_repos()
    assert len(repos) == 1
    assert repos[0]['full_name'] == 'test/repo'
    assert discovery_ledger.get_meta('session_id') == '12345'

    print("Verifying signal data...")
    assert signal_ledger.is_signal_processed('msg_1') == True
    assert signal_ledger.is_signal_processed('msg_2') == False

    # 5. Verify tables are dropped in Pokedex
    cur = mock_pokedex._conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='discovered_repos'")
    assert cur.fetchone() is None
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processed_signals'")
    assert cur.fetchone() is None
    
    print("SUCCESS: Migration and isolation verified.")
    mock_pokedex._conn.close()

if __name__ == "__main__":
    try:
        test_migration()
    finally:
        if os.path.exists("data/test"):
            shutil.rmtree("data/test")
