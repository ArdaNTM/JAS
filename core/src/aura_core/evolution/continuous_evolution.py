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

    def __init__(self, *, discovery, activation=None, analyzer=None,
                 interval_seconds: int = 240):
        if type(interval_seconds) is not int or not 180 <= interval_seconds <= 900:
            raise ValueError("Continuous scan period must be 180..900 seconds")
        self.discovery = discovery
        self.activation = activation
        self.analyzer = analyzer
        self._local_gaps = 0
        self._analyzed_files = 0
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
        self._source_health: dict[str, dict[str, object]] = {
            key: {"state": "IDLE", "successful_queries": 0,
                  "failed_queries": 0, "reason": ""}
            for key in ("github", "registry", "pypi")
        }

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
                    row.get("package_status") in (None, "pending", "Queued")
                    for row in proposals(50)
                )
        elif callable(getattr(self.discovery, "queued_count", None)):
            queued = int(self.discovery.queued_count())
        live = (self.activation.active_summary()
                if self.activation is not None else [])
        active = [row for row in live if row.get("status") == "ACTIVE"]
        from aura_core.evolution.attestor_health import read_attestor_health
        workspace = (getattr(self.activation, "workspace", None)
                     or getattr(self.discovery, "workspace", None))
        attestor = (read_attestor_health(workspace.root) if workspace is not None
                    else {"state": "UNKNOWN", "heartbeat": 0, "last_success": 0,
                          "last_renewal": 0, "last_error": ""})
        return {
            "attestor_health": attestor,
            "state": "RUNNING" if running else "IDLE",
            "active_sources": ["github", "registry", "pypi"] if running else [],
            "source_health": discovery.get("source_health", self._source_health),
            "scanned_candidates": self._scanned,
            "queued_packages": queued,
            "active_count": sum(len(row.get("capabilities", [])) for row in active),
            "recent_active": self._last_active[-10:],
            "active_providers": [
                {"repository": row["repository"], "tool_count": len(row.get("capabilities", []))}
                for row in active if isinstance(row.get("repository"), str)
            ],
            "proposal_count": discovery.get("proposal_count", 0),
            "static_ready_count": discovery.get("verified_static_count", 0),
            "cycles": self._cycles,
            "local_gap_count": self._local_gaps,
            "analyzed_files": self._analyzed_files,
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
                if self.analyzer is not None:
                    # Read-only bounded checkout analysis; no source edits,
                    # model access, or policy mutation is possible here.
                    local_report = await asyncio.to_thread(self.analyzer.scan)
                    self._local_gaps = len(local_report.proposals)
                    self._analyzed_files = local_report.scanned_files
                cycle_progress = 0

                def on_progress(scanned: int) -> None:
                    nonlocal cycle_progress
                    if type(scanned) is int and 0 < scanned <= 250:
                        # The authenticated status endpoint reads this counter
                        # while the same scan coroutine is still in progress.
                        cycle_progress += scanned
                        self._scanned += scanned

                result = await self.discovery.run_once(
                    full_scan=True, multi_source=True,
                    on_progress=on_progress,
                )
                if isinstance(result.get("source_health"), dict):
                    self._source_health = result["source_health"]
                if self.activation is not None:
                    # Rechecks strictly require independently signed, fresh
                    # attestations and current Owner delegation.
                    active = await self.activation.scan()
                    newly_active = [name for name in active if isinstance(name, str)][:10]
                    if newly_active:
                        self._last_active = newly_active
                self._cycles += 1
                self._last_run = int(time.time())
                if cycle_progress == 0:
                    # Compatibility for existing scheduler implementations that
                    # do not yet emit source-group progress callbacks.
                    self._scanned += max(
                        len(result.get("items", [])), int(result.get("new_count", 0)),
                    )
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
                # Some failures occur after individual queries have committed.
                # Expose the last trustworthy source statuses without claiming
                # every remote source was healthy.
                status = self.discovery.status()
                if isinstance(status.get("source_health"), dict):
                    self._source_health = status["source_health"]
                self._last_run = int(time.time())
                self._retry_failures = min(5, self._retry_failures + 1)
                delay = max(delay, min(1800, 60 * (2 ** self._retry_failures)))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
