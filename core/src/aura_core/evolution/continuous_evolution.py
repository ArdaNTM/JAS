"""Opt-in continuous *discovery*; never an attestor, Owner, or tool executor.

The independent attestor may run separately with --watch and its private OS
identity. This controller cannot sign a proof or bypass MCPGateway policies.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger("aura_core.evolution.continuous")


class ContinuousEvolutionController:
    """Run bounded public discovery, staging and signed-capability rechecks."""

    def __init__(self, *, discovery, activation=None, interval_seconds: int = 240):
        if type(interval_seconds) is not int or not 180 <= interval_seconds <= 900:
            raise ValueError("Continuous scan period must be 180..900 seconds")
        self.discovery = discovery
        self.activation = activation
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_error = ""
        self._last_summary: dict[str, Any] = {}
        self._cycles = 0
        self._scanned = 0
        self._last_active: list[str] = []
        self._retry_failures = 0
        self._last_run = 0

    def status(self) -> dict[str, Any]:
        running = self._task is not None and not self._task.done()
        discovery = self.discovery.status()
        proposals = getattr(self.discovery, "proposals", None)
        queued = 0
        if callable(proposals):
            # The durable queue count is normally supplied by the engine.
            counter = getattr(self.discovery, "queued_count", None)
            if callable(counter):
                queued = int(counter())
            else:
                queued = sum(
                    row.get("package_status") in (None, "pending", "Queued", "READY_FOR_OWNER_REVIEW")
                    for row in proposals(50)
                )
        elif callable(getattr(self.discovery, "queued_count", None)):
            queued = int(self.discovery.queued_count())
        live = (self.activation.active_summary()
                if self.activation is not None else [])
        active = [row for row in live if row.get("status") == "ACTIVE"]
        return {
            "state": "RUNNING" if running else "IDLE",
            "active_sources": ["github", "registry", "pypi"] if running else [],
            "scanned_candidates": self._scanned,
            "queued_packages": queued,
            "active_count": sum(len(row.get("capabilities", [])) for row in active),
            "recent_active": self._last_active[-10:],
            "proposal_count": discovery.get("proposal_count", 0),
            "static_ready_count": discovery.get("verified_static_count", 0),
            "cycles": self._cycles,
            "last_run": self._last_run,
            "last_error": self._last_error,
            "last_summary": self._last_summary,
            "interval_seconds": self.interval_seconds,
            "owner_delegation_required": True,
            "independent_attestation_required": True,
            "gateway_required": True,
        }

    def start(self) -> dict[str, Any]:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(
                self._run(), name="aura-continuous-evolution",
            )
        return self.status()

    async def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
        return self.status()

    async def _run(self) -> None:
        while not self._stop.is_set():
            delay = self.interval_seconds
            try:
                workspace = getattr(self.discovery, "workspace", None)
                if workspace is not None:
                    # Prune only age-proven rejected metadata before every scan.
                    await asyncio.to_thread(workspace.prune_rejected_staging)
                result = await self.discovery.run_once(
                    full_scan=True, multi_source=True,
                )
                if self.activation is not None:
                    # Rechecks strictly require independently signed, fresh
                    # attestations and current Owner delegation.
                    active = await self.activation.scan()
                    self._last_active = [
                        name for name in active if isinstance(name, str)
                    ][:10]
                else:
                    self._last_active = []
                self._cycles += 1
                self._last_run = int(time.time())
                self._scanned += int(result.get("new_count", 0))
                self._last_summary = {
                    "new_count": int(result.get("new_count", 0)),
                    "staged_count": int(result.get("staged_count", 0)),
                    "failed_sources": len(result.get("failed_queries", [])),
                }
                self._last_error = ""
                if result.get("failed_queries"):
                    # Partial rate-limits trigger restrained backoff without
                    # ever attempting to manufacture a missing MCP permission.
                    self._retry_failures = min(5, self._retry_failures + 1)
                    delay = max(delay, min(1800, 60 * (2 ** self._retry_failures)))
                else:
                    self._retry_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Continuous Evolution cycle failed", exc_info=True)
                self._cycles += 1
                self._last_error = type(exc).__name__
                self._last_run = int(time.time())
                self._retry_failures = min(5, self._retry_failures + 1)
                delay = max(delay, min(1800, 60 * (2 ** self._retry_failures)))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
