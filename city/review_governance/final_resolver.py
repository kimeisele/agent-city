"""Concrete production final-state composition for B1-S3B."""

from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Protocol

from .council import CouncilGateB1
from .evidence import (
    HEAD_POLICY,
    MERGE_POLICY,
    EvidenceProducerTrust,
    EvidenceReferenceVerifier,
    HeadEvidenceProvider,
    IntegrationEvidenceProvider,
    head_evidence_digest,
    integration_evidence_digest,
)
from .github_snapshot import GitHubSnapshotResolver, SnapshotError
from .ledger import LedgerError, ShadowLedger
from .merge_authority import FinalMergeSnapshotB1, MergeAuthorityError
from .request import ReviewRequestB1
from .schema import MergeReadinessEvaluationB1, ReviewVerdictB1
from .validator import validate_verdict


class CouncilStateProvider(Protocol):
    def resolve(
        self, *, repository: str, pull_request_number: int, reviewed_head_sha: str
    ) -> CouncilGateB1: ...


class FinalResolverError(MergeAuthorityError):
    pass


class GitHubFinalMergeStateResolver:
    """Resolve every final merge predicate from trusted read boundaries."""

    def __init__(
        self,
        *,
        request: ReviewRequestB1,
        verdict: ReviewVerdictB1,
        evaluation: MergeReadinessEvaluationB1,
        verifier: Any,
        snapshot_resolver: GitHubSnapshotResolver,
        head_evidence_provider: HeadEvidenceProvider,
        integration_evidence_provider: IntegrationEvidenceProvider,
        producer_trust: EvidenceProducerTrust,
        council_provider: CouncilStateProvider,
        ledger: ShadowLedger,
        consumer_core_classifier: Callable[[str], str],
        allow_closed: bool = True,
    ):
        self.request = request
        self.verdict = verdict
        self.evaluation = evaluation
        self.verifier = verifier
        self.snapshot_resolver = snapshot_resolver
        self.head_provider = head_evidence_provider
        self.integration_provider = integration_evidence_provider
        self.producer_trust = producer_trust
        self.council_provider = council_provider
        self.ledger = ledger
        self.consumer_core_classifier = consumer_core_classifier
        self.allow_closed = allow_closed

    def _fail(self, code: str) -> None:
        raise FinalResolverError(code)

    def resolve(self) -> FinalMergeSnapshotB1:
        try:
            snapshot = self.snapshot_resolver.resolve(
                repository=self.request.repository,
                pull_request_number=self.request.pull_request_number,
                allow_closed=self.allow_closed,
            )
        except (SnapshotError, LedgerError) as exc:
            raise FinalResolverError(getattr(exc, "code", "SNAPSHOT_UNAVAILABLE")) from exc
        if (
            snapshot.repository != self.request.repository
            or snapshot.pull_request_number != self.request.pull_request_number
        ):
            self._fail("PR_IDENTITY_CHANGED")
        if (
            self.verdict.repository != self.request.repository
            or self.verdict.pull_request_number != self.request.pull_request_number
            or self.verdict.reviewed_head_sha != self.request.reviewed_head_sha
            or self.verdict.review_request_base_sha != self.request.review_request_base_sha
            or self.verdict.scope_digest != self.request.scope_digest
            or self.verdict.reviewed_files != self.request.reviewed_files
        ):
            self._fail("REQUEST_LINEAGE_MISMATCH")
        if self.verdict.review_request_id != self.request.review_request_id:
            self._fail("REQUEST_LINEAGE_MISMATCH")
        if self.evaluation.verdict_id != self.verdict.verdict_id:
            self._fail("EVALUATION_VERDICT_MISMATCH")
        refs = tuple(
            ref
            for ref in self.verdict.evidence_refs
            if ref.kind == "head_security_evidence" and ref.name == HEAD_POLICY
        )
        if len(refs) != 1 or refs[0].sha != snapshot.current_head_sha:
            self._fail("EVIDENCE_REFERENCE_UNAVAILABLE")
        head_ref = refs[0]
        head = self.head_provider.resolve(
            repository=self.request.repository,
            pull_request_number=self.request.pull_request_number,
            reviewed_head_sha=snapshot.current_head_sha,
            evidence_ref=head_ref,
        )
        if (
            head.state != "verified"
            or head.repository != self.request.repository
            or head.pull_request_number != self.request.pull_request_number
            or head.observed_sha != snapshot.current_head_sha
            or head.provider != head_ref.provider
            or head.policy_name != HEAD_POLICY
            or head_evidence_digest(head) != head_ref.evidence_digest
            or not self.producer_trust.is_trusted(
                repository=self.request.repository,
                policy_name=HEAD_POLICY,
                provider=head.provider,
                producer_identity=head.producer_identity,
            )
        ):
            self._fail("HEAD_EVIDENCE_INVALID")
        verification = validate_verdict(
            self.verdict.to_mapping(),
            repository=self.request.repository,
            verifier=self.verifier,
            evidence_verifier=EvidenceReferenceVerifier(((head_ref, head),)),
            scope_entries=[dict(item) for item in self.request.scope_entries],
            consumer_core="core" if self.verdict.core_classification == "core" else "non_core",
            current_head_sha=snapshot.current_head_sha,
            expected_evidence_policy=HEAD_POLICY,
            now=dt.datetime.strptime(snapshot.observed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.UTC
            ),
        )
        if verification.state != "valid":
            self._fail(verification.error_code or "VERDICT_NOT_USABLE")
        integration = self.integration_provider.resolve(
            repository=self.request.repository,
            pull_request_number=self.request.pull_request_number,
            reviewed_head_sha=snapshot.current_head_sha,
            current_base_sha=snapshot.current_base_sha,
            integration_sha=snapshot.integration_identity,
        )
        required = tuple(
            check
            for check in self.evaluation.required_check_results
            if check["name"] == MERGE_POLICY and check["head_sha"] == snapshot.integration_identity
        )
        try:
            readiness_record = self.ledger.latest_readiness_record(
                repository=self.request.repository,
                pull_request_number=self.request.pull_request_number,
                reviewed_head_sha=self.request.reviewed_head_sha,
                evaluation_id=self.evaluation.evaluation_id,
            )
        except LedgerError as exc:
            raise FinalResolverError(exc.code) from exc
        expected_integration_digest = readiness_record.get("integration_evidence_identity")
        expected_head_digest = readiness_record.get("head_evidence_identity")
        if (
            len(required) != 1
            or integration.state != "verified"
            or integration.repository != self.request.repository
            or integration.pull_request_number != self.request.pull_request_number
            or integration.source_head_sha != snapshot.current_head_sha
            or integration.source_base_sha != snapshot.current_base_sha
            or integration.observed_sha != snapshot.integration_identity
            or integration.run_or_check_identity != required[0]["run_id"]
            or not isinstance(expected_integration_digest, str)
            or integration_evidence_digest(integration) != expected_integration_digest
            or not isinstance(expected_head_digest, str)
            or head_ref.evidence_digest != expected_head_digest
            or not self.producer_trust.is_trusted(
                repository=self.request.repository,
                policy_name=MERGE_POLICY,
                provider=integration.provider,
                producer_identity=integration.producer_identity,
            )
        ):
            self._fail("INTEGRATION_EVIDENCE_INVALID")
        effective_core = self.verdict.core_classification == "core"
        council = (
            self.council_provider.resolve(
                repository=self.request.repository,
                pull_request_number=self.request.pull_request_number,
                reviewed_head_sha=snapshot.current_head_sha,
            )
            if effective_core
            else CouncilGateB1(
                self.request.repository,
                self.request.pull_request_number,
                snapshot.current_head_sha,
                "not_required",
            )
        )
        if effective_core and council.state != "approved":
            self._fail("COUNCIL_REQUIRED")
        try:
            latest, invalidated, ledger_head = self.ledger.readiness_lineage(
                repository=self.request.repository,
                pull_request_number=self.request.pull_request_number,
                reviewed_head_sha=snapshot.current_head_sha,
                evaluation_id=self.evaluation.evaluation_id,
            )
        except LedgerError as exc:
            raise FinalResolverError(exc.code) from exc
        return FinalMergeSnapshotB1(
            self.request.repository,
            self.request.pull_request_number,
            snapshot.current_head_sha,
            snapshot.current_base_sha,
            snapshot.integration_identity,
            snapshot.pr_state,
            snapshot.mergeability_state,
            head.state,
            head_ref.evidence_digest,
            integration.state,
            integration_evidence_digest(integration),
            council.state,
            latest,
            invalidated,
            ledger_head,
            snapshot.merged,
            snapshot.final_merge_sha,
            snapshot.observed_at,
            snapshot.merged_by,
            snapshot.merged_at,
        )
