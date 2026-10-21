"""Best-effort host telemetry and advisory load-shedding signals."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class SystemTelemetry:
    """Collects system metrics without requiring a specific operating system."""

    def __init__(self, *, cpu_warning: float = 85.0, memory_warning: float = 85.0) -> None:
        if not 1 <= cpu_warning <= 100 or not 1 <= memory_warning <= 100:
            raise ValueError("warning thresholds must be within 1..100")
        self.cpu_warning = cpu_warning
        self.memory_warning = memory_warning
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
                "network_io": None,
                "alerts": [],
                "recommendations": ["Install psutil to enable host CPU, memory, and network telemetry."],
            }
            self._last_snapshot = result
            return result

        cpu = float(psutil.cpu_percent(interval=None))
        memory = psutil.virtual_memory()
        network = psutil.net_io_counters()
        alerts: list[dict[str, str]] = []
        recommendations: list[str] = []
        if cpu >= self.cpu_warning:
            alerts.append({"code": "cpu_pressure", "severity": "warning", "message": f"CPU utilization is {cpu:.1f}%."})
            recommendations.append("Temporarily reduce optional background concurrency; do not cancel authorized foreground tasks.")
        if float(memory.percent) >= self.memory_warning:
            alerts.append({"code": "memory_pressure", "severity": "warning", "message": f"Memory utilization is {memory.percent:.1f}%."})
            recommendations.append("Defer optional background work and inspect memory-intensive providers.")
        result = {
            "status": "ok",
            "sampled_at": datetime.now(UTC).isoformat(),
            "cpu_percent": cpu,
            "memory_percent": float(memory.percent),
            "memory_available_bytes": int(memory.available),
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
