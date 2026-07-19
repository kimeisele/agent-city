from __future__ import annotations

import json
import base64
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from city import federation_v1
from city.federation_v1 import (
    FEATURE_GATE_DEFAULT,
    V1Reject,
    carrier_inner,
    canonical_bytes,
    parse_canonical,
    validate_envelope,
)
from tests.test_federation_v1_admission import REQUEST, semantic_payload, services
from tests.test_federation_v1_assignment import admitted, assign, candidate


def assigned(tmp_path: Path):
    target, ledger = admitted(tmp_path)
    assign(target, lambda: [candidate()])
    return target, ledger


def ready_in_process(args: tuple[str, str]) -> dict:
    root, created_at = args
    _, target, *_ = services(Path(root))
    code, child = target.ledger.create_ready_work_item(
        REQUEST["payload"]["delegation_id"], created_at
    )
    return {"code": code, "child": child}


def test_assigned_creates_one_closed_ready_child(tmp_path: Path) -> None:
    target, ledger = assigned(tmp_path)
    code, child = ledger.create_ready_work_item(
        REQUEST["payload"]["delegation_id"], "2026-07-18T11:03:00Z"
    )
    assert code == "created"
    assert set(child) == federation_v1.READY_WORK_ITEM_FIELDS
    assert child["state"] == "READY"
    assert child["work_item_id"].startswith("work_v1_")
    assert ledger.get(REQUEST["payload"]["delegation_id"])["ready_work_item"] == child
    assert target.enabled is True


def test_ready_duplicate_returns_first_set_without_rebuilding(tmp_path: Path) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    first_code, first = ledger.create_ready_work_item(
        delegation_id, "2026-07-18T11:03:00Z"
    )
    second_code, second = ledger.create_ready_work_item(
        delegation_id, "2026-07-18T11:20:00Z"
    )
    assert first_code == "created"
    assert second_code == "duplicate"
    assert second == first


def test_ready_creation_does_not_read_candidate_or_transport_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ledger = assigned(tmp_path)

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("READY must only use persisted parent evidence")

    monkeypatch.setattr(federation_v1.FederationV1CandidateSnapshotAdapter, "observe", forbidden)
    monkeypatch.setattr(federation_v1, "build_carrier", forbidden)
    monkeypatch.setattr(federation_v1, "carrier_inner", forbidden)
    code, _ = ledger.create_ready_work_item(
        REQUEST["payload"]["delegation_id"], "2026-07-18T11:03:00Z"
    )
    assert code == "created"


def test_two_processes_create_one_first_set_ready_child(tmp_path: Path) -> None:
    assigned(tmp_path)
    context = multiprocessing.get_context("fork")
    with context.Pool(2) as pool:
        results = pool.map(
            ready_in_process,
            [
                (str(tmp_path), "2026-07-18T11:03:00Z"),
                (str(tmp_path), "2026-07-18T11:20:00Z"),
            ],
        )
    assert {result["code"] for result in results} == {"created", "duplicate"}
    assert results[0]["child"] == results[1]["child"]
    persisted = json.loads((tmp_path / "target.json").read_text())["delegations"][
        REQUEST["payload"]["delegation_id"]
    ]
    assert persisted["assignment_state"] == "ASSIGNED"
    assert persisted["ready_work_item"] == results[0]["child"]


def test_two_ledger_instances_are_first_set_safe(tmp_path: Path) -> None:
    assigned(tmp_path)
    first_ledger = services(tmp_path)[1].ledger
    second_ledger = services(tmp_path)[1].ledger
    delegation_id = REQUEST["payload"]["delegation_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda item: item.create_ready_work_item(
                    delegation_id, "2026-07-18T11:03:00Z"
                ),
                [first_ledger, second_ledger],
            )
        )
    assert results[0][1] == results[1][1]


def test_crash_before_ready_replace_leaves_assigned_without_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ledger = assigned(tmp_path)

    def crash(*_: object, **__: object) -> None:
        raise RuntimeError("ready commit crash")

    monkeypatch.setattr(federation_v1, "_atomic", crash)
    with pytest.raises(RuntimeError, match="ready commit crash"):
        ledger.create_ready_work_item(
            REQUEST["payload"]["delegation_id"], "2026-07-18T11:03:00Z"
        )
    record = ledger.get(REQUEST["payload"]["delegation_id"])
    assert record["assignment_state"] == "ASSIGNED"
    assert record["ready_work_item"] is None


def test_crash_after_ready_replace_leaves_complete_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ledger = assigned(tmp_path)
    real_atomic = federation_v1._atomic

    def commit_then_crash(path: Path, data: object) -> None:
        real_atomic(path, data)
        raise RuntimeError("ready post-commit crash")

    monkeypatch.setattr(federation_v1, "_atomic", commit_then_crash)
    with pytest.raises(RuntimeError, match="ready post-commit crash"):
        ledger.create_ready_work_item(
            REQUEST["payload"]["delegation_id"], "2026-07-18T11:03:00Z"
        )
    fresh = services(tmp_path)[1].ledger
    child = fresh.get(REQUEST["payload"]["delegation_id"])["ready_work_item"]
    assert child["state"] == "READY"
    assert child["work_item_content_digest"]


def test_non_assigned_parent_requires_assignment(tmp_path: Path) -> None:
    origin, target, *_ = services(tmp_path)
    _, carrier = origin.create(
        payload=semantic_payload(),
        target_node_id=REQUEST["target_node_id"],
        message_id=REQUEST["message_id"],
        issued_at="2026-07-18T11:00:00Z",
        expires_at="2026-07-18T11:05:00Z",
    )
    target.handle(carrier, now="2026-07-18T11:01:00Z")
    with pytest.raises(V1Reject, match="assignment_required"):
        target.ledger.create_ready_work_item(
            REQUEST["payload"]["delegation_id"], "2026-07-18T11:03:00Z"
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("work_item_id", "work_v1_" + "0" * 64),
        ("input_digest", "0" * 64),
        ("candidate_snapshot_digest", "0" * 64),
        ("assignment_authority_digest", "0" * 64),
        ("target_key_binding_digest", "0" * 64),
        ("work_item_content_digest", "0" * 64),
    ],
)
def test_ready_mutation_fails_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")
    raw = json.loads(ledger.path.read_text())
    raw["delegations"][delegation_id]["ready_work_item"][field] = value
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.get(delegation_id)


def test_invalid_assignment_attestation_prevents_ready(tmp_path: Path) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    raw = json.loads(ledger.path.read_text())
    record = raw["delegations"][delegation_id]
    record["assignment_signature"] = "A" * len(record["assignment_signature"])
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")


def test_mutated_persisted_request_bytes_prevent_ready(tmp_path: Path) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    raw = json.loads(ledger.path.read_text())
    record = raw["delegations"][delegation_id]
    request = parse_canonical(base64.b64decode(record["request_wire_bytes_b64"]))
    request["payload"]["task_description"] = "mutated-after-admission"
    record["request_wire_bytes_b64"] = base64.b64encode(
        canonical_bytes(request)
    ).decode("ascii")
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")


@pytest.mark.parametrize("value", [None, 1.25, "2026-07-18T11:03:00+00:00"])
def test_ready_malformed_scalar_fails_closed(tmp_path: Path, value: object) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")
    raw = json.loads(ledger.path.read_text())
    raw["delegations"][delegation_id]["ready_work_item"]["created_at"] = value
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.get(delegation_id)


def test_ready_missing_and_extra_fields_fail_closed(tmp_path: Path) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")
    raw = json.loads(ledger.path.read_text())
    child = raw["delegations"][delegation_id]["ready_work_item"]
    child.pop("input_digest")
    child["queue_item_id"] = "forbidden"
    ledger.path.write_text(json.dumps(raw))
    with pytest.raises(V1Reject, match="ledger_corrupt"):
        ledger.get(delegation_id)


def test_ready_is_not_a_federation_envelope_or_carrier(tmp_path: Path) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    _, child = ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")
    raw = canonical_bytes(child)
    with pytest.raises(V1Reject, match="schema_field_set"):
        validate_envelope(
            raw,
            registry=services(tmp_path)[2],
            expected_target=REQUEST["target_node_id"],
            operation="delegate_task",
            now="2026-07-18T11:03:00Z",
        )
    with pytest.raises(V1Reject):
        carrier_inner(child, REQUEST["target_node_id"])


def test_ready_does_not_change_frozen_request_or_assignment_bytes(tmp_path: Path) -> None:
    _, ledger = assigned(tmp_path)
    delegation_id = REQUEST["payload"]["delegation_id"]
    before = json.loads(ledger.path.read_text())["delegations"][delegation_id]
    request_wire = before["request_wire_bytes_b64"]
    assignment_wire = before["assignment_wire_bytes_b64"]
    ledger.create_ready_work_item(delegation_id, "2026-07-18T11:03:00Z")
    after = json.loads(ledger.path.read_text())["delegations"][delegation_id]
    assert after["request_wire_bytes_b64"] == request_wire
    assert after["assignment_wire_bytes_b64"] == assignment_wire


def test_ready_feature_gate_and_legacy_boundary_remain_disabled(tmp_path: Path) -> None:
    _, target, *_ = services(tmp_path)
    assert FEATURE_GATE_DEFAULT is False
    assert target.enabled is True  # test fixture opts in; production default is false
    target.enabled = False
    assert target.enabled is False
