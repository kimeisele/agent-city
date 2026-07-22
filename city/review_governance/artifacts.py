"""Explicit opt-in local artifact writer for B1-S2."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .request import ReviewRequestB1
from .schema import ReviewVerdictB1


class ArtifactError(ValueError):
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
) -> tuple[Path, Path]:
    """Write only when explicitly called to a caller-selected directory."""

    target = Path(directory)
    request_path = target / "review-request.json"
    verdict_path = target / "review-verdict.json"
    _write_atomic(request_path, request.canonical_bytes(), overwrite=overwrite)
    try:
        _write_atomic(verdict_path, verdict.canonical_bytes(), overwrite=overwrite)
    except Exception:
        if not overwrite:
            try:
                request_path.unlink()
            except FileNotFoundError:
                pass
        raise
    return request_path, verdict_path
