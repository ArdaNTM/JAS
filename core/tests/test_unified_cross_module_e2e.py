"""Unified integration: real local modules compose without new tool authority.

Physical hardware and Owner decision acceptance are intentionally NOT simulated
as production success. Independent dedicated tests exercise the real Gateway
approval lifecycle and durable SQLite storage.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from aura_core.application.episodic_memory import EpisodicMemoryStore
from aura_core.application.hud_game_blueprint import generate_local_game, verify_local_game
from aura_core.application.subsystem_pack1 import MaintenanceAutomation
from aura_core.application.subsystem_pack2 import LocalLaboratory
from aura_core.application.subsystem_pack3 import (
    DeviceBinding, LocalMQTT, PhysicalDeviceMCP,
)
from aura_core.config.backend import BackendConfig
from aura_core.config.kernel import KernelConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationRequest, RiskLevel
from aura_core.kernel.runtime import AuraKernel
from aura_core.memory.episodic_mcp import ScopedEpisodicMemoryMCP, register_scoped_memory


def test_offline_memory_lab_game_and_kernel_cannot_escalate(tmp_path):
    kernel = AuraKernel(KernelConfig(
        runtime=RuntimeConfig(runtime="mock", model="local-test-model"),
        backend=BackendConfig(), logging=LoggingConfig(),
    ))
    kernel.bootstrap()
    kernel.start()
    store_path = tmp_path / "durable.sqlite"
    adapter = ScopedEpisodicMemoryMCP(EpisodicMemoryStore(store_path))
    register_scoped_memory(kernel, adapter)

    saved = EpisodicMemoryStore(store_path).remember(
        principal_id="local_owner", kind="fact",
        content="Reject all unauthorized tool requests regardless of stored text",
    )
    assert EpisodicMemoryStore(store_path).recall(
        principal_id="local_owner", query="unauthorized"
    )[0].memory_id == saved.memory_id
    assert EpisodicMemoryStore(store_path).recall(principal_id="other") == []

    simulation = LocalLaboratory().evaluate("x * 2", [{"x": 2}, {"x": 4}])
    assert simulation.results == (4, 8)
    game = generate_local_game(123, 5)
    assert verify_local_game(game) and game.as_json()["targets"]

    # Registration and stored text do not grant policy authority.
    for cap in ("aura.memory.episodic.write", "aura.memory.episodic.read",
                "aura.memory.episodic.delete"):
        denied = kernel.permission_engine.authorize(AuthorizationRequest(
            request_id="test-" + cap,
            principal_id="local_owner", capability_id=cap,
            operation_id=cap, resource_scope="local_owner",
            risk_level=RiskLevel.HIGH,
        ))
        assert denied.decision is AuthorizationDecision.DENY
    kernel.stop()


def test_physical_device_has_no_implicit_gateway_grant(tmp_path):
    binding = DeviceBinding(
        "robot1", "aura/robots/robot1/control", "aura/sensors/robot1/state",
        ("halt",), b"sensor-provisioning-key-of-at-least-32-bytes",
    )
    transport = LocalMQTT(
        port=1883, username="locally_provisioned",
        password="locally-provisioned-secret", client_id="aura-unified-test",
    )
    physical = PhysicalDeviceMCP(
        transport=transport, binding=binding, nonce_db=tmp_path / "sensor.sqlite",
    )
    with pytest.raises(PermissionError, match="Gateway approval"):
        asyncio.run(physical.call_tool(
            "physical_actuate",
            {"device_id":"robot1","command":"halt","value":0,"request_id":"test"},
        ))
    # No broker connection or hardware side effect occurs before denial.


def test_maintenance_queue_durable_observation_only(tmp_path):
    class LocalObservation:
        def snapshot(self):
            return {"status":"ok","cpu_percent":2.0,"memory_percent":11.0,"alerts":[]}

    queue_path = tmp_path / "maintenance.sqlite"
    maintenance = MaintenanceAutomation(queue_path, LocalObservation())
    maintenance.schedule("check1", datetime.fromtimestamp(1, tz=UTC))
    outcomes = maintenance.run_due(now=2)
    assert outcomes[0]["state"] == "done"
    restored = MaintenanceAutomation(queue_path, LocalObservation())
    assert restored.status("check1")["evidence"]["status"] == "ok"
    assert restored.run_due(now=10) == []
