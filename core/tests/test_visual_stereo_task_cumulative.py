"""Cross-modular real stereo -> telemetry EventBus -> durable task Gateway test."""
import asyncio
import base64

import pytest

from aura_core.application.live_svg_chart import (
    GovernedLiveSVGChart, LiveChartDenied, register_live_svg_chart,
)
from aura_core.application.live_task_panel import (
    GovernedLiveTaskPanel, LiveTaskDenied, register_live_task_panel,
)
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.providers.stereo_depth_mcp import (
    GovernedStereoDepth, StereoCalibration, register_local_stereo_depth,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry


def _pair(shift=5, w=80, h=56):
    pixels = bytes((x * 73 + y * 29 + x * y * 11 + x * x * 7) % 256
                   for y in range(h) for x in range(w))
    right = bytes(pixels[y * w + x + shift] if x + shift < w else 0
                  for y in range(h) for x in range(w))
    header = f"P5\n{w} {h}\n255\n".encode("ascii")
    return header + pixels, header + right


def _setup(allowed_caps):
    bus = EventBus()
    store = TaskStateMachine(":memory:", event_bus=bus)
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    caps = CapabilityRegistry(services)
    register_live_svg_chart(services=services, providers=providers,
                            capabilities=caps, event_bus=bus)
    register_live_task_panel(services=services, providers=providers,
                             capabilities=caps, event_bus=bus,
                             task_state_machine=store)
    register_local_stereo_depth(
        services=services, providers=providers, capabilities=caps,
        calibration=StereoCalibration(focal_px=400, baseline_m=0.08),
    )
    engine = PermissionEngine(caps)
    policies = (
        ("vision.stereo.depth", "vision/consented/rectified-stereo",
         AuthorizationLevel.READ),
        ("visualization.telemetry.read", "visualization/gateway-latency/read-only",
         AuthorizationLevel.READ),
        ("visualization.tasks.read", "visualization/tasks/read-only",
         AuthorizationLevel.READ),
    )
    for cap, scope, level in policies:
        if cap in allowed_caps:
            engine.add_policy(PermissionPolicy(
                policy_id="integration." + cap, policy_version="1.0.0",
                principal_id="owner", capability_id=cap, operation_id=cap,
                resource_scope=scope, authorization_level=level,
                decision=AuthorizationDecision.ALLOW,
            ))
    gateway = MCPGateway(caps, providers, engine, event_bus=bus)
    return (
        bus, store, engine,
        GovernedStereoDepth(gateway, authenticated_principal_id="owner"),
        GovernedLiveSVGChart(gateway, authenticated_principal_id="owner"),
        GovernedLiveTaskPanel(gateway, authenticated_principal_id="owner"),
    )


def test_live_stereo_gateway_profiler_and_real_persisted_tasks_share_core():
    caps = {"vision.stereo.depth", "visualization.telemetry.read",
            "visualization.tasks.read"}
    bus, store, engine, stereo, chart, tasks = _setup(caps)
    record = store.create_task(principal_id="owner", goal="HIDDEN_PURCHASE_SECRET")
    store.transition(record.task_id, principal_id="owner", target=TaskState.RUNNING)
    pair = _pair()
    result = asyncio.run(stereo.estimate(*pair, capture_confirmed=True))
    assert len(result.samples) >= 20
    assert result.safe_for_physical_control is False
    for _ in range(12):
        asyncio.run(bus.dispatch_once())
    svg = asyncio.run(chart.render())
    panel = asyncio.run(tasks.read())
    assert svg.sample_count >= 1
    assert svg.trust == "REDACTED_UNTRUSTED_TELEMETRY"
    assert panel.tasks[0].task_id == record.task_id
    assert panel.tasks[0].state == "running"
    assert "HIDDEN_PURCHASE_SECRET" not in repr(panel)
    assert "HIDDEN_PURCHASE_SECRET" not in svg.svg
    assert len(engine.audit_records()) >= 3
    assert set(engine.audit_records()[-3:][i].request.capability_id
               for i in range(3)) == caps
    store.close()


def test_stereo_allow_does_not_grant_chart_or_task_reading():
    bus, store, _, stereo, chart, tasks = _setup({"vision.stereo.depth"})
    pair = _pair()
    assert len(asyncio.run(stereo.estimate(*pair, capture_confirmed=True)).samples) >= 20
    with pytest.raises(LiveChartDenied):
        asyncio.run(chart.render())
    with pytest.raises(LiveTaskDenied):
        asyncio.run(tasks.read())
    store.close()


def test_stereo_input_never_grants_actuation_or_task_state_changes():
    bus, store, _, stereo, chart, tasks = _setup({
        "vision.stereo.depth", "visualization.tasks.read",
    })
    initial = store.create_task(principal_id="owner", goal="NOT_ACTUATED")
    before = store.get(initial.task_id, principal_id="owner")
    result = asyncio.run(stereo.estimate(*_pair(), capture_confirmed=True))
    after = store.get(initial.task_id, principal_id="owner")
    assert before.state == after.state
    assert result.safe_for_physical_control is False
    assert not hasattr(stereo, "click")
    assert not hasattr(stereo, "move_robot")
    store.close()
