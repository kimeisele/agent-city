from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from city.wiki.publisher import ensure_wiki_checkout, publish_wiki


def test_ensure_wiki_checkout_clones_when_missing(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, cwd, check, capture_output, text):
        calls.append((cmd, cwd))
        if cmd[:2] == ["git", "clone"]:
            Path(cmd[3]).mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("city.wiki.publisher.subprocess.run", fake_run)

    checkout = ensure_wiki_checkout(workspace=tmp_path, wiki_repo_url="git@example:wiki.git")

    assert checkout.exists()
    assert calls[0][0][:2] == ["git", "clone"]


def test_publish_wiki_commits_without_push(tmp_path, monkeypatch):
    checkout = tmp_path / "wiki"
    checkout.mkdir()
    calls = []

    monkeypatch.setattr("city.wiki.publisher.ensure_wiki_checkout", lambda **kwargs: checkout)
    monkeypatch.setattr(
        "city.wiki.publisher.build_wiki",
        lambda root, output_dir: [(output_dir / "Home.md").write_text("# Home\n") or (output_dir / "Home.md")],
    )

    def fake_run(cmd, cwd, check, capture_output, text):
        calls.append(cmd)
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(stdout=" M Home.md\n")
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="abc123\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("city.wiki.publisher.subprocess.run", fake_run)

    result = publish_wiki(root=Path.cwd(), wiki_path=checkout, push=False)

    assert result["changed"] is True
    assert result["pushed"] is False
    assert ["git", "commit", "-m", "wiki: manifest world state from abc123"] in calls


def test_publish_wiki_skips_commit_when_clean(tmp_path, monkeypatch):
    checkout = tmp_path / "wiki"
    checkout.mkdir()
    calls = []

    monkeypatch.setattr("city.wiki.publisher.ensure_wiki_checkout", lambda **kwargs: checkout)
    monkeypatch.setattr("city.wiki.publisher.build_wiki", lambda root, output_dir: [])

    def fake_run(cmd, cwd, check, capture_output, text):
        calls.append(cmd)
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(stdout="")
        return SimpleNamespace(stdout="abc123\n" if cmd[:3] == ["git", "rev-parse", "HEAD"] else "")

    monkeypatch.setattr("city.wiki.publisher.subprocess.run", fake_run)

    result = publish_wiki(root=Path.cwd(), wiki_path=checkout, push=False)

    assert result["changed"] is False
    assert all(cmd[1] != "commit" for cmd in calls if len(cmd) > 1)