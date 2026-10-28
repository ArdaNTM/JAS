"""Shared persistence and object-storage contracts.

Contracts do not make a local adapter remote. Remote mode remains blocked until
all production composition paths select and verify remote implementations.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AsyncRecordRepository(Protocol):
    async def save(self, record: Any) -> Any: ...
    async def get(self, entity_type: str, entity_id: str) -> Any | None: ...
    async def close(self) -> None: ...


@runtime_checkable
class ObjectStorage(Protocol):
    async def put(self, key: str, body: bytes, *, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


@runtime_checkable
class PresignedURLProvider(Protocol):
    """Produces short-lived, object-scoped URLs using a trusted signer."""

    def url_for(self, operation: str, key: str) -> str: ...
