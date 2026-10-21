"""Bounded asynchronous work coordination for responsive AURA APIs."""
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
        return {
            "active": self.active,
            "completed": self.completed,
            "failed": self.failed,
            "capacity": self.capacity,
        }


class AsyncWorkCoordinator:
    """Bounds concurrent blocking/offloaded work and tracks its lifecycle."""

    def __init__(self, capacity: int = 4) -> None:
        if not 1 <= capacity <= 64:
            raise ValueError("capacity must be between 1 and 64")
        self.capacity = capacity
        self._semaphore = asyncio.Semaphore(capacity)
        self._active = 0
        self._completed = 0
        self._failed = 0
        self._lock = asyncio.Lock()

    async def run(self, operation: Callable[[], Any]) -> Any:
        async with self._semaphore:
            async with self._lock:
                self._active += 1
            try:
                result = await asyncio.to_thread(operation)
            except BaseException:
                async with self._lock:
                    self._failed += 1
                raise
            else:
                async with self._lock:
                    self._completed += 1
                return result
            finally:
                async with self._lock:
                    self._active -= 1

    async def run_async(self, operation: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        async with self._semaphore:
            async with self._lock:
                self._active += 1
            try:
                result = await operation()
            except BaseException:
                async with self._lock:
                    self._failed += 1
                raise
            else:
                async with self._lock:
                    self._completed += 1
                return result
            finally:
                async with self._lock:
                    self._active -= 1

    async def snapshot(self) -> WorkSnapshot:
        async with self._lock:
            return WorkSnapshot(self._active, self._completed, self._failed, self.capacity)
