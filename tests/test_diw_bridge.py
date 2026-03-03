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


# ── 8E: DIW-Gated Handler Tests ────────────────────────────────────────


class TestDIWBitAccessors:
    """DIWAwareHandler bit extraction properties."""

    def test_venu_energy_no_event(self):
        h = _MockDIWHandler()
        assert h.venu_energy == 0

    def test_venu_energy_with_event(self):
        h = _MockDIWHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 42, "vamsi": 5, "murali": 3, "mode": 0})
        assert h.venu_energy == 42

    def test_vamsi_action(self):
        h = _MockDIWHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 7, "vamsi": 123, "murali": 0, "mode": 0})
        assert h.vamsi_action == 123

    def test_murali_phase(self):
        h = _MockDIWHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 7, "vamsi": 0, "murali": 12, "mode": 0})
        assert h.murali_phase == 12


class TestHealHandlerDIWGate:
    """HealHandler energy gating via venu bits."""

    def _make_ctx(self):
        ctx = MagicMock()
        ctx.executor = MagicMock()
        ctx.contracts = MagicMock()
        ctx.contracts.failing.return_value = []
        return ctx

    def test_heal_runs_without_diw(self):
        """No DIW event = no gate = runs."""
        from city.karma_handlers.heal import HealHandler
        h = HealHandler()
        assert h.should_run(self._make_ctx()) is True

    def test_heal_runs_high_energy(self):
        """venu=50 >= 32 threshold = runs."""
        from city.karma_handlers.heal import HealHandler
        h = HealHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 50, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(self._make_ctx()) is True

    def test_heal_skips_low_energy(self):
        """venu=10 < 32 threshold = skipped."""
        from city.karma_handlers.heal import HealHandler
        h = HealHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 10, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(self._make_ctx()) is False

    def test_heal_skips_at_boundary(self):
        """venu=31 < 32 threshold = skipped (boundary)."""
        from city.karma_handlers.heal import HealHandler
        h = HealHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 31, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(self._make_ctx()) is False

    def test_heal_runs_at_threshold(self):
        """venu=32 == 32 threshold = runs."""
        from city.karma_handlers.heal import HealHandler
        h = HealHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 32, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(self._make_ctx()) is True

    def test_heal_skips_without_executor(self):
        """No executor = skipped regardless of energy."""
        from city.karma_handlers.heal import HealHandler
        h = HealHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 63, "vamsi": 0, "murali": 0, "mode": 0})
        ctx = MagicMock()
        ctx.executor = None
        ctx.contracts = MagicMock()
        assert h.should_run(ctx) is False

    def test_heal_is_diw_aware(self):
        """HealHandler extends DIWAwareHandler."""
        from city.karma_handlers.heal import HealHandler
        assert isinstance(HealHandler(), DIWAwareHandler)


class TestCognitionHandlerDIWGate:
    """CognitionHandler energy gating via venu bits."""

    def test_cognition_runs_without_diw(self):
        """No DIW event = no gate = runs."""
        from city.karma_handlers.cognition import CognitionHandler
        h = CognitionHandler()
        assert h.should_run(MagicMock()) is True

    def test_cognition_runs_moderate_energy(self):
        """venu=30 >= 16 threshold = runs."""
        from city.karma_handlers.cognition import CognitionHandler
        h = CognitionHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 30, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(MagicMock()) is True

    def test_cognition_skips_low_energy(self):
        """venu=5 < 16 threshold = skipped."""
        from city.karma_handlers.cognition import CognitionHandler
        h = CognitionHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 5, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(MagicMock()) is False

    def test_cognition_runs_at_threshold(self):
        """venu=16 == 16 threshold = runs."""
        from city.karma_handlers.cognition import CognitionHandler
        h = CognitionHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 16, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(MagicMock()) is True

    def test_cognition_skips_at_boundary(self):
        """venu=15 < 16 threshold = skipped (boundary)."""
        from city.karma_handlers.cognition import CognitionHandler
        h = CognitionHandler()
        h.on_diw({"diw": 0, "tick": 0, "position": 0, "phase": 0,
                   "venu": 15, "vamsi": 0, "murali": 0, "mode": 0})
        assert h.should_run(MagicMock()) is False

    def test_cognition_is_diw_aware(self):
        """CognitionHandler extends DIWAwareHandler."""
        from city.karma_handlers.cognition import CognitionHandler
        assert isinstance(CognitionHandler(), DIWAwareHandler)
