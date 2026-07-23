"""Explicit atomic B1-S2 review artifact bundle publication."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .canonical import CanonicalError, canonical_bytes, parse_canonical
from .request import ReviewRequestB1, RequestError
from .schema import ReviewVerdictB1, SchemaError

BUNDLE_SCHEMA = "review-artifact-bundle-b1.1"
BUNDLE_FIELDS = frozenset({"schema", "review_request", "review_verdict"})
BUNDLE_FILENAME = "review-artifact-bundle.json"


class ArtifactError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _validated_bundle(request: ReviewRequestB1, verdict: ReviewVerdictB1) -> dict[str, Any]:
    if not isinstance(request, ReviewRequestB1) or not isinstance(verdict, ReviewVerdictB1):
        raise ArtifactError("INVALID_ARTIFACT_TYPE")
    if (
        verdict.review_request_id != request.review_request_id
        or verdict.repository != request.repository
        or verdict.pull_request_number != request.pull_request_number
        or verdict.reviewed_head_sha != request.reviewed_head_sha
        or verdict.review_request_base_sha != request.review_request_base_sha
        or verdict.scope_digest != request.scope_digest
        or tuple(verdict.reviewed_files) != tuple(request.reviewed_files)
    ):
        raise ArtifactError("ARTIFACT_BINDING_MISMATCH")
    return {
        "schema": BUNDLE_SCHEMA,
        "review_request": request.to_mapping(),
        "review_verdict": verdict.to_mapping(),
    }


def _fsync_parent(path: Path) -> None:
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass


def _write_atomic(path: Path, data: bytes, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ArtifactError("ARTIFACT_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as tmp:
            temp_name = tmp.name
            os.chmod(tmp.fileno(), 0o600)
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_name, path)
        temp_name = None
        _fsync_parent(path)
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def write_artifacts(
    directory: str | os.PathLike[str],
    request: ReviewRequestB1,
    verdict: ReviewVerdictB1,
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically publish one bound bundle; no two-file intermediate state exists."""

    bundle = _validated_bundle(request, verdict)
    path = Path(directory) / BUNDLE_FILENAME
    _write_atomic(path, canonical_bytes(bundle), overwrite=overwrite)
    return path


def read_artifacts(path: str | os.PathLike[str]) -> tuple[ReviewRequestB1, ReviewVerdictB1]:
    """Read and validate one published bundle."""

    try:
        value = parse_canonical(Path(path).read_bytes())
        if not isinstance(value, Mapping) or set(value) != BUNDLE_FIELDS:
            raise ArtifactError("INVALID_BUNDLE")
        request = ReviewRequestB1.from_mapping(value["review_request"])
        verdict = ReviewVerdictB1.from_mapping(value["review_verdict"])
        _validated_bundle(request, verdict)
        return request, verdict
    except ArtifactError:
        raise
    except (OSError, CanonicalError, RequestError, SchemaError, TypeError) as exc:
        raise ArtifactError("INVALID_BUNDLE") from exc
