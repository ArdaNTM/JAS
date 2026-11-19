"""Monitor geometry validation and consented EventBus projection regressions."""
import asyncio
from dataclasses import FrozenInstanceError
from dataclasses import replace

import pytest

from aura_core.application.monitor_topology import (
    DisplayGeometry, MonitorTopologyObserver, validate_display_topology,
)
from aura_core.kernel.events import EventBus


def _pair():
    return [
        DisplayGeometry("ephemeral-right", 0, 0, 2560, 1440, 1.25, True),
        DisplayGeometry("ephemeral-left", -1920, 0, 1920, 1080, 1.0, False),
    ]


def test_multimonitor_negative_coordinates_are_supported_and_digest_is_order_independent():
    first = validate_display_topology(_pair())
    second = validate_display_topology(list(reversed(_pair())))
    assert first.bounds == (-1920, 0, 2560, 1440)
    assert first.digest == second.digest
    assert [x.display_id for x in first.displays] == ["ephemeral-left", "ephemeral-right"]
    assert first.source_trust == "TRUSTED_SHELL_METADATA_ONLY"
    assert len(first.digest) == 64
    with pytest.raises(FrozenInstanceError):
        first.displays[0].x = -999


def test_real_geometry_change_changes_digest_without_reading_screen():
    original = validate_display_topology(_pair())
    changed = _pair()
    changed[1] = replace(changed[1], x=-1800)
    assert validate_display_topology(changed).digest != original.digest


@pytest.mark.parametrize("bad", [
    [],
    [DisplayGeometry("d", 0, 0, 800, 600, 1.0, False)],
    [DisplayGeometry("d", 0, 0, 800, 600, 1.0, True)] * 2,
    [DisplayGeometry("d", 0, 0, 800, 600, float("nan"), True)],
    [DisplayGeometry("d", 0, 0, 800, 600, float("inf"), True)],
    [DisplayGeometry("d", 0, 0, 800, 600, 0.1, True)],
    [DisplayGeometry("d", 0, 0, 800, 600, 9.0, True)],
    [DisplayGeometry("../private", 0, 0, 800, 600, 1.0, True)],
    [DisplayGeometry("d\nx", 0, 0, 800, 600, 1.0, True)],
    [DisplayGeometry("d", True, 0, 800, 600, 1.0, True)],
    [DisplayGeometry("d", 0, 0, -1, 600, 1.0, True)],
    [DisplayGeometry("d", 0, 0, 0, 600, 1.0, True)],
    [DisplayGeometry("d", 100001, 0, 800, 600, 1.0, True)],
    [DisplayGeometry("d", 0, 0, 16000, 18000, 1.0, True)],
    [DisplayGeometry("d", 0, 0, 800, 600, True, True)],
    [DisplayGeometry("d", 0, 0, 800, 600, 1.0, 1)],
    [DisplayGeometry(str(x), x * 800, 0, 800, 600, 1.0, x == 0) for x in range(9)],
])
def test_bad_topology_is_rejected_fail_closed(bad):
    with pytest.raises(ValueError):
        validate_display_topology(bad)


def test_requires_confirmed_local_shell_and_rejects_other_sessions():
    bus = EventBus()
    observer = MonitorTopologyObserver(bus)
    with pytest.raises(PermissionError):
        observer.start(session_id="session", confirmed_local_shell=False)
    with pytest.raises(PermissionError):
        observer.observe(_pair(), session_id="session")
    observer.start(session_id="session", confirmed_local_shell=True)
    with pytest.raises(PermissionError):
        observer.start(session_id="other", confirmed_local_shell=True)
    with pytest.raises(PermissionError):
        observer.observe(_pair(), session_id="other")
    assert bus.snapshot()["published_total"] == 0


def test_event_has_only_bounded_layout_info_not_raw_display_ids_or_screen():
    bus = EventBus()
    seen = []
    bus.subscribe("DisplayTopologyChanged", lambda event: seen.append(event))
    observer = MonitorTopologyObserver(bus)
    observer.start(session_id="session", confirmed_local_shell=True)
    observer.observe(_pair(), session_id="session")
    observer.observe(list(reversed(_pair())), session_id="session")
    edited = _pair()
    edited[1] = replace(edited[1], x=-1600)
    observer.observe(edited, session_id="session")
    assert bus.snapshot()["published_total"] == 2
    assert asyncio.run(bus.dispatch_once()) is True
    assert asyncio.run(bus.dispatch_once()) is True
    assert [e.payload["display_count"] for e in seen] == [2, 2]
    assert seen[0].payload["metadata_only"] is True
    assert "ephemeral-left" not in str(seen[0].payload)
    assert "screen" not in str(seen[0].payload).casefold()
    assert "capture" not in str(seen[0].payload).casefold()


def test_stopping_during_validation_suppresses_stale_projection(monkeypatch):
    import aura_core.application.monitor_topology as module
    bus = EventBus()
    observer = MonitorTopologyObserver(bus)
    observer.start(session_id="session", confirmed_local_shell=True)
    original = module.validate_display_topology

    def validate_and_stop(displays):
        observer.stop(session_id="session")
        return original(displays)

    monkeypatch.setattr(module, "validate_display_topology", validate_and_stop)
    with pytest.raises(PermissionError, match="revoked"):
        observer.observe(_pair(), session_id="session")
    assert bus.snapshot()["published_total"] == 0


@pytest.mark.parametrize("invalid_session", [
    "", " padded ", "a\x00b", "a\nb", "\ud800", "a" * 129,
])
def test_invalid_shell_sessions_fail_before_observation(invalid_session):
    observer = MonitorTopologyObserver(EventBus())
    with pytest.raises(ValueError):
        observer.start(session_id=invalid_session, confirmed_local_shell=True)


def test_stop_prevents_post_session_observation():
    observer = MonitorTopologyObserver(EventBus())
    observer.start(session_id="session", confirmed_local_shell=True)
    observer.stop(session_id="session")
    with pytest.raises(PermissionError):
        observer.observe(_pair(), session_id="session")
    with pytest.raises(PermissionError):
        observer.stop(session_id="session")


def test_only_existing_eventbus_can_be_used():
    with pytest.raises(TypeError):
        MonitorTopologyObserver(object())
