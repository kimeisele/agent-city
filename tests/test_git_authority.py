"""Tests for GitStateAuthority — config-driven git governance."""
import json
import pytest
from pathlib import Path
from city.git_client import GitStateAuthority


@pytest.fixture
def authority(tmp_path):
    """GitStateAuthority with a realistic config, no real git repo needed."""
    config = {
        "git": {
            "runtime_patterns": [
                "data/*.db",
                "data/*.db-journal",
                "data/mayor_state.json",
                ".vibe/state/",
                "*.log",
                "**/__pycache__/",
            ],
            "security_patterns": [
                "**/*.pem",
                "secrets/",
                "*.key",
            ],
            "protected_files": [
                "city/identity.py",
                "city/pokedex.py",
                "config/city.yaml",
            ],
        }
    }
    return GitStateAuthority(workspace=tmp_path, config=config)


# ── Classification ────────────────────────────────────────────────────


def test_classify_runtime(authority):
    assert authority.classify("data/city.db") == "runtime"
    assert authority.classify("data/mayor_state.json") == "runtime"
    assert authority.classify("server.log") == "runtime"


def test_classify_security(authority):
    assert authority.classify("agent.pem") == "security"
    assert authority.classify("deep/nested/key.pem") == "security"
    assert authority.classify("master.key") == "security"


def test_classify_protected(authority):
    assert authority.classify("city/identity.py") == "protected"
    assert authority.classify("config/city.yaml") == "protected"


def test_classify_code(authority):
    assert authority.classify("city/social.py") == "code"
    assert authority.classify("tests/test_social.py") == "code"


def test_is_blocked(authority):
    assert authority.is_blocked("data/city.db") is True
    assert authority.is_blocked("master.key") is True
    assert authority.is_blocked("city/social.py") is False
    assert authority.is_blocked("city/identity.py") is False  # protected but not blocked


# ── .gitignore Generation ────────────────────────────────────────────


def test_generate_gitignore_contains_all_patterns(authority):
    content = authority.generate_gitignore()
    assert "AUTO-GENERATED" in content
    assert "data/*.db" in content
    assert "**/*.pem" in content
    assert "secrets/" in content
    assert "*.log" in content


def test_sync_gitignore_creates_file(authority):
    changed = authority.sync_gitignore()
    assert changed is True
    gitignore = authority._workspace / ".gitignore"
    assert gitignore.exists()
    assert "AUTO-GENERATED" in gitignore.read_text()


def test_sync_gitignore_idempotent(authority):
    authority.sync_gitignore()
    changed = authority.sync_gitignore()
    assert changed is False  # no change on second call


# ── Protected File Integrity ─────────────────────────────────────────


def test_hash_roundtrip(authority):
    """Save hashes, verify passes. Modify file, verify fails."""
    ws = authority._workspace
    # Create fake protected files
    (ws / "city").mkdir(parents=True)
    (ws / "config").mkdir(parents=True)
    (ws / "city" / "identity.py").write_text("original content")
    (ws / "city" / "pokedex.py").write_text("pokedex content")
    (ws / "config" / "city.yaml").write_text("config content")

    # Save baseline
    authority.save_hashes()

    # Verify passes
    violations = authority.verify_protected()
    assert violations == []

    # Tamper with a protected file
    (ws / "city" / "identity.py").write_text("TAMPERED!")

    # Verify catches it
    violations = authority.verify_protected()
    assert "city/identity.py" in violations
    assert len(violations) == 1


def test_verify_no_hash_file(authority):
    """If no hash file exists, verify returns empty (graceful)."""
    violations = authority.verify_protected()
    assert violations == []


def test_compute_hash_missing_file(authority):
    assert authority.compute_hash("nonexistent.py") == "FILE_NOT_FOUND"


# ── Stage Blocking ───────────────────────────────────────────────────


def test_stage_blocks_runtime(authority, monkeypatch):
    """Staging runtime files must be rejected."""
    result = authority.stage(["data/city.db", "data/mayor_state.json"])
    assert result is False


def test_stage_blocks_security(authority, monkeypatch):
    """Staging security files must be rejected."""
    result = authority.stage(["secrets/token.key"])
    assert result is False
