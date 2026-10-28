"""Durable checkpoint artifacts with S3-first, PostgreSQL-reference commit ordering.

The object key is deterministic for a principal/task/payload digest. If the
process stops after the object write but before the PostgreSQL reference write,
retrying the same checkpoint safely reuses the object and completes the pointer.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from aura_core.enterprise.postgresql_workflow_store import PostgreSQLWorkflowStore
from aura_core.storage.s3_object_storage import S3ObjectStorage


class RemoteCheckpointArtifacts:
    def __init__(self, objects: S3ObjectStorage, workflows: PostgreSQLWorkflowStore) -> None:
        self._objects = objects
        self._workflows = workflows

    @staticmethod
    def _key(principal_id: str, task_id: str, payload: bytes) -> str:
        scope = hashlib.sha256(f"{principal_id}\0{task_id}".encode()).hexdigest()
        digest = hashlib.sha256(payload).hexdigest()
        return f"checkpoints/{scope}/{digest}.json"

    async def save(self, *, principal_id: str, task_id: str, checkpoint: dict[str, Any]) -> str:
        if not principal_id.strip() or not task_id.strip():
            raise ValueError("principal_id and task_id are required")
        payload = json.dumps(checkpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        key = self._key(principal_id, task_id, payload)
        # S3 must be durable before PostgreSQL publishes a reference to it.
        await asyncio.to_thread(
            self._objects.put_bytes, key, payload, content_type="application/json"
        )
        workflow = await self._workflows.get(task_id)
        if workflow is None:
            raise KeyError("Workflow not found for checkpoint")
        if workflow.principal_id != principal_id or workflow.task_id != task_id:
            raise PermissionError("Checkpoint scope does not match workflow owner")
        if workflow.checkpoint_ref != key:
            await self._workflows.save_checkpoint(
                task_id, expected_version=workflow.version, checkpoint_ref=key
            )
        return key

    async def load(self, *, principal_id: str, task_id: str) -> dict[str, Any] | None:
        workflow = await self._workflows.get(task_id)
        if workflow is None:
            raise KeyError("Workflow not found for checkpoint")
        if workflow.principal_id != principal_id or workflow.task_id != task_id:
            raise PermissionError("Checkpoint scope does not match workflow owner")
        if not workflow.checkpoint_ref:
            return None
        payload = await asyncio.to_thread(self._objects.get_bytes, workflow.checkpoint_ref)
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Stored checkpoint payload must be an object")
        return value

    async def verify(self, *, principal_id: str, task_id: str) -> bool:
        checkpoint = await self.load(principal_id=principal_id, task_id=task_id)
        return checkpoint is not None
