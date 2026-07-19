from __future__ import annotations

import base64
import hashlib
import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from city.federation_v1 import (
    FEATURE_GATE_DEFAULT,
    V1Reject,
    canonical_bytes,
    parse_canonical,
)

from tests.test_federation_v1_admission import KEYS, REQUEST, semantic_payload, services


def candidate(candidate_id: str = "sys_alpha") -> dict:
    return {
        "candidate_id": candidate_id,
        "cartridge_id": "alpha",
        "capabilities": ["fix_repository", "read"],
        "capability_tier": "contributor",
        "domain": "engineering",
        "capability_protocol": "",
        "guardian": "",
        "active": True,
    }


def admitted(tmp_path: Path):
    origin, target, *rest = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    assert target.handle(carrier, now="2026-07-18T11:01:00Z") is not None
    return target, rest[-1]


def assign(target, source):
    return target.assign_candidate(
        REQUEST["payload"]["delegation_id"],
        candidate_source=source,
        observed_at="2026-07-18T11:02:00Z",
    )


def assign_in_fork(ledger_root: str) -> str:
    """Re-open the target from an independent process and assign once."""
    _, target, *_ = services(Path(ledger_root))
    return assign(target, lambda: [candidate()])[
        "assignment_wire_bytes_b64"
    ]


def test_acceptance_becomes_one_target_local_assigned_attestation(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    record = assign(target, lambda: [candidate()])

    assert record["state"] == "ACCEPTED"
    assert record["assignment_state"] == "ASSIGNED"
    assert record["assignment_epoch"] == 1
    assert record["target_work_id"]
    assert record["assigned_candidate_id"] == "sys_alpha"
    assert record["assignment_wire_bytes_b64"]
    raw = base64.b64decode(record["assignment_wire_bytes_b64"])
    attestation = parse_canonical(raw)
    assert "contract_version" not in attestation
    assert attestation["assignment_state"] == "ASSIGNED"
    assert attestation["target_work_id"] == record["target_work_id"]
    assert attestation["assignment_epoch"] == 1
    public = base64.b64decode(KEYS["target_signing_key"]["public_key_b64"])
    body = {
        key: value
        for key, value in attestation.items()
        if key not in {"assignment_message_hash", "assignment_signature"}
    }
    assert attestation["assignment_message_hash"] == hashlib.sha256(
        canonical_bytes(body)
    ).hexdigest()
    Ed25519PublicKey.from_public_bytes(public).verify(
        base64.b64decode(attestation["assignment_signature"]),
        b"STEWARD-FEDERATION-ASSIGNMENT-ATTESTATION-V1\x00"
        + bytes.fromhex(attestation["assignment_message_hash"]),
    )
    assert ledger.get(REQUEST["payload"]["delegation_id"])["assignment_state"] == "ASSIGNED"


def test_identical_duplicate_returns_byte_identical_local_evidence(tmp_path: Path) -> None:
    target, _ = admitted(tmp_path)

    def source():
        return [candidate()]

    first = assign(target, source)
    second = assign(target, source)
    assert second["assignment_wire_bytes_b64"] == first["assignment_wire_bytes_b64"]
    assert second["assignment_attestation_id"] == first["assignment_attestation_id"]
    assert second["assignment_epoch"] == 1


def test_changed_candidate_snapshot_is_assignment_conflict(tmp_path: Path) -> None:
    target, _ = admitted(tmp_path)
    assign(target, lambda: [candidate()])
    changed = candidate("sys_beta")
    with pytest.raises(V1Reject, match="assignment_conflict"):
        assign(target, lambda: [changed])


def test_changed_authority_binding_is_assignment_conflict(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    assign(target, lambda: [candidate()])
    raw = json.loads(ledger.path.read_text())
    authority = raw["delegations"][REQUEST["payload"]["delegation_id"]][
        "assignment_authority"
    ]["authority"]
    authority["allowed_actions"] = ["branch", "commit", "read"]
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="assignment_conflict"):
        assign(target, lambda: [candidate()])


@pytest.mark.parametrize("field", ["assignment_epoch", "target_work_id"])
def test_changed_persisted_assignment_binding_fails_closed(
    tmp_path: Path, field: str
) -> None:
    target, ledger = admitted(tmp_path)
    assign(target, lambda: [candidate()])
    raw = json.loads(ledger.path.read_text())
    record = raw["delegations"][REQUEST["payload"]["delegation_id"]]
    record[field] = 2 if field == "assignment_epoch" else "work_mutated"
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.get(REQUEST["payload"]["delegation_id"])


def test_source_generation_change_is_stale_before_commit(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    calls = 0

    def changing_source():
        nonlocal calls
        calls += 1
        value = candidate("sys_alpha" if calls == 1 else "sys_beta")
        return [value]

    with pytest.raises(V1Reject, match="candidate_snapshot_stale"):
        assign(target, changing_source)
    assert ledger.get(REQUEST["payload"]["delegation_id"])["assignment_state"] == "ACCEPTED"
    assert "assignment_wire_bytes_b64" not in json.loads(ledger.path.read_text())[
        "delegations"
    ][REQUEST["payload"]["delegation_id"]] or json.loads(ledger.path.read_text())[
        "delegations"
    ][REQUEST["payload"]["delegation_id"]]["assignment_wire_bytes_b64"] is None


def test_no_candidate_is_unavailable_without_attestation(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    with pytest.raises(V1Reject, match="assignment_unavailable"):
        assign(target, lambda: [candidate("sys_no_fix") | {"capabilities": ["read"]}])
    assert ledger.get(REQUEST["payload"]["delegation_id"])["assignment_state"] == "ACCEPTED"


def test_authority_mismatch_is_fail_closed(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    raw = json.loads(ledger.path.read_text())
    raw["delegations"][REQUEST["payload"]["delegation_id"]]["assignment_authority"][
        "authority"
    ]["denied_actions"] = []
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="authority_denied"):
        assign(target, lambda: [candidate()])
    assert ledger.get(REQUEST["payload"]["delegation_id"])["assignment_state"] == "ACCEPTED"


def test_corrupt_assignment_record_fails_closed(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    raw = json.loads(ledger.path.read_text())
    raw["delegations"][REQUEST["payload"]["delegation_id"]]["assignment_state"] = "ASSIGNED"
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.get(REQUEST["payload"]["delegation_id"])


def test_corrupt_assignment_attestation_fails_closed(tmp_path: Path) -> None:
    target, ledger = admitted(tmp_path)
    assign(target, lambda: [candidate()])
    raw = json.loads(ledger.path.read_text())
    record = raw["delegations"][REQUEST["payload"]["delegation_id"]]
    attestation = parse_canonical(base64.b64decode(record["assignment_wire_bytes_b64"]))
    attestation["assignment_signature"] = base64.b64encode(b"0" * 64).decode("ascii")
    record["assignment_wire_bytes_b64"] = base64.b64encode(
        canonical_bytes(attestation)
    ).decode("ascii")
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.get(REQUEST["payload"]["delegation_id"])


def test_two_process_safe_instances_create_one_assignment(tmp_path: Path) -> None:
    target, _ = admitted(tmp_path)
    ledger_path = target.ledger.path
    services_again = services(tmp_path)
    targets = [services_again[1], target]

    def source():
        return [candidate()]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda item: assign(item, source),
                targets,
            )
        )
    assert results[0]["assignment_wire_bytes_b64"] == results[1]["assignment_wire_bytes_b64"]
    persisted = json.loads(ledger_path.read_text())["delegations"][
        REQUEST["payload"]["delegation_id"]
    ]
    assert persisted["assignment_state"] == "ASSIGNED"
    assert persisted["assignment_epoch"] == 1


def test_two_independent_processes_create_one_assignment(tmp_path: Path) -> None:
    admitted(tmp_path)
    context = multiprocessing.get_context("fork")
    with context.Pool(2) as pool:
        results = pool.map(assign_in_fork, [str(tmp_path), str(tmp_path)])
    assert results[0] == results[1]
    persisted = json.loads((tmp_path / "target.json").read_text())["delegations"][
        REQUEST["payload"]["delegation_id"]
    ]
    assert persisted["assignment_state"] == "ASSIGNED"
    assert persisted["assignment_epoch"] == 1


def test_crash_before_assignment_commit_leaves_accepted_without_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, ledger = admitted(tmp_path)

    def crash_before_commit(*_: object, **__: object) -> None:
        raise RuntimeError("simulated assignment commit crash")

    monkeypatch.setattr("city.federation_v1._atomic", crash_before_commit)
    with pytest.raises(RuntimeError, match="assignment commit crash"):
        assign(target, lambda: [candidate()])
    record = ledger.get(REQUEST["payload"]["delegation_id"])
    assert record["assignment_state"] == "ACCEPTED"
    assert record["assignment_attestation_id"] is None
    assert record["assignment_wire_bytes_b64"] is None


def test_crash_after_assignment_commit_leaves_complete_assigned_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, ledger = admitted(tmp_path)
    import city.federation_v1 as federation_v1

    real_atomic = federation_v1._atomic

    def commit_then_crash(path: Path, data: object) -> None:
        real_atomic(path, data)
        raise RuntimeError("simulated post-commit crash")

    monkeypatch.setattr(federation_v1, "_atomic", commit_then_crash)
    with pytest.raises(RuntimeError, match="post-commit crash"):
        assign(target, lambda: [candidate()])
    record = ledger.get(REQUEST["payload"]["delegation_id"])
    assert record["assignment_state"] == "ASSIGNED"
    assert record["assignment_epoch"] == 1
    assert record["assignment_attestation_id"]
    assert record["assignment_wire_bytes_b64"]


def test_assignment_feature_gate_is_disabled_by_default(tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    assert FEATURE_GATE_DEFAULT is False
    assert target.enabled is True  # test fixture opts in explicitly
    target.enabled = False
    with pytest.raises(V1Reject, match="feature_disabled"):
        target.assign_candidate(
            REQUEST["payload"]["delegation_id"],
            candidate_source=lambda: [candidate()],
            observed_at="2026-07-18T11:02:00Z",
        )
    assert origin.enabled is True


def test_assignment_does_not_call_dispatch_or_execution_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import city.heal_executor as heal_executor
    import city.mission_router as mission_router

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("Slice 02 must not execute mission or heal work")

    monkeypatch.setattr(mission_router, "route_mission", forbidden)
    monkeypatch.setattr(heal_executor, "HealExecutor", forbidden)
    target, _ = admitted(tmp_path)
    record = assign(target, lambda: [candidate()])
    assert record["assignment_state"] == "ASSIGNED"
    assert "mission_id" not in record
    assert "queue_item_id" not in record
    assert "execution_result" not in record


def test_assignment_attestation_is_not_a_federation_receipt(tmp_path: Path) -> None:
    target, _ = admitted(tmp_path)
    record = assign(target, lambda: [candidate()])
    raw = base64.b64decode(record["assignment_wire_bytes_b64"])
    assert parse_canonical(raw)["assignment_attestation_version"] == (
        "federation-assignment-attestation-v1"
    )
    assert "operation" not in parse_canonical(raw)
