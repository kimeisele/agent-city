"""
AGENT CITY — Test Configuration
================================

Shared fixtures, markers, timeouts, and sys.path setup.
Every test file imports from here automatically (pytest convention).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# ═══════════════════════════════════════════════════════════════════════
# PATH SETUP — run once, not 10 times per file
# ═══════════════════════════════════════════════════════════════════════

_repo_root = Path(__file__).parent.parent
_steward_root = _repo_root.parent / "steward-protocol"

if str(_steward_root) not in sys.path:
    sys.path.insert(0, str(_steward_root))
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


# ═══════════════════════════════════════════════════════════════════════
# LOGGING — minimal noise during tests
# ═══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s",
)


# ═══════════════════════════════════════════════════════════════════════
# PYTEST HOOKS — markers, timeouts, auto-categorization
# ═══════════════════════════════════════════════════════════════════════


def pytest_configure(config):
    """Register markers and set defaults."""
    config.addinivalue_line("markers", "fast: Quick unit tests (<1s)")
    config.addinivalue_line("markers", "slow: Slow tests (>5s)")
    config.addinivalue_line("markers", "integration: Cross-layer integration tests")
    config.addinivalue_line("markers", "hardening: Stress/chaos/security tests")
    config.addinivalue_line("markers", "layer1: Layer 1 — Jiva + Cell + Identity")
    config.addinivalue_line("markers", "layer2: Layer 2 — Gateway + Network + Mayor")
    config.addinivalue_line("markers", "layer3: Layer 3 — Governance + Contracts")
    config.addinivalue_line("markers", "layer4: Layer 4 — Executor + Delegation")
    config.addinivalue_line("markers", "layer5: Layer 5 — Council + Elections")
    config.addinivalue_line("markers", "layer6: Layer 6 — Federation + Moltbook")
    config.addinivalue_line("markers", "layer7: Layer 7 — Config + Persistence")
    config.addinivalue_line("markers", "federation: Federation protocol tests")


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on file location and name."""
    for item in items:
        fspath = str(item.fspath)

        # Auto-mark by test file layer
        for i in range(1, 8):
            if f"test_layer{i}" in fspath:
                item.add_marker(getattr(pytest.mark, f"layer{i}"))

        # Auto-mark hardening tests
        if "hardening" in fspath:
            item.add_marker(pytest.mark.hardening)
            item.add_marker(pytest.mark.slow)

        # Mark slow tests by name
        if "slow" in item.name.lower() or "stress" in item.name.lower():
            item.add_marker(pytest.mark.slow)

        # Mark full-cycle / integration tests
        if "full_" in item.name or "pipeline" in item.name or "feedback_loop" in item.name:
            item.add_marker(pytest.mark.integration)


# ═══════════════════════════════════════════════════════════════════════
# CORE FIXTURES
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_venu_singleton():
    """Reset the mahamantra VenuOrchestrator singleton between tests.

    The singleton accumulates ticks across the process lifetime.
    Without this, DIW energy gate outcomes depend on test ordering.
    """
    try:
        from vibe_core.mahamantra import mahamantra
        mahamantra.venu.reset()
    except Exception:
        pass
    yield


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the agent-city project root."""
    return _repo_root


@pytest.fixture(scope="session")
def steward_root() -> Path:
    """Return the steward-protocol project root."""
    return _steward_root


@pytest.fixture
def tmp_dir() -> Generator[Path, None, None]:
    """Auto-cleaned temporary directory.

    Replaces the pattern:
        tmpdir = Path(tempfile.mkdtemp())
        try: ...
        finally: shutil.rmtree(tmpdir)

    Usage:
        def test_something(tmp_dir):
            db = tmp_dir / "city.db"
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="agent_city_test_"))
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Reset environment variables for isolated testing."""
    old_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(old_env)


# ═══════════════════════════════════════════════════════════════════════
# CITY INFRASTRUCTURE FIXTURES
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def bank(tmp_dir):
    """CivicBank with temp database."""
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank
    return CivicBank(db_path=str(tmp_dir / "economy.db"))


@pytest.fixture
def pokedex(tmp_dir, bank):
    """Pokedex with temp database and CivicBank."""
    from city.pokedex import Pokedex
    return Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)


@pytest.fixture
def gateway():
    """CityGateway instance."""
    from city.gateway import CityGateway
    return CityGateway()


@pytest.fixture
def network(gateway):
    """CityNetwork wired to gateway."""
    from city.network import CityNetwork
    return CityNetwork(_address_book=gateway.address_book, _gateway=gateway)


@pytest.fixture
def federation_relay(tmp_dir):
    """FederationRelay in dry-run mode with temp dirs."""
    from city.federation import FederationRelay
    return FederationRelay(
        _dry_run=True,
        _directives_dir=tmp_dir / "directives",
        _reports_dir=tmp_dir / "reports",
    )


@pytest.fixture
def council(tmp_dir):
    """CityCouncil with temp state file."""
    from city.council import CityCouncil
    return CityCouncil(_state_path=tmp_dir / "council_state.json")


@pytest.fixture
def mock_bridge():
    """Mock MoltbookClient for bridge tests."""

    class MockBridgeClient:
        def __init__(self):
            self.posts_created = []
            self.comments_created = []
            self.subscribed = False

        def sync_subscribe_submolt(self, name):
            self.subscribed = True
            return {"success": True}

        def sync_get_personalized_feed(self, sort="hot", limit=25):
            return []

        def sync_get_feed(self, sort="hot", limit=25):
            return []

        def sync_create_post(self, title, content, submolt=None):
            self.posts_created.append(
                {"title": title, "content": content, "submolt": submolt}
            )
            return {"id": f"post_{len(self.posts_created)}"}

        def sync_comment_with_verification(self, post_id, content):
            self.comments_created.append({"post_id": post_id, "content": content})
            return {"id": f"comment_{len(self.comments_created)}"}

    return MockBridgeClient()


# ═══════════════════════════════════════════════════════════════════════
# MAYOR FACTORY — replaces _make_mayor() in 3+ test files
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def make_mayor(tmp_dir, pokedex, gateway, network):
    """Factory fixture for creating Mayor instances with optional wiring.

    Replaces the _make_mayor() helper duplicated across test_layer3,
    test_layer5, and test_layer6.

    Usage:
        def test_something(make_mayor):
            mayor = make_mayor()  # bare minimum
            mayor = make_mayor(_federation=relay, _council=council)
    """
    from city.mayor import Mayor

    def _factory(**kwargs):
        return Mayor(
            _pokedex=pokedex,
            _gateway=gateway,
            _network=network,
            _state_path=tmp_dir / "mayor_state.json",
            _offline_mode=True,
            **kwargs,
        )

    return _factory


# ═══════════════════════════════════════════════════════════════════════
# MOCK SANKALPA — for federation/mission tests
# ═══════════════════════════════════════════════════════════════════════


class MockSankalpaRegistry:
    """In-memory mission registry for tests."""

    def __init__(self):
        self.missions: list = []

    def add_mission(self, mission: object) -> None:
        self.missions.append(mission)

    def list_missions(self, status: str | None = None) -> list:
        if status is None:
            return self.missions
        return [m for m in self.missions if m.status.value == status]

    def get_all_missions(self) -> list:
        return self.missions

    def get_active_missions(self) -> list:
        return [m for m in self.missions if getattr(m, "status", None) and m.status.value == "active"]


class MockSankalpa:
    """Minimal SankalpaOrchestrator mock for tests."""

    def __init__(self):
        self.registry = MockSankalpaRegistry()

    def think(self) -> list:
        return []


@pytest.fixture
def mock_sankalpa():
    """MockSankalpa instance."""
    return MockSankalpa()


# ═══════════════════════════════════════════════════════════════════════
# ELECTION HELPER
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def seed_and_elect(pokedex, council):
    """Seed agents and run election. Returns (council, candidates).

    Usage:
        def test_gov(seed_and_elect):
            council, candidates = seed_and_elect(["Alpha", "Beta", "Gamma"])
            assert council.elected_mayor is not None
    """

    def _run(names: list[str], heartbeat: int = 0):
        candidates = []
        for name in names:
            entry = pokedex.register(name)
            candidates.append({
                "name": name,
                "prana": entry.get("vitals", {}).get("prana", 100),
                "guardian": "",
                "position": 0,
            })
        council.run_election(candidates, heartbeat_count=heartbeat)
        return council, candidates

    return _run
