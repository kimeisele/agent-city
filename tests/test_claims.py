"""
Tests for R1: Claim Levels — Graduated Identity Verification.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from city.claims import ClaimLevel, ClaimManager


def _mock_pokedex(current_level: int = 0) -> MagicMock:
    """Create a mock Pokedex with claim_level support."""
    pokedex = MagicMock()
    pokedex.get_claim_level.return_value = current_level
    pokedex.update_claim_level.return_value = None
    pokedex.verify_identity.return_value = True
    return pokedex


def _claims_membrane():
    from city.membrane import internal_membrane_snapshot

    return internal_membrane_snapshot(source_class="claims")


def _make_pokedex(tmp_path: Path):
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


def test_claim_level_ordering():
    """ClaimLevel values are strictly ordered 0 < 1 < 2 < 3."""
    assert ClaimLevel.DISCOVERED < ClaimLevel.SELF_CLAIMED
    assert ClaimLevel.SELF_CLAIMED < ClaimLevel.PLATFORM_VERIFIED
    assert ClaimLevel.PLATFORM_VERIFIED < ClaimLevel.CRYPTO_VERIFIED
    assert int(ClaimLevel.DISCOVERED) == 0
    assert int(ClaimLevel.CRYPTO_VERIFIED) == 3


def test_self_claim_success():
    """attempt_self_claim() upgrades level when tag matches."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=0)
    result = mgr.attempt_self_claim(
        "alice",
        "Hello world [city-claim:alice] my post",
        pokedex,
    )
    assert result is True
    pokedex.update_claim_level.assert_called_once_with(
        "alice",
        ClaimLevel.SELF_CLAIMED,
        membrane=_claims_membrane(),
    )


def test_self_claim_no_tag():
    """attempt_self_claim() returns False when tag not in title."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=0)
    result = mgr.attempt_self_claim("alice", "Just a normal post", pokedex)
    assert result is False
    pokedex.update_claim_level.assert_not_called()


def test_self_claim_already_claimed():
    """attempt_self_claim() does not downgrade existing level."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=2)  # Already PLATFORM_VERIFIED
    result = mgr.attempt_self_claim(
        "alice",
        "[city-claim:alice] I claim",
        pokedex,
    )
    assert result is False
    pokedex.update_claim_level.assert_not_called()


def test_platform_challenge_flow():
    """initiate + verify platform challenge upgrades to PLATFORM_VERIFIED."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=1)

    nonce = mgr.initiate_platform_challenge("bob")
    assert len(nonce) == 32  # 16 bytes hex = 32 chars
    assert mgr.has_pending_challenge("bob")

    # Agent replies with nonce in DM
    result = mgr.verify_platform_response("bob", f"Here is my proof: {nonce}", pokedex)
    assert result is True
    assert not mgr.has_pending_challenge("bob")
    pokedex.update_claim_level.assert_called_once_with(
        "bob",
        ClaimLevel.PLATFORM_VERIFIED,
        membrane=_claims_membrane(),
    )


def test_platform_challenge_wrong_nonce():
    """verify_platform_response() rejects wrong nonce."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=1)

    mgr.initiate_platform_challenge("charlie")
    result = mgr.verify_platform_response("charlie", "wrong_nonce_here", pokedex)
    assert result is False
    assert mgr.has_pending_challenge("charlie")  # Still pending
    pokedex.update_claim_level.assert_not_called()


def test_crypto_verify():
    """verify_crypto_claim() upgrades to CRYPTO_VERIFIED on valid sig."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=2)
    pokedex.verify_identity.return_value = True

    result = mgr.verify_crypto_claim("dave", "nonce123", "valid_sig_b64", pokedex)
    assert result is True
    pokedex.verify_identity.assert_called_once_with("dave", b"nonce123", "valid_sig_b64")
    pokedex.update_claim_level.assert_called_once_with(
        "dave",
        ClaimLevel.CRYPTO_VERIFIED,
        membrane=_claims_membrane(),
    )


def test_crypto_verify_bad_signature():
    """verify_crypto_claim() rejects invalid ECDSA signature."""
    mgr = ClaimManager()
    pokedex = _mock_pokedex(current_level=2)
    pokedex.verify_identity.return_value = False

    result = mgr.verify_crypto_claim("eve", "nonce456", "bad_sig", pokedex)
    assert result is False
    pokedex.update_claim_level.assert_not_called()


def test_update_claim_level_denied_without_authority(tmp_path):
    """Direct claim-level mutations must fail without explicit authority."""
    pdx = _make_pokedex(tmp_path)
    pdx.register("alice")

    with pytest.raises(PermissionError, match="claim_level_denied:access<operator"):
        pdx.update_claim_level("alice", ClaimLevel.CRYPTO_VERIFIED)


def test_update_claim_level_allowed_with_claims_membrane(tmp_path):
    """Verified claim mutations succeed with explicit trusted claims membrane."""
    pdx = _make_pokedex(tmp_path)
    pdx.register("alice")

    pdx.update_claim_level(
        "alice",
        ClaimLevel.CRYPTO_VERIFIED,
        membrane=_claims_membrane(),
    )

    assert pdx.get_claim_level("alice") == int(ClaimLevel.CRYPTO_VERIFIED)


if __name__ == "__main__":
    test_claim_level_ordering()
    test_self_claim_success()
    test_self_claim_no_tag()
    test_self_claim_already_claimed()
    test_platform_challenge_flow()
    test_platform_challenge_wrong_nonce()
    test_crypto_verify()
    test_crypto_verify_bad_signature()
    print("All 8 claim level tests passed.")
