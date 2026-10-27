from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from aura_core.enterprise.approval_store import (
    ApprovalConflict,
    ApprovalExpired,
    ApprovalStatus,
    InvalidApprovalTransition,
    SQLiteApprovalStore,
)


FINGERPRINT = "a" * 64
POLICY_DIGEST = "b" * 64


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def create_pending(store: SQLiteApprovalStore, **overrides):
    values = {
        "approval_id": "approval-1",
        "principal_id": "local-user",
        "capability_id": "filesystem.read_test_data",
        "operation_id": "read",
        "resource_scope": "test-data/governor-read-test.txt",
        "request_fingerprint": FINGERPRINT,
        "policy_digest": POLICY_DIGEST,
        "ttl_seconds": 60,
    }
    values.update(overrides)
    return store.create(**values)


def approve(store: SQLiteApprovalStore, record):
    return store.decide(
        record.approval_id,
        expected_version=record.version,
        approver_id="operator-1",
        decision=ApprovalStatus.APPROVED,
    )


def consume(store: SQLiteApprovalStore, record, **overrides):
    values = {
        "expected_version": record.version,
        "principal_id": record.principal_id,
        "capability_id": record.capability_id,
        "operation_id": record.operation_id,
        "resource_scope": record.resource_scope,
        "request_fingerprint": record.request_fingerprint,
        "policy_digest": record.policy_digest,
    }
    values.update(overrides)
    return store.consume(record.approval_id, **values)


def test_create_pending_record_and_persist_across_reopen(tmp_path):
    path = str(tmp_path / "approvals.sqlite3")
    clock = FakeClock()
    store = SQLiteApprovalStore(path, clock=clock)
    record = create_pending(store)

    assert record.status is ApprovalStatus.PENDING
    assert record.version == 1
    assert record.principal_id == "local-user"
    assert record.requested_at == "2026-10-27T12:00:00.000000+00:00"
    assert record.expires_at == "2026-10-27T12:01:00.000000+00:00"
    assert record.approver_id is None
    store.close()

    reopened = SQLiteApprovalStore(path, clock=clock)
    assert reopened.get(record.approval_id) == record
    reopened.close()


def test_approval_can_be_consumed_once_and_is_bound_to_request(tmp_path):
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=FakeClock())
    pending = create_pending(store)
    approved = approve(store, pending)

    assert approved.status is ApprovalStatus.APPROVED
    assert approved.version == 2
    assert approved.approver_id == "operator-1"
    assert approved.decided_at is not None

    consumed = consume(store, approved)
    assert consumed.status is ApprovalStatus.CONSUMED
    assert consumed.version == 3
    assert consumed.consumed_at is not None

    with pytest.raises(InvalidApprovalTransition, match="APPROVED"):
        consume(store, consumed)
    store.close()


@pytest.mark.parametrize(
    "override",
    [
        {"principal_id": "other-user"},
        {"capability_id": "filesystem.write"},
        {"operation_id": "write"},
        {"resource_scope": "test-data/other.txt"},
        {"request_fingerprint": "c" * 64},
        {"policy_digest": "d" * 64},
    ],
)
def test_consume_rejects_mismatched_request_or_policy(tmp_path, override):
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=FakeClock())
    approved = approve(store, create_pending(store))

    with pytest.raises(ApprovalConflict, match="does not match"):
        consume(store, approved, **override)

    # A failed match must not burn the approval or change its version.
    current = store.get(approved.approval_id)
    assert current.status is ApprovalStatus.APPROVED
    assert current.version == approved.version
    store.close()


def test_optimistic_concurrency_rejects_stale_decision(tmp_path):
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=FakeClock())
    pending = create_pending(store)
    approved = approve(store, pending)

    with pytest.raises(ApprovalConflict, match="version changed"):
        store.decide(
            pending.approval_id,
            expected_version=pending.version,
            approver_id="operator-2",
            decision=ApprovalStatus.DENIED,
        )

    assert store.get(pending.approval_id) == approved
    store.close()


def test_expired_pending_approval_is_persistently_expired_on_decision(tmp_path):
    clock = FakeClock()
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=clock)
    pending = create_pending(store)
    clock.advance(61)

    with pytest.raises(ApprovalExpired):
        store.decide(
            pending.approval_id,
            expected_version=pending.version,
            approver_id="operator-1",
            decision=ApprovalStatus.APPROVED,
        )

    expired = store.get(pending.approval_id)
    assert expired.status is ApprovalStatus.EXPIRED
    assert expired.version == 2
    store.close()


def test_expired_approved_record_cannot_be_consumed(tmp_path):
    clock = FakeClock()
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=clock)
    approved = approve(store, create_pending(store))
    clock.advance(61)

    with pytest.raises(ApprovalExpired):
        consume(store, approved)

    expired = store.get(approved.approval_id)
    assert expired.status is ApprovalStatus.EXPIRED
    assert expired.version == 3
    store.close()


def test_approved_record_can_be_revoked_but_not_consumed_afterward(tmp_path):
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=FakeClock())
    approved = approve(store, create_pending(store))
    revoked = store.revoke(
        approved.approval_id,
        expected_version=approved.version,
        revoked_by="operator-2",
    )

    assert revoked.status is ApprovalStatus.REVOKED
    assert revoked.version == 3
    assert revoked.revoked_by == "operator-2"
    assert revoked.revoked_at is not None
    with pytest.raises(InvalidApprovalTransition):
        consume(store, revoked)
    store.close()


def test_two_connections_can_consume_only_once(tmp_path):
    path = str(tmp_path / "approvals.sqlite3")
    clock = FakeClock()
    writer = SQLiteApprovalStore(path, clock=clock)
    approved = approve(writer, create_pending(writer))
    contender_a = SQLiteApprovalStore(path, clock=clock)
    contender_b = SQLiteApprovalStore(path, clock=clock)
    barrier = threading.Barrier(2)
    outcomes = []
    outcomes_lock = threading.Lock()

    def attempt(store):
        barrier.wait()
        try:
            result = consume(store, approved)
            outcome = ("consumed", result.status)
        except (ApprovalConflict, InvalidApprovalTransition) as exc:
            outcome = ("rejected", type(exc))
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=attempt, args=(contender_a,)),
        threading.Thread(target=attempt, args=(contender_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert sum(outcome[0] == "consumed" for outcome in outcomes) == 1
    assert sum(outcome[0] == "rejected" for outcome in outcomes) == 1
    assert writer.get(approved.approval_id).status is ApprovalStatus.CONSUMED

    contender_a.close()
    contender_b.close()
    writer.close()


def test_schema_stores_only_allowlisted_metadata_not_raw_payloads(tmp_path):
    path = str(tmp_path / "approvals.sqlite3")
    store = SQLiteApprovalStore(path, clock=FakeClock())
    create_pending(store)
    columns = {
        row["name"]
        for row in store._connection.execute("PRAGMA table_info(approvals)").fetchall()
    }
    assert columns == {
        "approval_id", "principal_id", "capability_id", "operation_id", "resource_scope",
        "request_fingerprint", "policy_digest", "status", "version", "requested_at",
        "expires_at", "approver_id", "decided_at", "consumed_at", "revoked_by", "revoked_at",
    }
    store.close()

    with sqlite3.connect(path) as connection:
        raw_schema = " ".join(row[0] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table'"
        ))
    assert "tool_arguments" not in raw_schema
    assert "provider_response" not in raw_schema
    assert "prompt" not in raw_schema.lower()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"request_fingerprint": "not-a-digest"},
        {"policy_digest": "g" * 64},
        {"ttl_seconds": 0},
        {"ttl_seconds": 30 * 24 * 60 * 60 + 1},
        {"ttl_seconds": True},
    ],
)
def test_create_rejects_invalid_digest_or_ttl(tmp_path, kwargs):
    store = SQLiteApprovalStore(str(tmp_path / "approvals.sqlite3"), clock=FakeClock())
    values = {
        "principal_id": "local-user",
        "capability_id": "filesystem.read_test_data",
        "operation_id": "read",
        "resource_scope": "test-data/governor-read-test.txt",
        "request_fingerprint": FINGERPRINT,
        "policy_digest": POLICY_DIGEST,
        "ttl_seconds": 60,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        store.create(**values)
    store.close()
