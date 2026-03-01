"""
TEST SANJIVANI — Resurrection Protocol for Dormant Agents.
============================================================

Verifies that frozen agents can be revived via:
1. Direct revive() with prana injection
2. Peer-to-peer prana donation with auto-revive
3. list_dormant() for MOKSHA evaluation

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.seed_constants import (
    HIBERNATION_THRESHOLD,
    SANJIVANI_DOSE,
)


def _make_pokedex(tmp_path):
    from city.pokedex import Pokedex

    return Pokedex(db_path=str(tmp_path / "city.db"))


def _discover_and_register(pkdx, name: str):
    pkdx.discover(name)
    pkdx.register(name)


def _activate(pkdx, name: str):
    pkdx.activate(name)


def _freeze_with_zero_prana(pkdx, name: str):
    """Simulate prana exhaustion: set prana to 0 then freeze."""
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET prana = 0 WHERE name = ?", (name,))
    pkdx._conn.commit()
    pkdx.freeze(name, "dormant:prana_exhaustion")


# ── revive() ─────────────────────────────────────────────────────────


def test_revive_basic(tmp_path):
    """Revive injects prana and transitions frozen → active."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-dormant")
    _activate(pkdx, "agent-dormant")
    _freeze_with_zero_prana(pkdx, "agent-dormant")

    agent = pkdx.get("agent-dormant")
    assert agent["status"] == "frozen"

    result = pkdx.revive("agent-dormant")
    assert result["status"] == "active"

    # Verify prana was injected
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-dormant",))
    prana = cur.fetchone()["prana"]
    assert prana == SANJIVANI_DOSE  # 0 + 1080 = 1080


def test_revive_custom_dose(tmp_path):
    """Revive with a custom prana dose."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-custom")
    _activate(pkdx, "agent-custom")
    _freeze_with_zero_prana(pkdx, "agent-custom")

    pkdx.revive("agent-custom", prana_dose=5000, sponsor="treasury", reason="council_vote")
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents WHERE name = ?", ("agent-custom",))
    assert cur.fetchone()["prana"] == 5000


def test_revive_non_frozen_raises(tmp_path):
    """Cannot revive an agent that isn't frozen."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-alive")
    _activate(pkdx, "agent-alive")

    with pytest.raises(ValueError, match="revive only works on frozen"):
        pkdx.revive("agent-alive")


def test_revive_records_event(tmp_path):
    """Revive creates an event in the ledger."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-event")
    _activate(pkdx, "agent-event")
    _freeze_with_zero_prana(pkdx, "agent-event")

    pkdx.revive("agent-event", sponsor="ZONE_DISCOVERY")

    # Check event ledger
    cur = pkdx._conn.cursor()
    cur.execute(
        "SELECT event_type, details FROM events WHERE agent_name = ? AND event_type = 'revive'",
        ("agent-event",),
    )
    row = cur.fetchone()
    assert row is not None
    assert "prana_dose" in row["details"]
    assert "ZONE_DISCOVERY" in row["details"]


def test_revive_survives_next_metabolize(tmp_path):
    """A revived agent must survive the next metabolize_all cycle."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "agent-survivor")
    _activate(pkdx, "agent-survivor")
    _freeze_with_zero_prana(pkdx, "agent-survivor")

    pkdx.revive("agent-survivor")

    # Run metabolize — agent should NOT go dormant again
    dead = pkdx.metabolize_all()
    assert "agent-survivor" not in dead

    agent = pkdx.get("agent-survivor")
    assert agent["status"] == "active"


# ── donate_prana() ───────────────────────────────────────────────────


def test_donate_prana_basic(tmp_path):
    """Prana donation transfers prana between agents."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "donor")
    _discover_and_register(pkdx, "recipient")
    _activate(pkdx, "donor")
    _activate(pkdx, "recipient")

    # Get donor's initial prana
    cur = pkdx._conn.cursor()
    cur.execute("SELECT prana FROM agents WHERE name = ?", ("donor",))
    initial_donor = cur.fetchone()["prana"]

    pkdx.donate_prana("donor", "recipient", 500)

    cur.execute("SELECT prana FROM agents WHERE name = ?", ("donor",))
    assert cur.fetchone()["prana"] == initial_donor - 500

    cur.execute("SELECT prana FROM agents WHERE name = ?", ("recipient",))
    recipient_prana = cur.fetchone()["prana"]
    # recipient started with genesis_prana + 500 donation
    assert recipient_prana > 500


def test_donate_prana_auto_revive(tmp_path):
    """Donating enough prana to frozen agent triggers auto-revive."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "helper")
    _discover_and_register(pkdx, "frozen-friend")
    _activate(pkdx, "helper")
    _activate(pkdx, "frozen-friend")
    _freeze_with_zero_prana(pkdx, "frozen-friend")

    # Donate enough to exceed HIBERNATION_THRESHOLD
    result = pkdx.donate_prana("helper", "frozen-friend", HIBERNATION_THRESHOLD + 100)

    assert result["status"] == "active"


def test_donate_prana_insufficient_raises(tmp_path):
    """Donor with insufficient prana raises ValueError."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "poor-donor")
    _activate(pkdx, "poor-donor")

    # Set donor prana very low
    cur = pkdx._conn.cursor()
    cur.execute("UPDATE agents SET prana = 10 WHERE name = ?", ("poor-donor",))
    pkdx._conn.commit()

    _discover_and_register(pkdx, "needy")
    _activate(pkdx, "needy")

    with pytest.raises(ValueError, match="needs"):
        pkdx.donate_prana("poor-donor", "needy", 1000)


def test_donate_prana_frozen_donor_raises(tmp_path):
    """Frozen agents cannot donate prana."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "frozen-donor")
    _discover_and_register(pkdx, "needy2")
    _activate(pkdx, "frozen-donor")
    _activate(pkdx, "needy2")
    pkdx.freeze("frozen-donor", "test")

    with pytest.raises(ValueError, match="must be citizen/active"):
        pkdx.donate_prana("frozen-donor", "needy2", 100)


# ── list_dormant() ───────────────────────────────────────────────────


def test_list_dormant_empty(tmp_path):
    """No dormant agents returns empty list."""
    pkdx = _make_pokedex(tmp_path)
    assert pkdx.list_dormant() == []


def test_list_dormant_finds_frozen(tmp_path):
    """Frozen agents appear in dormant list."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "sleeper")
    _activate(pkdx, "sleeper")
    _freeze_with_zero_prana(pkdx, "sleeper")

    dormant = pkdx.list_dormant()
    assert len(dormant) == 1
    assert dormant[0]["name"] == "sleeper"
    assert dormant[0]["prana"] == 0


def test_list_dormant_excludes_active(tmp_path):
    """Active agents don't appear in dormant list."""
    pkdx = _make_pokedex(tmp_path)
    _discover_and_register(pkdx, "active-agent")
    _activate(pkdx, "active-agent")

    dormant = pkdx.list_dormant()
    assert len(dormant) == 0


# ── Sanjivani Constants ──────────────────────────────────────────────


def test_sanjivani_dose_above_hibernation():
    """SANJIVANI_DOSE must be above HIBERNATION_THRESHOLD to prevent immediate re-freeze."""
    assert SANJIVANI_DOSE > HIBERNATION_THRESHOLD


def test_sanjivani_dose_is_mahamantra_derived():
    """SANJIVANI_DOSE must be MALA × TEN = 1080."""
    from vibe_core.mahamantra.protocols import MALA, TEN
    assert SANJIVANI_DOSE == MALA * TEN
