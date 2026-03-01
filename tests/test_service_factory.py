"""
Tests for D2: Service Factory — declarative service wiring.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.factory import BuildContext, CityServiceFactory, ServiceDefinition
from city.registry import CityServiceRegistry


def _make_ctx(registry: CityServiceRegistry | None = None) -> BuildContext:
    return BuildContext(
        registry=registry or CityServiceRegistry(),
        db_path=Path("/tmp/test_city.db"),
        offline=True,
        args=object(),
    )


def test_build_simple_service():
    """Factory builds a simple service and registers it."""
    registry = CityServiceRegistry()
    ctx = _make_ctx(registry)

    defs = [
        ServiceDefinition(
            name="test_svc",
            factory=lambda c: {"status": "ok"},
        )
    ]
    factory = CityServiceFactory(defs)
    factory.build_all(registry, ctx)

    assert registry.has("test_svc")
    assert registry.get("test_svc") == {"status": "ok"}
    assert factory.stats()["built"] == ["test_svc"]


def test_dependency_order():
    """Services are built in dependency order."""
    build_order: list[str] = []
    registry = CityServiceRegistry()
    ctx = _make_ctx(registry)

    def make_factory(name: str):
        def f(c):
            build_order.append(name)
            return name

        return f

    defs = [
        ServiceDefinition(name="c", factory=make_factory("c"), deps=("a", "b")),
        ServiceDefinition(name="a", factory=make_factory("a")),
        ServiceDefinition(name="b", factory=make_factory("b"), deps=("a",)),
    ]
    factory = CityServiceFactory(defs)
    factory.build_all(registry, ctx)

    assert build_order == ["a", "b", "c"]


def test_disabled_services():
    """Disabled services are skipped."""
    registry = CityServiceRegistry()
    ctx = _make_ctx(registry)

    defs = [
        ServiceDefinition(name="enabled", factory=lambda c: "yes"),
        ServiceDefinition(name="disabled_svc", factory=lambda c: "no"),
    ]
    factory = CityServiceFactory(defs)
    factory.build_all(registry, ctx, disabled=["disabled_svc"])

    assert registry.has("enabled")
    assert not registry.has("disabled_svc")
    assert "disabled_svc" in factory.stats()["skipped"]


def test_optional_failure():
    """Optional service failure is logged, not raised."""
    registry = CityServiceRegistry()
    ctx = _make_ctx(registry)

    def failing_factory(c):
        raise RuntimeError("boom")

    defs = [
        ServiceDefinition(name="fragile", factory=failing_factory, optional=True),
    ]
    factory = CityServiceFactory(defs)
    factory.build_all(registry, ctx)

    assert not registry.has("fragile")
    assert "fragile" in factory.stats()["failed"]


def test_missing_deps_skip():
    """Service with missing deps is skipped if optional."""
    registry = CityServiceRegistry()
    ctx = _make_ctx(registry)

    defs = [
        ServiceDefinition(
            name="orphan",
            factory=lambda c: "value",
            deps=("nonexistent",),
            optional=True,
        ),
    ]
    factory = CityServiceFactory(defs)
    factory.build_all(registry, ctx)

    assert not registry.has("orphan")
    assert "orphan" in factory.stats()["skipped"]


if __name__ == "__main__":
    test_build_simple_service()
    test_dependency_order()
    test_disabled_services()
    test_optional_failure()
    test_missing_deps_skip()
    print("All 5 service factory tests passed.")
