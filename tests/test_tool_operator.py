"""
TDD Red Phase: ToolOperator — CLI Agent Identity & Access Control.

ToolOperators are non-autonomous agents (Claude Code, Cursor, GH Actions, etc.)
that mutate the repo but have no Jiva, no MahaCell, no ECDSA key.

They need:
  1. Registration in Pokedex (separate operators table)
  2. AccessClass (OBSERVER, OPERATOR, STEWARD, SOVEREIGN)
  3. Fingerprint (trace-only, not crypto)
  4. Event logging in the chained ledger
  5. O(1) lookup by name
"""

from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_pokedex(tmp_path: Path):
    """Create a minimal Pokedex pointing at tmp_path for isolated tests."""
    # We mock the heavy deps (CivicBank, MahaCellUnified) to keep tests fast
    from unittest.mock import MagicMock, patch

    mock_bank = MagicMock()
    mock_bank.get_balance.return_value = 0
    mock_bank.get_system_stats.return_value = {}

    with patch("city.pokedex.CivicBank", return_value=mock_bank):
        with patch("city.pokedex.get_config", return_value={"economy": {}}):
            from city.pokedex import Pokedex
            return Pokedex(
                db_path=str(tmp_path / "test.db"),
                bank=mock_bank,
                constitution_path=str(tmp_path / "CONSTITUTION.md"),
            )


# ── Tests: AccessClass Enum ─────────────────────────────────────────────


def test_access_class_enum_values():
    """AccessClass enum must have exactly 4 levels."""
    from city.access import AccessClass

    assert AccessClass.OBSERVER.value == "observer"
    assert AccessClass.OPERATOR.value == "operator"
    assert AccessClass.STEWARD.value == "steward"
    assert AccessClass.SOVEREIGN.value == "sovereign"


def test_access_class_can_write():
    """OBSERVER cannot write, all others can."""
    from city.access import AccessClass

    assert AccessClass.OBSERVER.can_write is False
    assert AccessClass.OPERATOR.can_write is True
    assert AccessClass.STEWARD.can_write is True
    assert AccessClass.SOVEREIGN.can_write is True


def test_access_class_can_modify_protected():
    """Only STEWARD and SOVEREIGN can modify protected files."""
    from city.access import AccessClass

    assert AccessClass.OBSERVER.can_modify_protected is False
    assert AccessClass.OPERATOR.can_modify_protected is False
    assert AccessClass.STEWARD.can_modify_protected is True
    assert AccessClass.SOVEREIGN.can_modify_protected is True


def test_access_class_ordering():
    """Higher access classes must compare greater than lower ones."""
    from city.access import AccessClass

    assert AccessClass.SOVEREIGN.level > AccessClass.STEWARD.level
    assert AccessClass.STEWARD.level > AccessClass.OPERATOR.level
    assert AccessClass.OPERATOR.level > AccessClass.OBSERVER.level


# ── Tests: ToolOperator Registration ─────────────────────────────────────


def test_register_operator(tmp_path):
    """Pokedex.register_operator() creates an operator entry."""
    pdx = _make_pokedex(tmp_path)

    op = pdx.register_operator(
        name="opus_3_cascade",
        operator_type="cascade",
        access_class="steward",
        registered_by="sovereign:ss",
    )

    assert op is not None
    assert op["name"] == "opus_3_cascade"
    assert op["operator_type"] == "cascade"
    assert op["access_class"] == "steward"
    assert op["registered_by"] == "sovereign:ss"
    assert op["fingerprint"] is not None
    assert len(op["fingerprint"]) == 16  # SHA-256 truncated to 16 hex chars


def test_register_operator_idempotent(tmp_path):
    """Registering the same operator twice returns existing record."""
    pdx = _make_pokedex(tmp_path)

    op1 = pdx.register_operator("opus_3", "cascade", "steward", "sovereign:ss")
    op2 = pdx.register_operator("opus_3", "cascade", "steward", "sovereign:ss")

    assert op1["name"] == op2["name"]
    assert op1["fingerprint"] == op2["fingerprint"]


def test_register_operator_records_event(tmp_path):
    """Registration must create an event in the chained ledger."""
    pdx = _make_pokedex(tmp_path)

    pdx.register_operator("test_bot", "gh_actions", "operator", "sovereign:ss")

    events = pdx.get_events("test_bot", limit=5)
    assert len(events) >= 1
    assert events[0]["event_type"] == "register_operator"


# ── Tests: Operator Lookup ───────────────────────────────────────────────


def test_get_operator(tmp_path):
    """Pokedex.get_operator() returns operator by name."""
    pdx = _make_pokedex(tmp_path)

    pdx.register_operator("my_cursor", "cursor", "operator", "sovereign:ss")
    op = pdx.get_operator("my_cursor")

    assert op is not None
    assert op["name"] == "my_cursor"
    assert op["access_class"] == "operator"


def test_get_operator_not_found(tmp_path):
    """get_operator() returns None for unknown operators."""
    pdx = _make_pokedex(tmp_path)

    assert pdx.get_operator("nonexistent") is None


def test_list_operators(tmp_path):
    """list_operators() returns all registered operators."""
    pdx = _make_pokedex(tmp_path)

    pdx.register_operator("bot_a", "cascade", "steward", "sovereign:ss")
    pdx.register_operator("bot_b", "cursor", "operator", "sovereign:ss")

    ops = pdx.list_operators()
    assert len(ops) == 2
    names = {o["name"] for o in ops}
    assert names == {"bot_a", "bot_b"}


# ── Tests: Access Checks ────────────────────────────────────────────────


def test_check_operator_access_write(tmp_path):
    """OPERATOR can write, OBSERVER cannot."""
    pdx = _make_pokedex(tmp_path)

    pdx.register_operator("writer", "cascade", "operator", "sovereign:ss")
    pdx.register_operator("reader", "cascade", "observer", "sovereign:ss")

    assert pdx.check_operator_access("writer", "write") is True
    assert pdx.check_operator_access("reader", "write") is False


def test_check_operator_access_protected(tmp_path):
    """Only STEWARD+ can modify protected files."""
    pdx = _make_pokedex(tmp_path)

    pdx.register_operator("steward_bot", "cascade", "steward", "sovereign:ss")
    pdx.register_operator("normal_bot", "cascade", "operator", "sovereign:ss")

    assert pdx.check_operator_access("steward_bot", "modify_protected") is True
    assert pdx.check_operator_access("normal_bot", "modify_protected") is False


def test_check_operator_access_unknown(tmp_path):
    """Unknown operator has no access."""
    pdx = _make_pokedex(tmp_path)

    assert pdx.check_operator_access("ghost", "write") is False


# ── Tests: Update Access Class ───────────────────────────────────────────


def test_update_operator_access(tmp_path):
    """Access class can be upgraded/downgraded."""
    pdx = _make_pokedex(tmp_path)

    pdx.register_operator("bot", "cascade", "observer", "sovereign:ss")
    assert pdx.get_operator("bot")["access_class"] == "observer"

    pdx.update_operator_access("bot", "steward", "promoted by council")
    assert pdx.get_operator("bot")["access_class"] == "steward"

    events = pdx.get_events("bot", limit=10)
    access_events = [e for e in events if e["event_type"] == "access_change"]
    assert len(access_events) >= 1
