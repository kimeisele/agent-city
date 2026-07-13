import json
import pytest
from city.node_identity import parse_identity_from_text, derive_node_id

SEED_HEX = "4a" * 32  # 32 bytes, deterministic


def _pub_for(seed_hex: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    return sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


class TestParseIdentityFromText:
    def test_json_blob_is_parsed(self):
        """The format GitHub secrets actually carry (Befund §219)."""
        pub = _pub_for(SEED_HEX)
        blob = json.dumps({
            "private_key": SEED_HEX,
            "public_key": pub,
            "node_id": derive_node_id(pub),
        })
        ident = parse_identity_from_text(blob)
        assert ident is not None
        assert ident.node_id == derive_node_id(pub)
        assert ident.public_key_hex == pub

    def test_json_blob_without_node_id_derives_it(self):
        pub = _pub_for(SEED_HEX)
        blob = json.dumps({"private_key": SEED_HEX, "public_key": pub})
        ident = parse_identity_from_text(blob)
        assert ident is not None
        assert ident.node_id == derive_node_id(pub)

    def test_raw_hex_seed_is_parsed(self):
        ident = parse_identity_from_text(SEED_HEX)
        assert ident is not None
        assert ident.public_key_hex == _pub_for(SEED_HEX)

    def test_hex_wins_over_base64_ambiguity(self):
        """64 hex chars are often valid base64 — hex must be tried first."""
        ident = parse_identity_from_text(SEED_HEX)
        assert ident is not None
        assert ident.private_key_hex == SEED_HEX

    def test_garbage_returns_none_and_does_not_raise(self):
        assert parse_identity_from_text("not-a-key") is None
        assert parse_identity_from_text("") is None
        assert parse_identity_from_text("{}") is None

    def test_node_id_matches_steward_algorithm(self):
        """derive_node_id must stay in lockstep with steward.federation_crypto."""
        ident = parse_identity_from_text(SEED_HEX)
        assert ident.node_id == derive_node_id(ident.public_key_hex)
        assert ident.node_id.startswith("ag_")
        assert len(ident.node_id) == 19  # "ag_" + 16


class TestRegressionBefund219:
    def test_json_blob_no_longer_falls_through_to_ephemeral(self):
        """REGRESSION: bytes.fromhex() on a JSON blob raised ValueError and the
        node silently generated a throwaway key on every heartbeat."""
        pub = _pub_for(SEED_HEX)
        blob = json.dumps({"private_key": SEED_HEX, "public_key": pub})
        first = parse_identity_from_text(blob)
        second = parse_identity_from_text(blob)
        assert first.node_id == second.node_id, "identity must be STABLE across calls"
