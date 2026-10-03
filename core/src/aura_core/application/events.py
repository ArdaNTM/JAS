from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Any
from uuid import UUID

class EventConnection:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send(self, event: dict[str, Any]) -> None:
        await self.queue.put(event)

    async def receive(self) -> dict[str, Any]:
        return await self.queue.get()

class LiveEventHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[EventConnection]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, task_id: UUID, connection: EventConnection) -> None:
        async with self._lock:
            self._connections[str(task_id)].add(connection)

    async def disconnect(self, task_id: UUID, connection: EventConnection) -> None:
        async with self._lock:
            self._connections[str(task_id)].discard(connection)
            if not self._connections[str(task_id)]:
                del self._connections[str(task_id)]

    async def broadcast(self, task_id: UUID, event: dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._connections.get(str(task_id), []))
        for conn in conns:
            await conn.send(event)
