"""Real stores and Gateway authorization for the additional JARVIS subsystems."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest

from aura_core.application.briefing_service import BriefingService, BRIEFING_CAP, BRIEFING_TOOL
from aura_core.application.semantic_consolidation import (
    SemanticConsolidationMCP, CONSOLIDATE_CAP, CONSOLIDATE_TOOL,
)
from aura_core.application.iot_gateway import SmartDeviceMCP, project_iot_event
from aura_core.application.subsystem_pack3 import DeviceBinding
from aura_core.application.task_memory import TaskMemoryCoordinator
from aura_core.application.task_state_machine import TaskState, TaskStateMachine
from aura_core.enterprise.workflow_store import SQLiteWorkflowStore
from aura_core.kernel.events import EventBus
from aura_core.memory.hierarchical_memory import SQLiteEpisodicMemory
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.security.face_id import FaceVerificationGate


def call(provider, name, args, *, principal="local_owner", cap, approved=False, risk="low"):
    token = enter_dispatch(DispatchGrant(principal, cap, name, approved, risk))
    try:
        return asyncio.run(provider.call_tool(name, args))
    finally:
        leave_dispatch(token)


def test_briefing_reads_persisted_tasks_and_dependencies_without_cross_scope(tmp_path):
    tasks = TaskStateMachine(tmp_path / "tasks.db")
    workflows = SQLiteWorkflowStore(str(tmp_path / "workflows.db"))
    memory = TaskMemoryCoordinator(SQLiteEpisodicMemory(tmp_path / "memory.db"))
    a = tasks.create_task(principal_id="local_owner", goal="Önce hazırlık", task_id="a")
    tasks.create_task(principal_id="local_owner", goal="Sonraki görev", task_id="b", dependencies=("a",))
    tasks.create_task(principal_id="foreign", goal="FOREIGN_SECRET", task_id="foreign")
    memory.begin(principal_id="local_owner", task_id="a", goal="Önce hazırlık")
    provider = BriefingService(tasks, workflows, memory)
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool(BRIEFING_TOOL, {}))
    summary = call(provider, BRIEFING_TOOL, {}, cap=BRIEFING_CAP)
    assert summary["title"] == "Günün Planı"
    assert summary["alerts_title"] == "Kritik Uyarılar"
    assert summary["plan"][0]["task_id"] == a.task_id
    assert summary["plan"][0]["memory_state"] == "running"
    assert any(row["task_id"] == "b" for row in summary["alerts"])
    assert "FOREIGN_SECRET" not in repr(summary)
    assert tasks.get("a", principal_id="local_owner").state is TaskState.READY
    tasks.close()
    workflows.close()


def test_semantic_records_are_deduplicated_scoped_and_erased_with_sources(tmp_path):
    store = SQLiteEpisodicMemory(tmp_path / "memory.db")
    ids = []
    for _ in range(2):
        ids.append(store.append(principal_id="local_owner", task_id="t", content="Türkçe araştırma kaynakları",
                                source="test").record_id)
    store.append(principal_id="foreign", task_id="t", content="FOREIGN_SECRET", source="test")
    prompts = []

    class LocalModel:
        async def complete_json(self, *, system_prompt, user_prompt):
            prompts.append(user_prompt)
            return {"summary": "Türkçe araştırma kaynakları tekrarlandı."}

    idle = [False]
    provider = SemanticConsolidationMCP(store, LocalModel(), principal_id="local_owner",
                                       is_idle=lambda: idle[0])
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool(CONSOLIDATE_TOOL, {}))
    assert call(provider, CONSOLIDATE_TOOL, {}, cap=CONSOLIDATE_CAP, risk="medium")["saved"] == 0
    idle[0] = True
    assert call(provider, CONSOLIDATE_TOOL, {}, cap=CONSOLIDATE_CAP, risk="medium")["saved"] == 1
    assert call(provider, CONSOLIDATE_TOOL, {}, cap=CONSOLIDATE_CAP, risk="medium")["saved"] == 0
    assert len(prompts) == 1 and "FOREIGN_SECRET" not in prompts[0]
    records = store.recall_semantic(principal_id="local_owner", task_id="t")
    assert set(records[0].source_ids) == set(ids)
    assert records[0].untrusted
    assert store.recall_semantic(principal_id="foreign", task_id="t") == []
    assert len(store.recall(principal_id="local_owner", task_id="t")) == 2
    store.forget_task(principal_id="local_owner", task_id="t", confirmed=True)
    assert store.recall_semantic(principal_id="local_owner", task_id="t") == []
    assert len(store.recall(principal_id="foreign", task_id="t")) == 1


def test_face_gate_only_restricts_and_unavailable_does_not_grant_or_reset():
    values = iter([None, False, None, True])
    gate = FaceVerificationGate(lambda: next(values))
    assert not gate.restricted("local_owner")
    assert gate.verify("local_owner") == "unavailable"
    assert not gate.restricted("local_owner")
    assert gate.verify("local_owner") == "restricted"
    assert gate.restricted("local_owner")
    assert gate.verify("local_owner") == "unavailable"
    assert gate.restricted("local_owner")
    assert gate.verify("local_owner") == "matched"
    assert not gate.restricted("local_owner")
    with pytest.raises(PermissionError):
        gate.verify("foreign")


def test_smart_device_requires_bound_capability_consumed_approval_and_face_gate(tmp_path):
    sent = []
    bus = EventBus()
    events = []
    bus.subscribe("*", lambda event: events.append(event))
    gate = FaceVerificationGate(lambda: False)

    class Transport:
        def publish(self, topic, message):
            sent.append((topic, message))
        def receive(self, topic):
            payload = {"device_id": "lamp", "metric": "power", "value": 1,
                       "sequence": 1, "timestamp": int(time.time())}
            payload["signature"] = hmac.new(b"s" * 32,
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
                hashlib.sha256).hexdigest()
            return payload

    device = SmartDeviceMCP(
        transport=Transport(),
        binding=DeviceBinding("lamp", "aura/robots/lamp/control", "aura/sensors/lamp/power",
                              ("on", "off"), b"s" * 32),
        nonce_db=tmp_path / "nonce.db", event_bus=bus, face_gate=gate,
    )
    args = {"device_id":"lamp", "command":"on", "value":1, "request_id":"req1"}
    for cap, approved in [(device.actuate_capability, False), ("iot.other.actuate", True)]:
        with pytest.raises(PermissionError):
            call(device, "physical_actuate", args, cap=cap, approved=approved, risk="critical")
    assert sent == []
    result = call(device, "physical_actuate", args, cap=device.actuate_capability, approved=True, risk="critical")
    assert result["status"] == "submitted_unverified" and len(sent) == 1
    assert asyncio.run(bus.dispatch_once())
    event = events[0]
    envelope = {"event": event.event_type, "source": event.source_component, "data": dict(event.payload)}
    assert project_iot_event(envelope, "foreign") is None
    assert project_iot_event(envelope, "local_owner")["data"]["status"] == "submitted_unverified"
    gate.verify("local_owner")
    with pytest.raises(PermissionError):
        call(device, "physical_actuate", args, cap=device.actuate_capability, approved=True, risk="critical")
    assert len(sent) == 1
    status = call(device, "physical_sensor", {"device_id":"lamp"},
                  cap=device.status_capability, approved=True, risk="high")
    assert status["attested"] is True and status["state"] == "on"
    with pytest.raises(PermissionError, match="replayed"):
        call(device, "physical_sensor", {"device_id":"lamp"},
             cap=device.status_capability, approved=True, risk="high")
