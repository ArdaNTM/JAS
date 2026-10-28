"""Real-service checks for remote persistence adapters and S3-compatible storage.

These tests deliberately do not enable AURA_STORAGE_MODE=remote: production
composition still has SQLite task-state/checkpoint paths, so the fail-closed
gate must remain in place until those interfaces are migrated too.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from uuid import uuid4

import pytest

from aura_core.application.postgresql_episodic_memory import PostgreSQLEpisodicMemoryStore
from aura_core.config.storage import validate_storage_mode
from aura_core.enterprise.approval_store import ApprovalStatus
from aura_core.enterprise.postgresql_approval_store import PostgreSQLApprovalStore
from aura_core.enterprise.postgresql_workflow_store import PostgreSQLWorkflowStore
from aura_core.enterprise.workflow_store import WorkflowStatus

DATABASE_URL = os.environ.get("AURA_TEST_DATABASE_URL")


def test_postgresql_stores_enforce_scope_lifecycle_and_one_time_approval():
    if not DATABASE_URL:
        pytest.skip("requires AURA_TEST_DATABASE_URL and a running PostgreSQL service")
    async def scenario():
        suffix = uuid4().hex
        principal = f"ci-principal-{suffix}"
        other_principal = f"ci-other-{suffix}"
        task_id = f"ci-task-{suffix}"
        workflow = PostgreSQLWorkflowStore(DATABASE_URL)
        approvals = PostgreSQLApprovalStore(DATABASE_URL)
        memory = PostgreSQLEpisodicMemoryStore(DATABASE_URL)
        try:
            await workflow.initialize()
            await approvals.initialize()
            await memory.initialize()
            created = await workflow.create(workflow_id=task_id, idempotency_key=f"ci-idempotency-{suffix}", principal_id=principal, task_id=task_id)
            running = await workflow.transition(task_id, expected_version=created.version, target=WorkflowStatus.RUNNING)
            succeeded = await workflow.transition(task_id, expected_version=running.version, target=WorkflowStatus.SUCCEEDED)
            assert succeeded.status is WorkflowStatus.SUCCEEDED
            assert (await workflow.get(task_id)).principal_id == principal

            remembered = await memory.remember(principal_id=principal, kind="episode", content=f"private remote memory marker {suffix}", tags=["ci", "remote"], source_task_id=task_id, importance=4)
            assert remembered.principal_id == principal
            assert await memory.count(principal_id=principal) >= 1
            assert await memory.count(principal_id=other_principal) == 0
            assert await memory.recall(principal_id=other_principal, query=suffix) == []

            fingerprint = hashlib.sha256(f"fingerprint-{suffix}".encode()).hexdigest()
            policy_digest = hashlib.sha256(f"policy-{suffix}".encode()).hexdigest()
            approval = await approvals.create(principal_id=principal, capability_id="research.fetch", operation_id="research.fetch", resource_scope=f"ci:{suffix}", request_fingerprint=fingerprint, policy_digest=policy_digest, approval_id=f"ci-approval-{suffix}")
            approved = await approvals.decide(approval.approval_id, expected_version=approval.version, approver_id=principal, decision=ApprovalStatus.APPROVED)
            consumed = await approvals.consume(approved.approval_id, expected_version=approved.version, principal_id=principal, capability_id="research.fetch", operation_id="research.fetch", resource_scope=f"ci:{suffix}", request_fingerprint=fingerprint, policy_digest=policy_digest)
            assert consumed.status is ApprovalStatus.CONSUMED
            with pytest.raises(Exception):
                await approvals.consume(approved.approval_id, expected_version=consumed.version, principal_id=principal, capability_id="research.fetch", operation_id="research.fetch", resource_scope=f"ci:{suffix}", request_fingerprint=fingerprint, policy_digest=policy_digest)
        finally:
            await memory.close()
            await approvals.close()
            await workflow.close()
    asyncio.run(scenario())


def test_minio_s3_compatible_service_round_trip_and_delete():
    minio = pytest.importorskip("minio")
    from minio import Minio
    from io import BytesIO

    client = Minio(os.environ.get("AURA_TEST_S3_ENDPOINT", "127.0.0.1:4566"), access_key=os.environ.get("AURA_TEST_S3_ACCESS_KEY", "test"), secret_key=os.environ.get("AURA_TEST_S3_SECRET_KEY", "minioadmin"), secure=False)
    bucket = f"aura-ci-{uuid4().hex[:20]}"
    payload = f"remote-object-{uuid4().hex}".encode()
    key = "integration/checkpoint.bin"
    try:
        client.make_bucket(bucket)
        client.put_object(bucket, key, BytesIO(payload), length=len(payload))
        result = client.get_object(bucket, key)
        try:
            assert result.read() == payload
        finally:
            result.close()
            result.release_conn()
        client.remove_object(bucket, key)
        assert not any(obj.object_name == key for obj in client.list_objects(bucket))
    finally:
        if client.bucket_exists(bucket):
            for obj in client.list_objects(bucket, recursive=True):
                client.remove_object(bucket, obj.object_name)
            client.remove_bucket(bucket)


def test_remote_mode_remains_fail_closed_until_every_production_path_is_remote(monkeypatch):
    monkeypatch.setenv("AURA_STORAGE_MODE", "remote")
    monkeypatch.setenv("AURA_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ENDPOINT", "https://objects.example.invalid")
    with pytest.raises(RuntimeError, match="Startup is blocked"):
        validate_storage_mode()
