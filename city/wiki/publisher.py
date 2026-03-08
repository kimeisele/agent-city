from __future__ import annotations

import json
import subprocess
from pathlib import Path

from city.wiki.compiler import build_wiki
from city.wiki.yamlio import load_yaml


def publish_wiki(*, root: Path, wiki_path: Path | None = None, wiki_repo_url: str | None = None, push: bool = False) -> dict:
    manifest = load_yaml(root / "wiki-src/manifest.yaml")
    effective_wiki_repo_url = wiki_repo_url or str(manifest["world"]["wiki_repo"])
    checkout = ensure_wiki_checkout(
        workspace=root,
        wiki_repo_url=effective_wiki_repo_url,
        wiki_path=wiki_path,
    )
    built = build_wiki(root=root, output_dir=checkout)
    _git_run(["add", "."], cwd=checkout)
    status = _git_output(["status", "--porcelain"], cwd=checkout)
    source_sha = _git_output(["rev-parse", "HEAD"], cwd=root).strip() or "unknown"
    commit_message = str(manifest["publication"]["commit_message_template"]).format(source_sha=source_sha)
    if not status.strip():
        return {
            "changed": False,
            "built": len(built),
            "wiki_path": str(checkout),
            "wiki_repo_url": effective_wiki_repo_url,
            "pushed": False,
            "source_sha": source_sha,
            "commit_message": commit_message,
        }
    _git_run(["commit", "-m", commit_message], cwd=checkout)
    if push:
        _git_run(["push"], cwd=checkout)
    return {
        "changed": True,
        "built": len(built),
        "wiki_path": str(checkout),
        "wiki_repo_url": effective_wiki_repo_url,
        "pushed": push,
        "source_sha": source_sha,
        "commit_message": commit_message,
    }


def write_publication_result(path: Path, result: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return path


def ensure_wiki_checkout(*, workspace: Path, wiki_repo_url: str, wiki_path: Path | None = None) -> Path:
    checkout = wiki_path or workspace / ".vibe" / "wiki"
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        _git_run(["clone", wiki_repo_url, str(checkout)], cwd=workspace)
        return checkout
    _git_run(["pull", "--rebase"], cwd=checkout)
    return checkout


def _git_run(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _git_output(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)
    return completed.stdout
