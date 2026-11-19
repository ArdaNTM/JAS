"""Best-effort host telemetry and advisory load-shedding signals."""
from __future__ import annotations

from datetime import UTC, datetime
import math
from pathlib import Path
from typing import Any


class SystemTelemetry:
    """Collects system metrics without requiring a specific operating system."""

    def __init__(
        self, *, cpu_warning: float = 85.0, memory_warning: float = 85.0,
        disk_warning: float = 90.0, disk_path: str | Path | None = None,
    ) -> None:
        thresholds = (cpu_warning, memory_warning, disk_warning)
        if any(type(value) not in (int, float)
               or not math.isfinite(value) or not 1 <= value <= 100
               for value in thresholds):
            raise ValueError("warning thresholds must be finite numbers within 1..100")
        self.cpu_warning = cpu_warning
        self.memory_warning = memory_warning
        self.disk_warning = disk_warning
        self.disk_path = Path(disk_path) if disk_path is not None else Path.home()
        self._last_snapshot: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        try:
            import psutil  # type: ignore[import-not-found]
        except ImportError:
            result = {
                "status": "unavailable",
                "reason": "optional_dependency_psutil_not_installed",
                "sampled_at": datetime.now(UTC).isoformat(),
                "cpu_percent": None,
                "memory_percent": None,
                "disk_percent": None,
                "disk_free_bytes": None,
                "network_io": None,
                "alerts": [],
                "recommendations": ["Install psutil to enable host CPU, memory, and network telemetry."],
            }
            self._last_snapshot = result
            return result

        cpu = float(psutil.cpu_percent(interval=None))
        memory = psutil.virtual_memory()
        network = psutil.net_io_counters()
        # Optional disk telemetry is advisory and must never make healthy
        # CPU/RAM observations fail. No physical path leaves the boundary.
        disk_percent: float | None = None
        disk_free_bytes: int | None = None
        try:
            usage = psutil.disk_usage(str(self.disk_path))
            percent = float(usage.percent)
            free_bytes = int(usage.free)
            if not math.isfinite(percent) or not 0 <= percent <= 100 or free_bytes < 0:
                raise ValueError("Invalid disk usage metrics")
            disk_percent = percent
            disk_free_bytes = free_bytes
        except (OSError, ValueError, TypeError, OverflowError, AttributeError):
            pass
        alerts: list[dict[str, str]] = []
        recommendations: list[str] = []
        if cpu >= self.cpu_warning:
            alerts.append({"code": "cpu_pressure", "severity": "warning", "message": f"CPU utilization is {cpu:.1f}%."})
            recommendations.append("Temporarily reduce optional background concurrency; do not cancel authorized foreground tasks.")
        if float(memory.percent) >= self.memory_warning:
            alerts.append({"code": "memory_pressure", "severity": "warning", "message": f"Memory utilization is {memory.percent:.1f}%."})
            recommendations.append("Defer optional background work and inspect memory-intensive providers.")
        if disk_percent is not None and disk_percent >= self.disk_warning:
            alerts.append({
                "code": "disk_pressure", "severity": "warning",
                "message": f"Disk utilization is {disk_percent:.1f}%.",
            })
            recommendations.append(
                "Review disk usage; do not automatically delete files without authorization."
            )
        result = {
            "status": "ok",
            "sampled_at": datetime.now(UTC).isoformat(),
            "cpu_percent": cpu,
            "memory_percent": float(memory.percent),
            "memory_available_bytes": int(memory.available),
            "disk_percent": disk_percent,
            "disk_free_bytes": disk_free_bytes,
            "network_io": {
                "bytes_sent": int(network.bytes_sent),
                "bytes_received": int(network.bytes_recv),
                "packets_sent": int(network.packets_sent),
                "packets_received": int(network.packets_recv),
            },
            "alerts": alerts,
            "recommendations": recommendations,
        }
        self._last_snapshot = result
        return result

    def latest(self) -> dict[str, Any] | None:
        return dict(self._last_snapshot) if self._last_snapshot else None
