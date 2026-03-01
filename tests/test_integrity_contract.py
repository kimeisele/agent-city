"""
TDD Red Phase: Tests for IntegrityContract.

IntegrityContract compares protected files against their last COMMITTED state
using `git show HEAD:<path>`. Git is the source of truth, not a JSON file.

Contract interface: check(cwd: Path) -> ContractResult
  - PASSING: all protected files match HEAD
  - FAILING: drift detected, details list which files changed
"""

import hashlib
import subprocess
import pytest
from pathlib import Path

from city.contracts import ContractStatus


# ── Helpers ──────────────────────────────────────────────────────────────


def _init_git_repo(tmp_path: Path) -> Path:
    """Create a git repo with initial commit."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path),
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=str(tmp_path),
                   check=True, capture_output=True)
    return tmp_path


def _commit_file(repo: Path, rel_path: str, content: str, msg: str = "init") -> None:
    """Write a file and commit it."""
    full = repo / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    subprocess.run(["git", "add", rel_path], cwd=str(repo), check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=str(repo), check=True,
                   capture_output=True)


# ── Tests: Contract returns PASSING when files match HEAD ────────────────


def test_integrity_passing_when_clean(tmp_path):
    """Contract PASSES when protected files match their committed state."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "city/identity.py", "# original")

    config = {"git": {"protected_files": ["city/identity.py"],
                       "runtime_patterns": [], "security_patterns": []}}

    result = check_integrity(repo, protected_files=config["git"]["protected_files"])
    assert result.status == ContractStatus.PASSING


def test_integrity_passing_multiple_files(tmp_path):
    """Contract PASSES when all protected files match HEAD."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "city/identity.py", "# id", "first")
    _commit_file(repo, "city/pokedex.py", "# poke", "second")

    result = check_integrity(repo, protected_files=["city/identity.py", "city/pokedex.py"])
    assert result.status == ContractStatus.PASSING


# ── Tests: Contract returns FAILING when files drift ─────────────────────


def test_integrity_failing_when_modified(tmp_path):
    """Contract FAILS when a protected file is modified after commit."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "city/identity.py", "# original")

    # Modify without committing
    (repo / "city/identity.py").write_text("# TAMPERED")

    result = check_integrity(repo, protected_files=["city/identity.py"])
    assert result.status == ContractStatus.FAILING
    assert "city/identity.py" in result.details[0]


def test_integrity_details_list_all_drifted(tmp_path):
    """Details must list every drifted file, not just the first."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "city/identity.py", "# id", "first")
    _commit_file(repo, "city/pokedex.py", "# poke", "second")

    # Tamper both
    (repo / "city/identity.py").write_text("# TAMPERED1")
    (repo / "city/pokedex.py").write_text("# TAMPERED2")

    result = check_integrity(repo, protected_files=["city/identity.py", "city/pokedex.py"])
    assert result.status == ContractStatus.FAILING
    assert len(result.details) == 2


# ── Tests: Edge cases ────────────────────────────────────────────────────


def test_integrity_new_file_not_in_git(tmp_path):
    """A protected file that doesn't exist in HEAD yet → PASSING (no baseline to compare)."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    # Create initial commit with something else
    _commit_file(repo, "README.md", "# readme")
    # Create protected file but don't commit it
    (repo / "city").mkdir(parents=True)
    (repo / "city/new_module.py").write_text("# new")

    result = check_integrity(repo, protected_files=["city/new_module.py"])
    # New file = no committed baseline = no violation
    assert result.status == ContractStatus.PASSING


def test_integrity_missing_file(tmp_path):
    """A protected file in the list that doesn't exist on disk → skip, no crash."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "README.md", "# readme")

    result = check_integrity(repo, protected_files=["city/nonexistent.py"])
    # Nonexistent = no disk file = skip
    assert result.status == ContractStatus.PASSING


def test_integrity_no_protected_files(tmp_path):
    """Empty protected_files list → PASSING (nothing to check)."""
    from city.contracts import check_integrity

    repo = _init_git_repo(tmp_path)
    _commit_file(repo, "README.md", "# readme")

    result = check_integrity(repo, protected_files=[])
    assert result.status == ContractStatus.PASSING


# ── Tests: Integration with ContractRegistry ─────────────────────────────


def test_integrity_registered_in_defaults():
    """check_integrity should be registerable as a QualityContract."""
    from city.contracts import QualityContract, check_integrity
    from functools import partial

    contract = QualityContract(
        name="integrity",
        description="Protected files match committed state",
        check=partial(check_integrity, protected_files=["city/identity.py"]),
    )
    assert contract.name == "integrity"
