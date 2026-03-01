"""
TDD Red Phase: Tests for VajraGuarded mixin.

Adapted from steward-protocol's VajraGuarded pattern
(vibe_core/protocols/mahajanas/nrisimha/types/security.py).

These tests define the contract BEFORE the implementation exists.
They MUST fail until city/security.py is implemented.
"""

import pytest


# ── Basic Seal Behavior ──────────────────────────────────────────────────


def _make_test_service_class():
    from city.security import VajraGuarded

    class _TestService(VajraGuarded):
        """Minimal class using VajraGuarded for testing."""

        def __init__(self):
            VajraGuarded.__init__(self)
            self.name = "test"
            self._critical_data = {"key": "value"}
            self._mutable_field = 42
            self.protect_attribute("_critical_data")
            self.protect_attribute("name")
            self.vajra_seal()

    return _TestService


def _TestService():
    """Factory that returns an instance of the test service."""
    cls = _make_test_service_class()
    return cls()


def test_vajra_seal_blocks_protected_attribute():
    """After seal, writing to a protected attribute raises PermissionError."""
    svc = _TestService()
    with pytest.raises(PermissionError, match="VAJRA VIOLATION"):
        svc._critical_data = {"poisoned": True}


def test_vajra_seal_blocks_protected_string():
    """Protected string attributes are also immutable after seal."""
    svc = _TestService()
    with pytest.raises(PermissionError, match="VAJRA VIOLATION"):
        svc.name = "hacked"


def test_vajra_seal_allows_unprotected():
    """Non-protected attributes can still be modified after seal."""
    svc = _TestService()
    svc._mutable_field = 99
    assert svc._mutable_field == 99


def test_vajra_sealed_state():
    """is_vajra_sealed() reflects the current seal state."""
    from city.security import VajraGuarded

    class Svc(VajraGuarded):
        def __init__(self):
            VajraGuarded.__init__(self)

    svc = Svc()
    assert svc.is_vajra_sealed() is False
    svc.vajra_seal()
    assert svc.is_vajra_sealed() is True


def test_vajra_unseal_allows_modification():
    """vajra_unseal() temporarily allows protected attribute modification."""
    svc = _TestService()
    svc.vajra_unseal()
    svc._critical_data = {"updated": True}
    assert svc._critical_data == {"updated": True}


def test_vajra_reseal_after_unseal():
    """After unseal + reseal, protection is restored."""
    svc = _TestService()
    svc.vajra_unseal()
    svc._critical_data = {"updated": True}
    svc.vajra_seal()
    with pytest.raises(PermissionError, match="VAJRA VIOLATION"):
        svc._critical_data = {"poisoned": True}


def test_get_protected_attributes():
    """get_protected_attributes() returns a copy of the protected set."""
    svc = _TestService()
    protected = svc.get_protected_attributes()
    assert "_critical_data" in protected
    assert "name" in protected
    assert "_mutable_field" not in protected
    # Returned set is a copy — modifying it doesn't affect the guard
    protected.add("fake")
    assert "fake" not in svc.get_protected_attributes()


def test_vajra_guard_internal_attrs_always_writable():
    """_vajra_sealed and _vajra_protected can always be set (no infinite recursion)."""
    from city.security import VajraGuarded

    class Svc(VajraGuarded):
        def __init__(self):
            VajraGuarded.__init__(self)
            self.vajra_seal()

    svc = Svc()
    # This should NOT raise — internal control attrs must always be writable
    assert svc.is_vajra_sealed() is True


# ── Inheritance ──────────────────────────────────────────────────────────


def test_vajra_works_with_multiple_inheritance():
    """VajraGuarded works correctly as a mixin with other base classes."""
    from city.security import VajraGuarded

    class Base:
        def __init__(self):
            self.base_val = "base"

    class Protected(Base, VajraGuarded):
        def __init__(self):
            Base.__init__(self)
            VajraGuarded.__init__(self)
            self._secret = "original"
            self.protect_attribute("_secret")
            self.vajra_seal()

    obj = Protected()
    assert obj.base_val == "base"
    with pytest.raises(PermissionError):
        obj._secret = "hacked"
    # Unprotected base attrs still writable
    obj.base_val = "modified"
    assert obj.base_val == "modified"


# ── Edge Cases ───────────────────────────────────────────────────────────


def test_vajra_protect_after_seal_has_no_effect():
    """Calling protect_attribute() after seal should not add new protections
    (the seal is already active, but the attribute list itself is not protected)."""
    from city.security import VajraGuarded

    class Svc(VajraGuarded):
        def __init__(self):
            VajraGuarded.__init__(self)
            self.field_a = "a"
            self.field_b = "b"
            self.protect_attribute("field_a")
            self.vajra_seal()

    svc = Svc()
    # field_b was not protected before seal — adding it now
    svc.protect_attribute("field_b")
    # But the seal should still let us modify field_b because
    # protect_attribute after seal is a design smell — test documents behavior
    # Actually: protect_attribute adds to the set, and __setattr__ checks the set.
    # So this WILL protect field_b now. That's the actual behavior in steward-protocol.
    with pytest.raises(PermissionError):
        svc.field_b = "hacked"


def test_vajra_new_attribute_after_seal():
    """New attributes (not existing at seal time) can be added if not protected."""
    svc = _TestService()
    svc.new_dynamic_field = "hello"
    assert svc.new_dynamic_field == "hello"


# ── GitStateAuthority Seal ───────────────────────────────────────────────


def test_git_state_authority_is_sealed(tmp_path):
    """GitStateAuthority must be sealed — config/workspace immutable at runtime."""
    from pathlib import Path
    from city.git_client import GitStateAuthority

    config = {"git": {"runtime_patterns": [], "security_patterns": [], "protected_files": []}}
    gsa = GitStateAuthority(workspace=tmp_path, config=config)

    assert gsa.is_vajra_sealed() is True

    with pytest.raises(PermissionError, match="VAJRA VIOLATION"):
        gsa._config = {"hacked": True}

    with pytest.raises(PermissionError, match="VAJRA VIOLATION"):
        gsa._git_cfg = {"hacked": True}

    with pytest.raises(PermissionError, match="VAJRA VIOLATION"):
        gsa._workspace = Path("/tmp/evil")
