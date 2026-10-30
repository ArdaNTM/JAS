"""Real-service checks for remote persistence composition and S3-compatible storage."""
from __future__ import annotations

import asyncio
import hashlib
import os
from uuid import uuid4

import pytest

from aura_core.application.postgresql_episodic_memory import PostgreSQLEpisodicMemoryStore
from aura_core.application.postgresql_task_state_machine import PostgreSQLTaskStateMachine
from aura_core.application.task_state_machine import TaskState
from aura_core.memory.postgresql_hierarchical_memory import PostgreSQLHierarchicalMemory
from aura_core.application.postgresql_task_memory import PostgreSQLTaskMemoryCoordinator
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



def test_postgresql_task_state_machine_persists_dependency_gates_and_owner_scope():
    if not DATABASE_URL:
        pytest.skip("requires AURA_TEST_DATABASE_URL and a running PostgreSQL service")

    async def scenario():
        suffix = uuid4().hex
        principal = f"state-principal-{suffix}"
        other = f"state-other-{suffix}"
        store = PostgreSQLTaskStateMachine(DATABASE_URL)
        try:
            await store.initialize()
            parent = await store.create_task(principal_id=principal, task_id=f"parent-{suffix}", goal="parent")
            child = await store.create_task(principal_id=principal, task_id=f"child-{suffix}", goal="child", dependencies=[parent.task_id])
            assert parent.state is TaskState.READY
            assert child.state is TaskState.PENDING
            with pytest.raises(ValueError, match="dependencies are not all succeeded"):
                await store.transition(child.task_id, principal_id=principal, target=TaskState.READY)
            await store.transition(parent.task_id, principal_id=principal, target=TaskState.RUNNING)
            await store.transition(parent.task_id, principal_id=principal, target=TaskState.SUCCEEDED)
            assert (await store.get(child.task_id, principal_id=principal)).state is TaskState.READY
            with pytest.raises(KeyError):
                await store.get(parent.task_id, principal_id=other)
            await store.close()
            store = PostgreSQLTaskStateMachine(DATABASE_URL)
            await store.initialize()
            assert (await store.get(parent.task_id, principal_id=principal)).state is TaskState.SUCCEEDED
        finally:
            await store.close()
    asyncio.run(scenario())



def test_postgresql_hierarchical_memory_checkpoints_survive_reopen_and_are_scoped():
    if not DATABASE_URL:
        pytest.skip("requires AURA_TEST_DATABASE_URL and a running PostgreSQL service")

    async def scenario():
        suffix = uuid4().hex
        principal = f"memory-principal-{suffix}"
        other = f"memory-other-{suffix}"
        store = PostgreSQLHierarchicalMemory(DATABASE_URL)
        coordinator = PostgreSQLTaskMemoryCoordinator(store)
        try:
            await coordinator.initialize()
            context = await coordinator.begin(principal_id=principal, task_id=f"memory-task-{suffix}", goal="test restart recovery")
            assert any(item.kind == "goal" for item in context)
            await coordinator.finish(principal_id=principal, task_id=f"memory-task-{suffix}", state="succeeded", summary="remote checkpoint persisted")
            checkpoint = await store.load_checkpoint(principal_id=principal, task_id=f"memory-task-{suffix}")
            assert checkpoint and checkpoint["state"] == "succeeded"
            assert await store.load_checkpoint(principal_id=other, task_id=f"memory-task-{suffix}") is None
            records = await store.recall(principal_id=principal, task_id=f"memory-task-{suffix}")
            assert any("remote checkpoint persisted" in item.content for item in records)
        finally:
            await coordinator.close()
    asyncio.run(scenario())


def test_minio_s3_compatible_service_round_trip_and_delete():
    minio = pytest.importorskip("minio")
    from minio import Minio
    from io import BytesIO
    from urllib.request import urlopen
    from aura_core.storage.s3_object_storage import S3ObjectStorage

    client = Minio(os.environ.get("AURA_TEST_S3_ENDPOINT", "127.0.0.1:9000"), access_key=os.environ.get("AURA_TEST_S3_ACCESS_KEY", "minioadmin"), secret_key=os.environ.get("AURA_TEST_S3_SECRET_KEY", "minioadmin"), secure=False)
    bucket = f"aura-ci-{uuid4().hex[:20]}"
    payload = f"remote-object-{uuid4().hex}".encode()
    key = "integration/checkpoint.bin"
    endpoint = os.environ.get("AURA_TEST_S3_ENDPOINT", "127.0.0.1:9000")
    adapter = S3ObjectStorage(endpoint_url=f"http://{endpoint}", bucket=bucket, access_key=os.environ.get("AURA_TEST_S3_ACCESS_KEY", "minioadmin"), secret_key=os.environ.get("AURA_TEST_S3_SECRET_KEY", "minioadmin"), region="us-east-1")
    try:
        client.make_bucket(bucket)
        adapter.put_bytes(key, payload, content_type="application/octet-stream")
        assert adapter.get_bytes(key) == payload
        signed_url = adapter.create_presigned_get_url(key, expires_in=60)
        with urlopen(signed_url, timeout=5) as signed_response:
            assert signed_response.status == 200
            assert signed_response.read() == payload
        result = client.get_object(bucket, key)
        try:
            assert result.read() == payload
        finally:
            result.close()
            result.release_conn()
        adapter.delete(key)
        assert not any(obj.object_name == key for obj in client.list_objects(bucket))
    finally:
        if client.bucket_exists(bucket):
            for obj in client.list_objects(bucket, recursive=True):
                client.remove_object(bucket, obj.object_name)
            client.remove_bucket(bucket)


def test_remote_mode_validates_remote_endpoints_without_local_fallback(monkeypatch):
    monkeypatch.setenv("AURA_STORAGE_MODE", "remote")
    monkeypatch.setenv("AURA_DATABASE_URL", DATABASE_URL or "postgresql+asyncpg://ci.invalid/aura")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ENDPOINT", "https://objects.example.invalid")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_BUCKET", "aura-test")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_ACCESS_KEY", "test-key")
    monkeypatch.setenv("AURA_OBJECT_STORAGE_SECRET_KEY", "test-secret")
    validate_storage_mode()


def test_s3_checkpoint_is_published_only_after_object_is_durable_and_retry_is_idempotent():
    minio = pytest.importorskip("minio")
    from aura_core.enterprise.postgresql_workflow_store import PostgreSQLWorkflowStore
    from aura_core.persistence.remote_checkpoint_artifacts import RemoteCheckpointArtifacts
    from aura_core.storage.s3_object_storage import S3ObjectStorage

    if not DATABASE_URL:
        pytest.skip("requires AURA_TEST_DATABASE_URL and a running PostgreSQL service")
    from minio import Minio
    suffix = uuid4().hex[:20]
    endpoint = os.environ.get("AURA_TEST_S3_ENDPOINT", "127.0.0.1:9000")
    access_key = os.environ.get("AURA_TEST_S3_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("AURA_TEST_S3_SECRET_KEY", "minioadmin")
    bucket = f"aura-checkpoint-{suffix}"
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
    objects = S3ObjectStorage(
        endpoint_url=f"http://{endpoint}", bucket=bucket,
        access_key=access_key, secret_key=secret_key,
        region=os.environ.get("AURA_TEST_S3_REGION", "us-east-1"),
    )
    workflows = PostgreSQLWorkflowStore(DATABASE_URL)

    async def scenario():
        workflow_id = f"checkpoint-{suffix}"
        principal_id = f"principal-{suffix}"
        try:
            client.make_bucket(bucket)
            await workflows.initialize()
            created = await workflows.create(
                workflow_id=workflow_id, idempotency_key=workflow_id,
                principal_id=principal_id, task_id=workflow_id,
            )
            running = await workflows.transition(
                workflow_id, expected_version=created.version, target=WorkflowStatus.RUNNING
            )
            artifacts = RemoteCheckpointArtifacts(objects, workflows)
            payload = {"schema_version": 1, "state": "running", "cursor": 3}
            key = await artifacts.save(
                principal_id=principal_id, task_id=workflow_id, checkpoint=payload
            )
            first = await workflows.get(workflow_id)
            assert first.checkpoint_ref == key
            assert await artifacts.load(principal_id=principal_id, task_id=workflow_id) == payload
            repeated = await artifacts.save(
                principal_id=principal_id, task_id=workflow_id, checkpoint=payload
            )
            second = await workflows.get(workflow_id)
            assert repeated == key
            assert second.version == first.version
            assert second.checkpoint_ref == key
            with pytest.raises(PermissionError):
                await artifacts.load(principal_id=f"other-{suffix}", task_id=workflow_id)
        finally:
            await workflows.close()
            if client.bucket_exists(bucket):
                for obj in client.list_objects(bucket, recursive=True):
                    client.remove_object(bucket, obj.object_name)
                client.remove_bucket(bucket)

    asyncio.run(scenario())


def test_postgresql_graph_edges_persist_and_are_principal_isolated():
    if not DATABASE_URL:
        pytest.skip("requires AURA_TEST_DATABASE_URL and a running PostgreSQL service")

    from aura_core.memory.graph_store import PostgreSQLGraphStore

    async def scenario():
        principal = f"graph-{uuid4().hex}"
        other = f"graph-other-{uuid4().hex}"
        store = PostgreSQLGraphStore(DATABASE_URL)
        try:
            await store.initialize()
            first = await store.insert(principal_id=principal, subject="alpha",
                predicate="relates", object="beta")
            second = await store.insert(principal_id=principal, subject="beta",
                predicate="relates", object="gamma")
            await store.insert(principal_id=other, subject="alpha",
                predicate="private", object="secret")
            edges = await store.query(principal_id=principal, subject="alpha", depth=2)
            assert {edge["fact_id"] for edge in edges} == {first, second}
            assert not any(edge["object"] == "secret" for edge in edges)
            await store.close()
            store = PostgreSQLGraphStore(DATABASE_URL)
            await store.initialize()
            again = await store.query(principal_id=principal, subject="alpha", depth=2)
            assert {edge["fact_id"] for edge in again} == {first, second}
            assert await store.query(principal_id="unknown", subject="alpha") == []
        finally:
            await store.close()

    asyncio.run(scenario())
