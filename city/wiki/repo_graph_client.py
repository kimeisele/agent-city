from __future__ import annotations

import sys
from functools import lru_cache
from importlib import import_module
from pathlib import Path


def load_mothership_repo_graph_snapshot(
    workspace_root: Path,
    *,
    node_type: str | None = None,
    domain: str | None = None,
    query: str | None = None,
    limit: int = 8,
) -> dict:
    repo_root = workspace_root.parent / "steward-protocol"
    if not repo_root.exists():
        return {"available": False, "repo_root": str(repo_root), "error": "missing_mothership_repo"}
    try:
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
    repo_root = workspace_root.parent / "steward-protocol"
    if not repo_root.exists():
        return {"available": False, "repo_root": str(repo_root), "error": "missing_mothership_repo", "concept": concept}
    try:
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
    repo_root = workspace_root.parent / "steward-protocol"
    if not repo_root.exists():
        return {"available": False, "repo_root": str(repo_root), "error": "missing_mothership_repo", "node_id": node_id}
    try:
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
        raise RuntimeError("missing_agent_internet_repo")
    path = str(sibling)
    if path not in sys.path:
        sys.path.insert(0, path)
    return import_module("agent_internet.agent_web_repo_graph")