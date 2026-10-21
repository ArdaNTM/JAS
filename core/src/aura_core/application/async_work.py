"""Bounded asynchronous work coordination with adaptive admission control."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Coroutine


@dataclass(frozen=True, slots=True)
class WorkSnapshot:
    active: int
    completed: int
    failed: int
    capacity: int

    def to_dict(self) -> dict[str, int]:
        return {"active": self.active, "completed": self.completed, "failed": self.failed, "capacity": self.capacity}


class AsyncWorkCoordinator:
    """Bounds concurrent work; capacity can be reduced under resource pressure."""

    def __init__(self, capacity: int = 4) -> None:
        if not 1 <= capacity <= 64:
            raise ValueError("capacity must be between 1 and 64")
        self.capacity = capacity
        self._configured_capacity = capacity
        self._active = self._completed = self._failed = 0
        self._condition = asyncio.Condition()

    async def set_capacity(self, capacity: int) -> None:
        if not 1 <= capacity <= 64:
            raise ValueError("capacity must be between 1 and 64")
        async with self._condition:
            self.capacity = capacity
            self._condition.notify_all()

    async def apply_resource_pressure(self, pressured: bool) -> None:
        await self.set_capacity(1 if pressured else self._configured_capacity)

    async def _acquire(self) -> None:
        async with self._condition:
            while self._active >= self.capacity:
                await self._condition.wait()
            self._active += 1

    async def _release(self, *, failed: bool) -> None:
        async with self._condition:
            self._active -= 1
            if failed:
                self._failed += 1
            else:
                self._completed += 1
            self._condition.notify_all()

    async def run(self, operation: Callable[[], Any]) -> Any:
        await self._acquire()
        failed = True
        try:
            result = await asyncio.to_thread(operation)
            failed = False
            return result
        finally:
            await self._release(failed=failed)

    async def run_async(self, operation: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        await self._acquire()
        failed = True
        try:
            result = await operation()
            failed = False
            return result
        finally:
            await self._release(failed=failed)

    async def snapshot(self) -> WorkSnapshot:
        async with self._condition:
            return WorkSnapshot(self._active, self._completed, self._failed, self.capacity)
