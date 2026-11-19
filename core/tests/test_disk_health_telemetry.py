"""Feature 029: advisory disk pressure must be bounded and side-effect free."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from aura_core.application.system_telemetry import SystemTelemetry


def fake_psutil(*, disk_percent=95.0, disk_free=1000, disk_exception=None):
    def disk_usage(path):
        if disk_exception is not None:
            raise disk_exception
        return SimpleNamespace(percent=disk_percent, free=disk_free)
    return SimpleNamespace(
        cpu_percent=lambda interval=None: 12.5,
        virtual_memory=lambda: SimpleNamespace(percent=34.0, available=4_000_000),
        net_io_counters=lambda: SimpleNamespace(
            bytes_sent=10, bytes_recv=20,
            packets_sent=1, packets_recv=2,
        ),
        disk_usage=disk_usage,
    )


def test_disk_pressure_is_advisory_and_never_deletes(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil())
    monitor = SystemTelemetry(disk_warning=90, disk_path=tmp_path)
    snapshot = monitor.snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["disk_percent"] == 95.0
    assert snapshot["disk_free_bytes"] == 1000
    assert snapshot["cpu_percent"] == 12.5
    assert snapshot["alerts"] == [{
        "code": "disk_pressure", "severity": "warning",
        "message": "Disk utilization is 95.0%.",
    }]
    assert not list(tmp_path.iterdir())
    assert str(tmp_path) not in str(snapshot)
    assert monitor.latest() == snapshot


def test_disk_metric_unavailable_does_not_hide_cpu_or_memory(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "psutil",
                        fake_psutil(disk_exception=OSError("private disk path")))
    snapshot = SystemTelemetry(disk_path=tmp_path).snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["disk_percent"] is None
    assert snapshot["disk_free_bytes"] is None
    assert snapshot["cpu_percent"] == 12.5
    assert snapshot["memory_percent"] == 34.0
    assert "private disk path" not in str(snapshot)


@pytest.mark.parametrize("percent, free", [
    (float("nan"), 1), (float("inf"), 1), (-5, 1),
    (101, 1), (50, -1),
])
def test_invalid_disk_samples_are_not_reported(tmp_path, monkeypatch, percent, free):
    monkeypatch.setitem(sys.modules, "psutil",
                        fake_psutil(disk_percent=percent, disk_free=free))
    snapshot = SystemTelemetry(disk_path=tmp_path).snapshot()
    assert snapshot["disk_percent"] is None
    assert snapshot["disk_free_bytes"] is None
    assert not any(item["code"] == "disk_pressure" for item in snapshot["alerts"])


@pytest.mark.parametrize("bad", [0, 101, True, float("nan"), float("inf"), "90"])
def test_invalid_thresholds_fail_closed(bad):
    with pytest.raises(ValueError):
        SystemTelemetry(disk_warning=bad)
