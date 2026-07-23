"""Read-only GitHub evidence adapters for B1-S3B.

The default client uses only GET requests.  No workflow, merge mutation, or
execution of repository content is performed here.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from .evidence import (
    HEAD_POLICY,
    MERGE_POLICY,
    HeadEvidenceResult,
    IntegrationEvidenceResult,
)
from .schema import EvidenceRefB1


class LiveEvidenceError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GitHubJSONClient:
    def __init__(self, *, token: str | None = None, timeout: float = 15.0):
        self._token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.timeout = timeout

    def get(self, path: str) -> Any:
        if not self._token:
            raise LiveEvidenceError("GITHUB_TOKEN_UNAVAILABLE")
        if not path.startswith("/repos/"):
            raise LiveEvidenceError("INVALID_GITHUB_PATH")
        request = urllib.request.Request(
            "https://api.github.com" + path,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            TimeoutError,
        ) as exc:
            raise LiveEvidenceError("GITHUB_READ_FAILED") from exc


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp(value: Any) -> str:
    """Normalize GitHub's RFC-3339 timestamps to the B1 second-precision form."""
    if not isinstance(value, str) or not value:
        return _now()
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _now()
    if parsed.tzinfo is None:
        return _now()
    return parsed.astimezone(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _producer(item: Mapping[str, Any]) -> str:
    app = item.get("app")
    if isinstance(app, Mapping) and isinstance(app.get("slug"), str):
        return app["slug"]
    creator = item.get("creator")
    if isinstance(creator, Mapping) and isinstance(creator.get("login"), str):
        return creator["login"]
    return "unknown"


def _run_id(item: Mapping[str, Any]) -> str | None:
    value = item.get("id") or item.get("node_id")
    return str(value) if value is not None else None


@dataclass
class GitHubLiveEvidenceProvider:
    client: GitHubJSONClient

    def _checks(self, repository: str, sha: str) -> list[Mapping[str, Any]]:
        value = self.client.get(
            "/repos/" + repository + "/commits/" + sha + "/check-runs?per_page=100"
        )
        runs = value.get("check_runs") if isinstance(value, Mapping) else None
        if not isinstance(runs, list):
            raise LiveEvidenceError("CHECK_RESPONSE_INVALID")
        return [item for item in runs if isinstance(item, Mapping)]

    def _statuses(self, repository: str, sha: str) -> list[Mapping[str, Any]]:
        value = self.client.get(
            "/repos/" + repository + "/commits/" + sha + "/statuses?per_page=100"
        )
        if not isinstance(value, list):
            raise LiveEvidenceError("STATUS_RESPONSE_INVALID")
        return [item for item in value if isinstance(item, Mapping)]

    def resolve(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        evidence_ref: EvidenceRefB1,
    ) -> HeadEvidenceResult:
        if evidence_ref.name != HEAD_POLICY or evidence_ref.sha != reviewed_head_sha:
            return HeadEvidenceResult(
                repository,
                pull_request_number,
                HEAD_POLICY,
                None,
                reviewed_head_sha,
                "unknown",
                evidence_ref.provider,
                "adapter",
                None,
                _now(),
                "mismatched",
                "EVIDENCE_SHA_MISMATCH",
            )
        try:
            if evidence_ref.provider == "github_check":
                candidates = [
                    item
                    for item in self._checks(repository, reviewed_head_sha)
                    if item.get("name") == evidence_ref.name
                    and item.get("head_sha") == reviewed_head_sha
                ]
                if len(candidates) != 1:
                    state = "unavailable" if not candidates else "ambiguous"
                    return HeadEvidenceResult(
                        repository,
                        pull_request_number,
                        HEAD_POLICY,
                        None,
                        reviewed_head_sha,
                        "unknown",
                        evidence_ref.provider,
                        "github",
                        None,
                        _now(),
                        state,
                        "EVIDENCE_UNAVAILABLE",
                    )
                item = candidates[0]
                conclusion = str(item.get("conclusion") or item.get("status") or "unknown").lower()
                producer = _producer(item)
                run_id = _run_id(item)
                state = (
                    "verified"
                    if conclusion == "success" and producer != "unknown" and run_id
                    else "unavailable"
                )
                result = HeadEvidenceResult(
                    repository,
                    pull_request_number,
                    HEAD_POLICY,
                    reviewed_head_sha,
                    reviewed_head_sha,
                    conclusion,
                    evidence_ref.provider,
                    producer if producer != "unknown" else "github",
                    run_id,
                    _timestamp(item.get("completed_at") or item.get("started_at")),
                    state,
                    None if state == "verified" else "PRODUCER_UNAVAILABLE",
                )
            else:
                candidates = [
                    item
                    for item in self._statuses(repository, reviewed_head_sha)
                    if item.get("context") == evidence_ref.name
                    and item.get("sha") == reviewed_head_sha
                ]
                if len(candidates) != 1:
                    state = "unavailable" if not candidates else "ambiguous"
                    return HeadEvidenceResult(
                        repository,
                        pull_request_number,
                        HEAD_POLICY,
                        None,
                        reviewed_head_sha,
                        "unknown",
                        evidence_ref.provider,
                        "github",
                        None,
                        _now(),
                        state,
                        "EVIDENCE_UNAVAILABLE",
                    )
                item = candidates[0]
                conclusion = str(item.get("state", "unknown")).lower()
                producer = _producer(item)
                run_id = _run_id(item)
                state = (
                    "verified"
                    if conclusion == "success" and producer != "unknown" and run_id
                    else "unavailable"
                )
                result = HeadEvidenceResult(
                    repository,
                    pull_request_number,
                    HEAD_POLICY,
                    reviewed_head_sha,
                    reviewed_head_sha,
                    conclusion,
                    evidence_ref.provider,
                    producer if producer != "unknown" else "github",
                    run_id,
                    _timestamp(item.get("updated_at")),
                    state,
                    None if state == "verified" else "PRODUCER_UNAVAILABLE",
                )
            return result
        except LiveEvidenceError as exc:
            return HeadEvidenceResult(
                repository,
                pull_request_number,
                HEAD_POLICY,
                None,
                reviewed_head_sha,
                "unknown",
                evidence_ref.provider,
                "github",
                None,
                _now(),
                "unavailable",
                exc.code,
            )

    def resolve_integration(
        self,
        *,
        repository: str,
        pull_request_number: int,
        reviewed_head_sha: str,
        current_base_sha: str,
        integration_sha: str | None,
    ) -> IntegrationEvidenceResult:
        if not integration_sha:
            return IntegrationEvidenceResult(
                repository,
                pull_request_number,
                MERGE_POLICY,
                None,
                "0" * 40,
                reviewed_head_sha,
                current_base_sha,
                "unknown",
                "github_check",
                "github",
                None,
                _now(),
                "unavailable",
                "INTEGRATION_IDENTITY_UNAVAILABLE",
            )
        try:
            pr = self.client.get(f"/repos/{repository}/pulls/{pull_request_number}")
            if (
                not isinstance(pr, Mapping)
                or pr.get("head", {}).get("sha") != reviewed_head_sha
                or pr.get("base", {}).get("sha") != current_base_sha
            ):
                return IntegrationEvidenceResult(
                    repository,
                    pull_request_number,
                    MERGE_POLICY,
                    None,
                    integration_sha,
                    reviewed_head_sha,
                    current_base_sha,
                    "unknown",
                    "github_check",
                    "github",
                    None,
                    _now(),
                    "mismatched",
                    "EVIDENCE_SHA_MISMATCH",
                )
            candidates = [
                item
                for item in self._checks(repository, integration_sha)
                if item.get("name") == MERGE_POLICY and item.get("head_sha") == integration_sha
            ]
            if len(candidates) != 1:
                state = "unavailable" if not candidates else "ambiguous"
                return IntegrationEvidenceResult(
                    repository,
                    pull_request_number,
                    MERGE_POLICY,
                    None,
                    integration_sha,
                    reviewed_head_sha,
                    current_base_sha,
                    "unknown",
                    "github_check",
                    "github",
                    None,
                    _now(),
                    state,
                    "EVIDENCE_UNAVAILABLE",
                )
            item = candidates[0]
            conclusion = str(item.get("conclusion") or item.get("status") or "unknown").lower()
            producer = _producer(item)
            run_id = _run_id(item)
            state = (
                "verified"
                if conclusion == "success" and producer != "unknown" and run_id
                else "unavailable"
            )
            return IntegrationEvidenceResult(
                repository,
                pull_request_number,
                MERGE_POLICY,
                integration_sha,
                integration_sha,
                reviewed_head_sha,
                current_base_sha,
                conclusion,
                "github_check",
                producer if producer != "unknown" else "github",
                run_id,
                _timestamp(item.get("completed_at") or item.get("started_at")),
                state,
                None if state == "verified" else "PRODUCER_UNAVAILABLE",
            )
        except LiveEvidenceError as exc:
            return IntegrationEvidenceResult(
                repository,
                pull_request_number,
                MERGE_POLICY,
                None,
                integration_sha,
                reviewed_head_sha,
                current_base_sha,
                "unknown",
                "github_check",
                "github",
                None,
                _now(),
                "unavailable",
                exc.code,
            )
