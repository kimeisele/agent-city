from __future__ import annotations

import os
import sys
import subprocess
from functools import lru_cache
from importlib import import_module
from pathlib import Path

from city.wiki.yamlio import load_yaml


def load_mothership_repo_graph_snapshot(
    workspace_root: Path,
    *,
    node_type: str | None = None,
    domain: str | None = None,
    query: str | None = None,
    limit: int = 8,
) -> dict:
    try:
        repo_root = _mothership_repo_root(workspace_root)
        module = _repo_graph_module(workspace_root)
        snapshot = module.build_agent_web_repo_graph_snapshot(
            repo_root,
            node_type=node_type,
            domain=domain,
            query=query,
            limit=limit,
        )
        return {"available": True, "repo_root": str(repo_root), "snapshot": snapshot}
    except Exception as exc:
        return {"available": False, "repo_root": str(repo_root), "error": str(exc)}


def load_mothership_repo_graph_context(workspace_root: Path, *, concept: str) -> dict:
    try:
        repo_root = _mothership_repo_root(workspace_root)
        module = _repo_graph_module(workspace_root)
        context = module.read_agent_web_repo_graph_context(repo_root, concept=concept)
        return {"available": True, "repo_root": str(repo_root), "context": context}
    except Exception as exc:
        return {"available": False, "repo_root": str(repo_root), "error": str(exc), "concept": concept}


def load_mothership_repo_graph_neighbors(
    workspace_root: Path,
    *,
    node_id: str,
    relation: str | None = None,
    depth: int = 1,
    limit: int = 8,
) -> dict:
    try:
        repo_root = _mothership_repo_root(workspace_root)
        module = _repo_graph_module(workspace_root)
        payload = module.read_agent_web_repo_graph_neighbors(
            repo_root,
            node_id=node_id,
            relation=relation,
            depth=depth,
            limit=limit,
        )
        return {"available": True, "repo_root": str(repo_root), "neighbors": payload}
    except Exception as exc:
        return {"available": False, "repo_root": str(repo_root), "error": str(exc), "node_id": node_id}


@lru_cache(maxsize=1)
def _repo_graph_module(workspace_root: Path):
    sibling = workspace_root.parent / "agent-internet"
    if not sibling.exists():
        sibling = _cached_repo_checkout(workspace_root, repo_slug=_agent_internet_repo_slug(workspace_root), cache_name="agent-internet")
    path = str(sibling)
    if path not in sys.path:
        sys.path.insert(0, path)
    return import_module("agent_internet.agent_web_repo_graph")


def _mothership_repo_root(workspace_root: Path) -> Path:
    sibling = workspace_root.parent / "steward-protocol"
    if sibling.exists():
        return sibling
    return _cached_repo_checkout(workspace_root, repo_slug=_mothership_repo_slug(workspace_root), cache_name="steward-protocol")


@lru_cache(maxsize=8)
def _cached_repo_checkout(workspace_root: Path, *, repo_slug: str, cache_name: str) -> Path:
    cache_root = workspace_root / ".vibe" / "federation-cache"
    checkout = cache_root / cache_name
    repo_url = f"https://github.com/{repo_slug}.git"
    if not checkout.exists():
        cache_root.mkdir(parents=True, exist_ok=True)
        _git_run(["clone", "--depth", "1", repo_url, str(checkout)], cwd=workspace_root)
        return checkout
    _git_run(["fetch", "origin", "--depth", "1", "--prune"], cwd=checkout)
    current_branch = _git_output(["branch", "--show-current"], cwd=checkout).strip()
    remote_branches = _git_output(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"], cwd=checkout).splitlines()
    if current_branch and f"origin/{current_branch}" in remote_branches:
        _git_run(["pull", "--rebase", "origin", current_branch], cwd=checkout)
    return checkout


def _agent_internet_repo_slug(workspace_root: Path) -> str:
    owner = _mothership_repo_slug(workspace_root).split("/", 1)[0]
    return _federation_repo_slug(
        workspace_root,
        env_key="AGENT_CITY_AGENT_INTERNET_REPO",
        config_key="agent_internet_repo",
        default=f"{owner}/agent-internet",
    )


def _mothership_repo_slug(workspace_root: Path) -> str:
    return _federation_repo_slug(
        workspace_root,
        env_key="AGENT_CITY_MOTHERSHIP_REPO",
        config_key="mothership_repo",
        default="kimeisele/steward-protocol",
    )


def _federation_repo_slug(workspace_root: Path, *, env_key: str, config_key: str, default: str) -> str:
    env_value = os.getenv(env_key, "").strip()
    if env_value:
        return env_value
    config = _city_config(workspace_root)
    federation = config.get("federation", {}) if isinstance(config, dict) else {}
    slug = str(federation.get(config_key, "") or "").strip()
    return slug or default


@lru_cache(maxsize=4)
def _city_config(workspace_root: Path) -> dict:
    path = workspace_root / "config" / "city.yaml"
    if not path.exists():
        return {}
    loaded = load_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def _git_run(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _git_output(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)
    return completed.stdout