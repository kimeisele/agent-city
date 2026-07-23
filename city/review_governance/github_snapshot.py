"""Fail-closed current PR and base-delta resolution boundary."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .live_evidence import LiveEvidenceError
from .readiness import CurrentPRSnapshotB1

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class SnapshotError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sha(value: Any) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise SnapshotError("OBJECT_ID_UNAVAILABLE")
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise SnapshotError("MERGE_CAUSALITY_UNAVAILABLE")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotError("MERGE_CAUSALITY_UNAVAILABLE") from exc
    if parsed.tzinfo is None:
        raise SnapshotError("MERGE_CAUSALITY_UNAVAILABLE")
    return parsed.astimezone(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class SnapshotSource(Protocol):
    def get(self, path: str) -> Any: ...

    def get_all(
        self, path: str, *, collection_key: str | None = None, max_pages: int = 20
    ) -> list[Mapping[str, Any]]: ...


@dataclass
class GitHubSnapshotResolver:
    client: SnapshotSource

    def _all(self, path: str, *, collection_key: str | None = None) -> list[Mapping[str, Any]]:
        getter = getattr(self.client, "get_all", None)
        if not callable(getter):
            raise SnapshotError("PAGINATION_UNAVAILABLE")
        try:
            return getter(path, collection_key=collection_key)
        except LiveEvidenceError as exc:
            raise SnapshotError(exc.code) from exc

    def _tree(self, repository: str, commit_sha: str) -> dict[str, str]:
        commit = self.client.get(f"/repos/{repository}/git/commits/{commit_sha}")
        tree_sha = commit.get("tree", {}).get("sha") if isinstance(commit, Mapping) else None
        if not isinstance(tree_sha, str):
            raise SnapshotError("OBJECT_ID_UNAVAILABLE")
        value = self.client.get(f"/repos/{repository}/git/trees/{tree_sha}?recursive=1")
        if not isinstance(value, Mapping) or value.get("truncated"):
            raise SnapshotError("TREE_INCOMPLETE")
        entries = value.get("tree")
        if not isinstance(entries, list):
            raise SnapshotError("TREE_RESPONSE_INVALID")
        result: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, Mapping) or entry.get("type") != "blob":
                continue
            path, blob = entry.get("path"), entry.get("sha")
            if not isinstance(path, str) or not isinstance(blob, str) or not SHA_RE.fullmatch(blob):
                raise SnapshotError("OBJECT_ID_UNAVAILABLE")
            result[path] = blob
        return result

    def _scope(
        self, files: Any, *, base_blobs: Mapping[str, str], head_blobs: Mapping[str, str]
    ) -> tuple[dict[str, Any], ...]:
        if not isinstance(files, list):
            raise SnapshotError("FILES_RESPONSE_INVALID")
        entries: list[dict[str, Any]] = []
        for item in files:
            if not isinstance(item, Mapping):
                raise SnapshotError("FILES_RESPONSE_INVALID")
            status = item.get("status")
            change_type = {
                "added": "added",
                "modified": "modified",
                "removed": "deleted",
                "renamed": "renamed",
                "copied": "copied",
            }.get(status)
            if change_type is None:
                raise SnapshotError("UNKNOWN_CHANGE_TYPE")
            path = item.get("filename")
            previous_path = item.get("previous_filename")
            base_blob_sha = (
                None if change_type == "added" else base_blobs.get(previous_path or path)
            )
            head_blob_sha = None if change_type == "deleted" else head_blobs.get(path)
            if change_type in {"added", "modified", "renamed", "copied"} and head_blob_sha is None:
                raise SnapshotError("OBJECT_ID_UNAVAILABLE")
            if (
                change_type in {"modified", "deleted", "renamed", "copied"}
                and base_blob_sha is None
            ):
                raise SnapshotError("OBJECT_ID_UNAVAILABLE")
            entries.append(
                {
                    "path": path,
                    "change_type": change_type,
                    "previous_path": previous_path,
                    "base_blob_sha": base_blob_sha,
                    "head_blob_sha": head_blob_sha,
                }
            )
        return tuple(entries)

    def resolve(
        self, *, repository: str, pull_request_number: int, allow_closed: bool = False
    ) -> CurrentPRSnapshotB1:
        try:
            pr = self.client.get(f"/repos/{repository}/pulls/{pull_request_number}")
            if not isinstance(pr, Mapping) or (
                pr.get("state") != "open" and not (allow_closed and pr.get("merged_at"))
            ):
                raise SnapshotError("PR_NOT_OPEN")
            head = _sha(pr.get("head", {}).get("sha"))
            base = _sha(pr.get("base", {}).get("sha"))
            integration = _sha(pr.get("merge_commit_sha"))
            files = self._all(f"/repos/{repository}/pulls/{pull_request_number}/files?per_page=100")
            scope = self._scope(
                files,
                base_blobs=self._tree(repository, base),
                head_blobs=self._tree(repository, head),
            )
            mergeable = pr.get("mergeable")
            mergeability = (
                "mergeable"
                if mergeable is True
                else "conflicting"
                if mergeable is False
                else "unknown"
            )
            merged = bool(pr.get("merged_at"))
            merged_at = _timestamp(pr.get("merged_at")) if merged else None
            merged_by = pr.get("merged_by", {}).get("login") if merged else None
            if merged and (not isinstance(merged_by, str) or not isinstance(merged_at, str)):
                raise SnapshotError("MERGE_CAUSALITY_UNAVAILABLE")
            return CurrentPRSnapshotB1(
                repository,
                pull_request_number,
                head,
                base,
                scope,
                integration,
                dt.datetime.now(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
                str(pr.get("state")),
                mergeability,
                merged,
                pr.get("merge_commit_sha") if merged else None,
                merged_by,
                merged_at,
            )
        except SnapshotError:
            raise
        except (LiveEvidenceError, KeyError, TypeError, AttributeError) as exc:
            raise SnapshotError("PR_SNAPSHOT_UNAVAILABLE") from exc

    def resolve_base_delta(
        self,
        *,
        repository: str,
        request_base_sha: str,
        current_base_sha: str,
        pull_request_number: int,
    ) -> tuple[dict[str, Any], ...]:
        try:
            value = self.client.get(
                f"/repos/{repository}/compare/{request_base_sha}...{current_base_sha}?per_page=100"
            )
            if not isinstance(value, Mapping) or value.get("status") not in {
                "ahead",
                "behind",
                "diverged",
                "identical",
            }:
                raise SnapshotError("ANCESTRY_UNAVAILABLE")
            if value.get("status") == "identical":
                return ()
            files = self._all(
                f"/repos/{repository}/compare/{request_base_sha}...{current_base_sha}?per_page=100",
                collection_key="files",
            )
            return self._scope(
                files,
                base_blobs=self._tree(repository, request_base_sha),
                head_blobs=self._tree(repository, current_base_sha),
            )
        except SnapshotError:
            raise
        except (LiveEvidenceError, KeyError, TypeError, AttributeError) as exc:
            raise SnapshotError("BASE_DELTA_UNAVAILABLE") from exc
