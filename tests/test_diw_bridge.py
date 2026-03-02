"""DIW Bridge Tests — VenuDispatcher, DIWAwareHandler mixin."""

from unittest.mock import MagicMock

from vibe_core.mahamantra.substrate.vm.venu_orchestrator import VenuOrchestrator

from city.karma_handlers import BaseKarmaHandler, KarmaHandlerRegistry
from city.karma_handlers.diw_bridge import DIWAwareHandler, VenuDispatcher


# ── Test Handler (DIW-aware) ─────────────────────────────────────────


class _MockDIWHandler(DIWAwareHandler, BaseKarmaHandler):
    """Test handler that is DIW-aware."""

    @property
    def name(self) -> str:
        return "mock_diw"

    @property
    def priority(self) -> int:
        return 50

    def should_run(self, ctx) -> bool:
        return True

    def execute(self, ctx, operations: list[str]) -> None:
        diw = self.current_diw
        if diw is not None:
            operations.append(f"mock_diw:venu={diw['venu']}")
        else:
            operations.append("mock_diw:no_diw")


class _MockPlainHandler(BaseKarmaHandler):
    """Test handler that is NOT DIW-aware (plain handler)."""

    @property
    def name(self) -> str:
        return "mock_plain"

    @property
    def priority(self) -> int:
        return 60

    def should_run(self, ctx) -> bool:
        return True

    def execute(self, ctx, operations: list[str]) -> None:
        operations.append("mock_plain:ok")


# ── DIWAwareHandler Tests ────────────────────────────────────────────


def test_diw_aware_handler_starts_with_no_event():
    """Initially, current_diw is None."""
    handler = _MockDIWHandler()
    assert handler.current_diw is None


def test_diw_aware_handler_receives_event():
    """on_diw stores the event."""
    handler = _MockDIWHandler()
    event = {
        "diw": 71, "tick": 0, "position": 0, "phase": 0,
        "venu": 7, "vamsi": 0, "murali": 4, "mode": 0,
    }
    handler.on_diw(event)
    assert handler.current_diw is not None
    assert handler.current_diw["diw"] == 71


def test_diw_aware_handler_subscriber_name():
    """subscriber_name returns handler name."""
    handler = _MockDIWHandler()
    assert handler.subscriber_name == "mock_diw"


# ── VenuDispatcher Tests ─────────────────────────────────────────────


def test_dispatcher_without_orchestrator():
    """Without orchestrator, dispatch falls back to plain registry dispatch."""
    registry = KarmaHandlerRegistry()
    registry.register(_MockPlainHandler())
    dispatcher = VenuDispatcher(registry, orchestrator=None)

    ctx = MagicMock()
    ops: list[str] = []
    dispatcher.dispatch(ctx, ops)

    assert "mock_plain:ok" in ops
    # No venu_tick operation without orchestrator
    assert not any(o.startswith("venu_tick:") for o in ops)


def test_dispatcher_with_orchestrator():
    """With orchestrator, dispatch steps the flute and emits DIW."""
    registry = KarmaHandlerRegistry()
    registry.register(_MockPlainHandler())
    dispatcher = VenuDispatcher(registry, orchestrator=VenuOrchestrator())

    ctx = MagicMock()
    ops: list[str] = []
    dispatcher.dispatch(ctx, ops)

    assert "mock_plain:ok" in ops
    # Should have a venu_tick operation
    venu_ops = [o for o in ops if o.startswith("venu_tick:")]
    assert len(venu_ops) == 1


def test_dispatcher_wires_diw_aware_handlers():
    """DIW-aware handlers receive the DIWEvent on dispatch."""
    registry = KarmaHandlerRegistry()
    diw_handler = _MockDIWHandler()
    registry.register(diw_handler)
    dispatcher = VenuDispatcher(registry, orchestrator=VenuOrchestrator())

    ctx = MagicMock()
    ops: list[str] = []
    dispatcher.dispatch(ctx, ops)

    # The DIW-aware handler should have received an event
    assert diw_handler.current_diw is not None
    # And should have appended its operation with the venu field
    diw_ops = [o for o in ops if o.startswith("mock_diw:venu=")]
    assert len(diw_ops) == 1


def test_dispatcher_mixes_diw_and_plain_handlers():
    """Both DIW-aware and plain handlers work together."""
    registry = KarmaHandlerRegistry()
    registry.register(_MockDIWHandler())
    registry.register(_MockPlainHandler())
    dispatcher = VenuDispatcher(registry, orchestrator=VenuOrchestrator())

    ctx = MagicMock()
    ops: list[str] = []
    dispatcher.dispatch(ctx, ops)

    assert "mock_plain:ok" in ops
    assert any(o.startswith("mock_diw:venu=") for o in ops)
    assert any(o.startswith("venu_tick:") for o in ops)


def test_dispatcher_handler_count():
    """handler_count delegates to registry."""
    registry = KarmaHandlerRegistry()
    registry.register(_MockDIWHandler())
    registry.register(_MockPlainHandler())
    dispatcher = VenuDispatcher(registry)
    assert dispatcher.handler_count == 2


def test_dispatcher_wiring_is_idempotent():
    """Multiple dispatch calls don't re-subscribe handlers."""
    registry = KarmaHandlerRegistry()
    registry.register(_MockDIWHandler())
    orch = VenuOrchestrator()
    dispatcher = VenuDispatcher(registry, orchestrator=orch)

    ctx = MagicMock()
    dispatcher.dispatch(ctx, [])
    count_after_first = orch.subscriber_count
    dispatcher.dispatch(ctx, [])
    count_after_second = orch.subscriber_count

    assert count_after_first == count_after_second
