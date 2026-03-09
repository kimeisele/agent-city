from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from city.wiki import repo_graph_client


def test_load_mothership_repo_graph_snapshot_clones_federation_cache_when_siblings_missing(tmp_path, monkeypatch):
    workspace = tmp_path / "agent-city"
    workspace.mkdir(parents=True)
    calls: list[tuple[list[str], str]] = []

    def fake_run(cmd, cwd, check=None, capture_output=None, text=None, **kwargs):
        calls.append((cmd, cwd))
        if cmd[:2] == ["git", "clone"]:
            Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
            return SimpleNamespace(stdout="", returncode=0)
        if cmd[:3] == ["git", "branch", "--show-current"]:
            return SimpleNamespace(stdout="main\n", returncode=0)
        if cmd[:3] == ["git", "for-each-ref", "--format=%(refname:short)"]:
            return SimpleNamespace(stdout="origin/main\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    module = SimpleNamespace(
        build_agent_web_repo_graph_snapshot=lambda root, **kwargs: {
            "summary": {"node_count": 3, "edge_count": 2, "constraint_count": 1, "metric_count": 0},
            "source": {"repo_slug": "test-owner/steward-protocol"},
            "nodes": [],
            "edges": [],
            "metrics": [],
            "constraints": [],
        }
    )

    repo_graph_client._repo_graph_module.cache_clear()
    repo_graph_client._cached_repo_checkout.cache_clear()
    repo_graph_client._city_config.cache_clear()
    monkeypatch.setattr(repo_graph_client, "_city_config", lambda workspace_root: {"federation": {"mothership_repo": "test-owner/steward-protocol"}})
    monkeypatch.setattr(repo_graph_client.subprocess, "run", fake_run)
    monkeypatch.setattr(repo_graph_client, "import_module", lambda name: module)

    payload = repo_graph_client.load_mothership_repo_graph_snapshot(workspace, limit=3)

    assert payload["available"] is True
    assert payload["repo_root"].endswith(".vibe/federation-cache/steward-protocol")
    clone_urls = [cmd[4] for cmd, _ in calls if cmd[:2] == ["git", "clone"]]
    assert "https://github.com/test-owner/steward-protocol.git" in clone_urls
    assert "https://github.com/test-owner/agent-internet.git" in clone_urls