"""AgentNadiManager Tests — Inter-Agent Messaging."""

import shutil
import sys
import tempfile
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── AgentNadiManager Unit Tests ────────────────────────────────────


def test_agent_nadi_creation():
    """AgentNadiManager initializes."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    assert manager.available is True
    assert manager.agent_count() == 0


def test_agent_nadi_register():
    """Register creates inbox for agent."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    assert manager.register("alice") is True
    assert manager.register("bob") is True
    assert manager.agent_count() == 2

    # Duplicate registration returns False
    assert manager.register("alice") is False


def test_agent_nadi_unregister():
    """Unregister removes agent inbox."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    assert manager.agent_count() == 1

    assert manager.unregister("alice") is True
    assert manager.agent_count() == 0
    assert manager.unregister("alice") is False


def test_agent_nadi_point_to_point():
    """Agent A can send a message to Agent B."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    manager.register("bob")

    result = manager.send("alice", "bob", "Hello Bob!")
    assert result is True

    messages = manager.drain("bob")
    assert len(messages) == 1
    assert messages[0]["text"] == "Hello Bob!"
    assert messages[0]["from_agent"] == "alice"

    assert manager.drain("alice") == []


def test_agent_nadi_broadcast():
    """Agent A broadcasts to all other agents."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    manager.register("bob")
    manager.register("carol")

    count = manager.broadcast("alice", "Hello everyone!")
    assert count == 2

    bob_msgs = manager.drain("bob")
    carol_msgs = manager.drain("carol")
    assert len(bob_msgs) == 1
    assert len(carol_msgs) == 1
    assert bob_msgs[0]["text"] == "Hello everyone!"


def test_agent_nadi_priority_sorting():
    """Drained messages sorted by priority (highest first)."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    manager.register("bob")

    manager.send("alice", "bob", "low priority", priority=0)
    manager.send("alice", "bob", "high priority", priority=3)
    manager.send("alice", "bob", "medium priority", priority=1)

    messages = manager.drain("bob")
    assert len(messages) == 3
    assert messages[0]["text"] == "high priority"
    assert messages[1]["text"] == "medium priority"
    assert messages[2]["text"] == "low priority"


def test_agent_nadi_drain_empty():
    """Drain on agent with no messages returns []."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    assert manager.drain("alice") == []


def test_agent_nadi_send_unknown_agent():
    """Send to unregistered agent returns False."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    assert manager.send("alice", "nobody", "Hello?") is False


def test_agent_nadi_stats():
    """Stats reflect aggregate state."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    manager.register("bob")
    manager.send("alice", "bob", "test")

    stats = manager.stats()
    assert stats["agents"] == 2
    assert stats["total_sent"] >= 1


def test_agent_nadi_mesh_connectivity():
    """All agents can message each other."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    manager.register("bob")
    manager.register("carol")

    assert manager.send("alice", "bob", "a→b") is True
    assert manager.send("bob", "carol", "b→c") is True
    assert manager.send("carol", "alice", "c→a") is True

    assert len(manager.drain("bob")) == 1
    assert len(manager.drain("carol")) == 1
    assert len(manager.drain("alice")) == 1


def test_agent_nadi_correlation_id():
    """Correlation IDs preserved in messages."""
    from city.agent_nadi import AgentNadiManager

    manager = AgentNadiManager()
    manager.register("alice")
    manager.register("bob")

    manager.send("alice", "bob", "request", correlation_id="req_123")

    messages = manager.drain("bob")
    assert len(messages) == 1
    assert messages[0]["correlation_id"] == "req_123"


# ── Integration with Network ─────────────────────────────────────


def test_network_with_agent_nadi():
    """CityNetwork delegates send/broadcast via AgentNadi."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.agent_nadi import AgentNadiManager
    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gateway = CityGateway()
        agent_nadi = AgentNadiManager()

        network = CityNetwork(
            _address_book=gateway.address_book,
            _gateway=gateway,
            _agent_nadi=agent_nadi,
        )

        pokedex.register("alice")
        pokedex.register("bob")
        cell_a = pokedex.get_cell("alice")
        cell_b = pokedex.get_cell("bob")
        network.register_agent("alice", cell_a)
        network.register_agent("bob", cell_b)

        assert agent_nadi.agent_count() == 2

        network.send("alice", "bob", "Hello via network!")

        messages = agent_nadi.drain("bob")
        assert len(messages) == 1
        assert messages[0]["text"] == "Hello via network!"
    finally:
        shutil.rmtree(tmp)


def test_network_without_agent_nadi():
    """CityNetwork works without AgentNadi (backward compat)."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.gateway import CityGateway
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(tmp / "city.db"), bank=bank)
        gateway = CityGateway()

        network = CityNetwork(
            _address_book=gateway.address_book,
            _gateway=gateway,
        )

        pokedex.register("alice")
        pokedex.register("bob")
        cell_a = pokedex.get_cell("alice")
        cell_b = pokedex.get_cell("bob")
        network.register_agent("alice", cell_a)
        network.register_agent("bob", cell_b)

        result = network.send("alice", "bob", "Hello!")
        assert result is True
    finally:
        shutil.rmtree(tmp)


# ── Integration with Mayor ───────────────────────────────────────


def test_mayor_with_agent_nadi():
    """Mayor with AgentNadiManager runs full rotation."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    from city.agent_nadi import AgentNadiManager
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex

    tmp = Path(tempfile.mkdtemp())
    try:
        db_path = tmp / "city.db"
        bank = CivicBank(db_path=str(tmp / "economy.db"))
        pokedex = Pokedex(db_path=str(db_path), bank=bank)
        gateway = CityGateway()
        agent_nadi = AgentNadiManager()
        network = CityNetwork(
            _address_book=gateway.address_book,
            _gateway=gateway,
            _agent_nadi=agent_nadi,
        )

        mayor = Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp / "mayor_state.json",
            _offline_mode=True,
            _agent_nadi=agent_nadi,
        )

        results = mayor.run_cycle(4)
        assert len(results) == 4
    finally:
        shutil.rmtree(tmp)


# ── Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import unittest

    test_functions = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    suite = unittest.TestSuite()
    for fn in test_functions:
        suite.addTest(unittest.FunctionTestCase(fn))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
