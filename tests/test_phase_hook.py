"""PhaseHook — protocol, registry, dispatch tests."""

from __future__ import annotations

from city.phase_hook import (
    ALL_PHASES,
    DHARMA,
    GENESIS,
    KARMA,
    MOKSHA,
    BasePhaseHook,
    PhaseHook,
    PhaseHookRegistry,
)


# ── Test Hooks ─────────────────────────────────────────────────────


class _StubHook(BasePhaseHook):
    def __init__(self, name: str, phase: str, priority: int = 50, gate: bool = True):
        self._name = name
        self._phase = phase
        self._priority = priority
        self._gate = gate
        self.executed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def priority(self) -> int:
        return self._priority

    def should_run(self, ctx) -> bool:
        return self._gate

    def execute(self, ctx, operations: list[str]) -> None:
        self.executed = True
        operations.append(f"executed:{self._name}")


class _CrashHook(BasePhaseHook):
    @property
    def name(self) -> str:
        return "crasher"

    @property
    def phase(self) -> str:
        return GENESIS

    def execute(self, ctx, operations: list[str]) -> None:
        raise RuntimeError("boom")


# ── Protocol Tests ─────────────────────────────────────────────────


def test_stub_hook_is_phase_hook():
    hook = _StubHook("test", GENESIS)
    assert isinstance(hook, PhaseHook)


def test_all_phases_defined():
    assert GENESIS in ALL_PHASES
    assert KARMA in ALL_PHASES
    assert MOKSHA in ALL_PHASES
    assert DHARMA in ALL_PHASES
    assert len(ALL_PHASES) == 4


# ── Registry Tests ─────────────────────────────────────────────────


def test_register_and_dispatch():
    reg = PhaseHookRegistry()
    hook = _StubHook("scanner", GENESIS)
    reg.register(hook)
    assert reg.hook_count(GENESIS) == 1
    assert reg.hook_names(GENESIS) == ["scanner"]

    ops = []
    reg.dispatch(GENESIS, None, ops)
    assert hook.executed
    assert ops == ["executed:scanner"]


def test_dedup_by_name():
    reg = PhaseHookRegistry()
    reg.register(_StubHook("scanner", GENESIS))
    reg.register(_StubHook("scanner", GENESIS))
    assert reg.hook_count(GENESIS) == 1


def test_priority_ordering():
    reg = PhaseHookRegistry()
    reg.register(_StubHook("last", GENESIS, priority=90))
    reg.register(_StubHook("first", GENESIS, priority=5))
    reg.register(_StubHook("middle", GENESIS, priority=50))

    ops = []
    reg.dispatch(GENESIS, None, ops)
    assert ops == ["executed:first", "executed:middle", "executed:last"]


def test_gate_skips_hook():
    reg = PhaseHookRegistry()
    gated = _StubHook("gated", GENESIS, gate=False)
    reg.register(gated)

    ops = []
    reg.dispatch(GENESIS, None, ops)
    assert not gated.executed
    assert ops == []


def test_phase_isolation():
    reg = PhaseHookRegistry()
    reg.register(_StubHook("gen_hook", GENESIS))
    reg.register(_StubHook("kar_hook", KARMA))

    ops = []
    reg.dispatch(GENESIS, None, ops)
    assert ops == ["executed:gen_hook"]  # only genesis hooks

    ops2 = []
    reg.dispatch(KARMA, None, ops2)
    assert ops2 == ["executed:kar_hook"]  # only karma hooks


def test_crash_isolation():
    """One hook crashing must not block others."""
    reg = PhaseHookRegistry()
    reg.register(_StubHook("before", GENESIS, priority=5))
    reg.register(_CrashHook())  # priority=50
    after = _StubHook("after", GENESIS, priority=90)
    reg.register(after)

    ops = []
    reg.dispatch(GENESIS, None, ops)
    assert "executed:before" in ops
    assert after.executed
    assert any("hook_error:crasher" in op for op in ops)


def test_unregister():
    reg = PhaseHookRegistry()
    reg.register(_StubHook("removeme", GENESIS))
    assert reg.hook_count(GENESIS) == 1
    removed = reg.unregister(GENESIS, "removeme")
    assert removed is True
    assert reg.hook_count(GENESIS) == 0


def test_unregister_nonexistent():
    reg = PhaseHookRegistry()
    removed = reg.unregister(GENESIS, "nope")
    assert removed is False


def test_hook_count_total():
    reg = PhaseHookRegistry()
    reg.register(_StubHook("a", GENESIS))
    reg.register(_StubHook("b", KARMA))
    reg.register(_StubHook("c", MOKSHA))
    assert reg.hook_count() == 3
    assert reg.hook_count(GENESIS) == 1


def test_stats():
    reg = PhaseHookRegistry()
    reg.register(_StubHook("scan", GENESIS, priority=10))
    reg.register(_StubHook("heal", MOKSHA, priority=50))
    s = reg.stats()
    assert s[GENESIS]["count"] == 1
    assert s[GENESIS]["names"] == ["scan"]
    assert s[MOKSHA]["count"] == 1
    assert s[KARMA]["count"] == 0


def test_get_hooks():
    reg = PhaseHookRegistry()
    h1 = _StubHook("a", DHARMA, priority=10)
    h2 = _StubHook("b", DHARMA, priority=90)
    reg.register(h2)
    reg.register(h1)
    hooks = reg.get_hooks(DHARMA)
    assert [h.name for h in hooks] == ["a", "b"]


def test_dispatch_empty_phase():
    """Dispatching a phase with no hooks is a no-op."""
    reg = PhaseHookRegistry()
    ops = []
    reg.dispatch(GENESIS, None, ops)
    assert ops == []


def test_base_phase_hook_repr():
    hook = _StubHook("test", GENESIS, priority=42)
    r = repr(hook)
    assert "test" in r
    assert "genesis" in r
    assert "42" in r
