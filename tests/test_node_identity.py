"""Tests for city.node_identity."""

import json
import hashlib
import pytest
from city.node_identity import derive_node_id, ensure_node_identity


class TestDeriveNodeId:
    def test_deterministic(self):
        assert derive_node_id("cafe") == derive_node_id("cafe")

    def test_prefix_and_length(self):
        nid = derive_node_id("cafe")
        assert nid.startswith("ag_")
        assert len(nid) == 19

    def test_different_keys_differ(self):
        assert derive_node_id("aaa") != derive_node_id("bbb")

    def test_matches_steward_algorithm(self):
        pub = "deadbeef1234"
        expected = "ag_" + hashlib.sha256(pub.encode()).hexdigest()[:16]
        assert derive_node_id(pub) == expected


class TestEnsureNodeIdentity:
    def test_generates_and_patches_peer(self, tmp_path):
        fed = tmp_path / "fed"; fed.mkdir()
        (fed / "peer.json").write_text(json.dumps({"identity": {"city_id": "ac"}}))
        r = ensure_node_identity(fed)
        assert r["node_id"].startswith("ag_")
        peer = json.loads((fed / "peer.json").read_text())
        assert peer["identity"]["node_id"] == r["node_id"]

    def test_idempotent(self, tmp_path):
        fed = tmp_path / "fed"; fed.mkdir()
        (fed / "peer.json").write_text(json.dumps({"identity": {}}))
        r1 = ensure_node_identity(fed)
        r2 = ensure_node_identity(fed)
        assert r1["node_id"] == r2["node_id"]

    def test_no_peer_json(self, tmp_path):
        fed = tmp_path / "fed"; fed.mkdir()
        r = ensure_node_identity(fed)
        assert r["node_id"].startswith("ag_")

    def test_node_id_matches_pubkey(self, tmp_path):
        fed = tmp_path / "fed"; fed.mkdir()
        r = ensure_node_identity(fed)
        assert r["node_id"] == derive_node_id(r["public_key"])
