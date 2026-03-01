
import pytest


def test_event_chain_detects_deletion(tmp_dir):
    """DELETE an event from the middle → chain verification MUST fail.

    Attack vector: Direct manipulation of Pokedex event storage.
    If this passes without detection, the audit trail is worthless.
    """
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank
    from city.pokedex import Pokedex

    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pdx = Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)

    # Create events
    pdx.register("Agent1")
    pdx.register("Agent2")
    pdx.activate("Agent1")
    pdx.freeze("Agent1", "test_violation")

    assert pdx.verify_event_chain(), "Chain should be valid before tampering"

    # ATTACK: Delete an event from the middle
    events = pdx.get_events("Agent1")
    assert len(events) >= 3, f"Expected >=3 events, got {len(events)}"

    # If _event_chain is accessible, tamper with it
    if hasattr(pdx, "_event_chain") and len(pdx._event_chain) > 2:
        del pdx._event_chain[1]  # Remove middle event
        assert not pdx.verify_event_chain(), (
            "VULNERABILITY: Event deletion went undetected! "
            "The audit trail can be silently manipulated."
        )
    elif hasattr(pdx, "_db"):
        # Direct DB manipulation
        import sqlite3

        conn = sqlite3.connect(str(tmp_dir / "city.db"))
        cursor = conn.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        if count > 2:
            conn.execute(
                "DELETE FROM events WHERE rowid = (SELECT rowid FROM events LIMIT 1 OFFSET 1)"
            )
            conn.commit()
            conn.close()
            assert not pdx.verify_event_chain(), (
                "VULNERABILITY: Direct DB event deletion went undetected!"
            )
        else:
            conn.close()
            pytest.skip("Not enough events to test deletion")
    else:
        pytest.skip("Cannot access internals to tamper")


def test_event_chain_detects_modification(tmp_dir):
    """MODIFY an event payload → chain verification MUST fail.

    Attack vector: Change event data after recording.
    Impact: History rewriting, false agent status.
    """
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank
    from city.pokedex import Pokedex

    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pdx = Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)

    pdx.register("Victim")
    pdx.activate("Victim")

    assert pdx.verify_event_chain(), "Chain should be valid before tampering"

    # ATTACK: Modify event payload
    if hasattr(pdx, "_event_chain") and pdx._event_chain:
        original = pdx._event_chain[-1].copy()
        pdx._event_chain[-1]["event_type"] = "FORGED_EVENT"
        assert not pdx.verify_event_chain(), (
            "VULNERABILITY: Event modification went undetected! "
            "Agent history can be rewritten."
        )
        # Restore
        pdx._event_chain[-1] = original