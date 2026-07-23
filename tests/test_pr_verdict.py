"""Containment tests for the legacy federation PR verdict hook."""

from __future__ import annotations

from unittest.mock import MagicMock

from city.hooks.dharma import pr_verdict as verdict_module
from city.hooks.dharma.pr_verdict import PRVerdictHook


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.offline_mode = False
    ctx.federation_nadi = MagicMock()
    ctx.heartbeat_count = 7
    ctx.gateway_queue = []
    ctx.recent_events = []
    identity = MagicMock()
    identity.verify.return_value = True
    ctx.registry.get.side_effect = lambda name: identity if name == "identity" else None
    ctx.council = MagicMock()
    return ctx


def _message(
    *,
    verdict: str = "approve",
    touches_core: object = False,
    key: str = "trusted-key",
    identity: str = "steward",
) -> dict:
    payload = {
        "pr_number": 42,
        "verdict": verdict,
        "reason": "reviewed",
        "touches_core": touches_core,
    }
    return {
        "membrane": {"surface": "federation"},
        "federation_operation": "pr_review_verdict",
        "signature": "signature",
        "signer_key": key,
        "signer_identity": identity,
        "federation_payload": payload,
    }


def _trusted_config(monkeypatch) -> None:
    monkeypatch.setattr(
        verdict_module,
        "get_config",
        lambda: {
            "federation": {
                "trusted_steward": {
                    "identity": "steward",
                    "public_key": "trusted-key",
                }
            }
        },
    )


def test_attacker_supplied_key_is_not_self_authorizing(monkeypatch) -> None:
    _trusted_config(monkeypatch)
    ctx = _ctx()
    ctx.gateway_queue.append(_message(key="attacker-key"))
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:blocked:#42"]
    assert ctx.recent_events == []
    ctx.council.propose.assert_not_called()


def test_trusted_pinned_steward_is_audit_only(monkeypatch) -> None:
    _trusted_config(monkeypatch)
    ctx = _ctx()
    ctx.gateway_queue.append(_message(verdict="approve"))
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:audit_only:#42"]
    assert ctx.recent_events[0]["mutation"] == "none"
    ctx.council.propose.assert_not_called()


def test_missing_key_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(verdict_module, "get_config", lambda: {"federation": {}})
    ctx = _ctx()
    ctx.gateway_queue.append(_message())
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:blocked:#42"]
    assert ctx.recent_events == []


def test_malformed_pinned_configuration_does_not_fallback_to_environment(monkeypatch) -> None:
    monkeypatch.setenv("STEWARD_TRUSTED_IDENTITY", "steward")
    monkeypatch.setenv("STEWARD_TRUSTED_PUBLIC_KEY", "trusted-key")
    monkeypatch.setattr(
        verdict_module,
        "get_config",
        lambda: {"federation": {"trusted_steward": "malformed"}},
    )
    ctx = _ctx()
    ctx.gateway_queue.append(_message())
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:blocked:#42"]
    assert ctx.recent_events == []


def test_wrong_steward_identity_fails_closed(monkeypatch) -> None:
    _trusted_config(monkeypatch)
    ctx = _ctx()
    ctx.gateway_queue.append(_message(identity="other-agent"))
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:blocked:#42"]
    assert ctx.recent_events == []


def test_missing_touches_core_blocks_without_defaulting_false(monkeypatch) -> None:
    _trusted_config(monkeypatch)
    ctx = _ctx()
    message = _message()
    del message["federation_payload"]["touches_core"]
    ctx.gateway_queue.append(message)
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:blocked:#42"]
    assert ctx.recent_events == []


def test_reject_never_closes_or_creates_council_outcome(monkeypatch) -> None:
    _trusted_config(monkeypatch)
    ctx = _ctx()
    ctx.gateway_queue.append(_message(verdict="reject", touches_core=True))
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["pr_verdict:audit_only:#42"]
    assert ctx.recent_events[0]["mutation"] == "none"
    ctx.council.propose.assert_not_called()


def test_compliance_report_handling_is_preserved(monkeypatch) -> None:
    _trusted_config(monkeypatch)
    ctx = _ctx()
    ctx.gateway_queue.append(
        {
            "membrane": {"surface": "federation"},
            "federation_operation": "compliance_report",
            "federation_payload": {"status": "warning", "subject": "trust drift"},
        }
    )
    operations: list[str] = []

    PRVerdictHook().execute(ctx, operations)

    assert operations == ["compliance_report:warning:trust drift"]
    assert ctx._compliance_reports[0]["subject"] == "trust drift"
