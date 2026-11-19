"""Cumulative PR112-135 integration: real Kernel, Gateway, SQLite and DSP boundaries.

This review suite does not claim device/model hardware acceptance; it ensures the
combined source tree preserves the same authorization and failure semantics.
"""
from __future__ import annotations

import asyncio
import io
import math
import struct
import wave
from types import SimpleNamespace

import pytest

from aura_core.application.full_duplex_session import FullDuplexSessionManager
from aura_core.application.voice_prosody import VoiceProsodyService
from aura_core.application.monitor_topology import DisplayGeometry, MonitorTopologyObserver
from aura_core.application.hud_layout_plan import HUDPanelRequest, plan_hud_layout
from aura_core.application.episodic_memory import EpisodicMemoryStore
from aura_core.memory.governed_access import GovernedEpisodicMemory, MemoryAccessDenied
from aura_core.application.governed_home_inventory import GovernedHomeInventoryReader
from aura_core.application.governed_ha_state import GovernedHomeAssistantStateReader, HomeStateDenied
from aura_core.kernel.events import EventBus
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.kernel.capabilities import (
    CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType,
)
from aura_core.kernel.permissions import (
    PermissionEngine, PermissionPolicy, AuthorizationLevel, AuthorizationDecision,
)
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.gateway import MCPGateway


def test_monitor_event_really_drives_bounded_hud_layout_not_window_authority():
    events = EventBus()
    observed = []
    events.subscribe("DisplayTopologyChanged", observed.append)
    tracker = MonitorTopologyObserver(events)
    tracker.start(session_id="trusted-shell", confirmed_local_shell=True)
    topology = tracker.observe([
        DisplayGeometry("screen-left", -1920, 0, 1920, 1080, 1.0, False),
        DisplayGeometry("screen-main", 0, 0, 2560, 1440, 1.5, True),
    ], session_id="trusted-shell")
    plan = plan_hud_layout(topology, [
        HUDPanelRequest("focus", 200, 110, "top-left", "screen-left"),
        HUDPanelRequest("status", 250, 90, "bottom-right"),
    ])
    assert plan.preview_only and plan.topology_digest == topology.digest
    assert len(plan.placements) == 2
    assert plan.placements[0].x < 0
    assert plan.placements[1].display_id == "screen-main"
    assert asyncio.run(events.dispatch_once()) is True
    assert observed[0].payload["metadata_only"] is True
    assert "screen-left" not in str(observed[0].payload)
    tracker.stop(session_id="trusted-shell")
    with pytest.raises(PermissionError):
        tracker.observe(list(topology.displays), session_id="trusted-shell")


def test_real_sqlite_memory_remains_principal_bound_under_combined_core(tmp_path):
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="memory-evidence", provider="aura", version="1.0.0",
        category=ServiceCategory.CORE,
    ), object())
    capabilities = CapabilityRegistry(services)
    capabilities.register(CapabilityDefinition(
        capability_id="memory.episodic.read", name="Memory evidence",
        version="1.0.0", description="Scoped read evidence",
        provider_id=service.service_id, provider_type=ProviderType.SERVICE,
        category=CapabilityCategory.MEMORY, risk_level="medium",
    ))
    policies = PermissionEngine(capabilities)
    store = EpisodicMemoryStore(tmp_path / "combined-memory.sqlite3")
    store.remember(principal_id="owner", kind="fact", content="owner note")
    store.remember(principal_id="other", kind="fact", content="other secret")
    reader = GovernedEpisodicMemory(store, policies, authenticated_principal_id="owner")
    with pytest.raises(MemoryAccessDenied):
        reader.recall()
    policies.add_policy(PermissionPolicy(
        policy_id="owner.read", policy_version="1.0.0",
        principal_id="owner", capability_id="memory.episodic.read",
        operation_id="memory.recall", resource_scope="memory/episodic/owner",
        authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))
    rows = reader.recall()
    assert [row.content for row in rows] == ["owner note"]
    assert all(row.trust == "UNTRUSTED" for row in rows)
    assert store.count(principal_id="other") == 1
    with pytest.raises(TypeError):
        reader.recall(principal_id="other")


class _CombinedHomeProvider:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return (
            MCPTool(name="list_devices", description="Read safe device inventory",
                    input_schema={"type": "object", "additionalProperties": False}),
            MCPTool(name="get_entity_state", description="Read a single entity state",
                    input_schema={"type": "object",
                                  "properties": {"device_id": {"type": "string"}},
                                  "required": ["device_id"],
                                  "additionalProperties": False}),
        )

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "list_devices":
            return SimpleNamespace(is_error=False, structured_content={"devices": [
                {"device_id": "light.desk", "category": "light", "available": True},
            ]})
        if name == "get_entity_state":
            return SimpleNamespace(is_error=False, structured_content={
                "device_id": "light.desk", "state": "on",
                "sampled_at": "2026-11-16T03:00:00+00:00",
            })
        raise AssertionError("An unregistered Home actuation tool was called")


def test_discovery_is_not_entity_read_authority_but_second_gateway_policy_is():
    services = ServiceRegistry()
    service = services.register(ServiceDefinition(
        name="Home evidence", provider="mcp", version="1.0.0",
        category=ServiceCategory.MCP,
    ), object())
    providers = ProviderRegistry(services)
    backend = _CombinedHomeProvider()
    providers.register(ProviderDefinition(
        provider_id="home.fake", name="Home evidence", version="1.0.0",
        service_id=service.service_id,
    ), backend)
    capabilities = CapabilityRegistry(services)
    for cap, tool in (
        ("home.device.discover", "list_devices"),
        ("home.entity.state.read", "get_entity_state"),
    ):
        capabilities.register(CapabilityDefinition(
            capability_id=cap, name=cap, version="1.0.0",
            description="Read-only Home evidence",
            provider_id="home.fake", provider_type=ProviderType.MCP,
            category=CapabilityCategory.AUTOMATION, tool_name=tool,
            risk_level="medium",
        ))
    permissions = PermissionEngine(capabilities)
    permissions.add_policy(PermissionPolicy(
        policy_id="owner.inventory", policy_version="1.0.0",
        principal_id="owner", capability_id="home.device.discover",
        operation_id="home.device.discover", resource_scope="home/devices/read-only",
        authorization_level=AuthorizationLevel.READ,
        decision=AuthorizationDecision.ALLOW,
    ))
    gateway = MCPGateway(capabilities, providers, permissions)

    async def scenario():
        inventory = await GovernedHomeInventoryReader(
            gateway, authenticated_principal_id="owner",
        ).discover()
        reader = GovernedHomeAssistantStateReader(
            gateway, authenticated_principal_id="owner",
            authorized_inventory=inventory,
        )
        with pytest.raises(HomeStateDenied):
            await reader.read(device_id="light.desk")
        assert backend.calls == [("list_devices", {})]
        permissions.add_policy(PermissionPolicy(
            policy_id="owner.entity", policy_version="1.0.0",
            principal_id="owner", capability_id="home.entity.state.read",
            operation_id="home.entity.state.read",
            resource_scope="home/entities/light.desk/read-only",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
        evidence = await reader.read(device_id="light.desk")
        assert evidence.state == "on" and evidence.trust == "UNTRUSTED_STATE_METADATA"
        assert backend.calls[-1] == ("get_entity_state", {"device_id": "light.desk"})
        with pytest.raises(HomeStateDenied):
            await reader.read(device_id="camera.secret")
        assert len(backend.calls) == 2

    asyncio.run(scenario())


def test_real_acoustic_prosody_dsp_and_generation_safe_speech_manager_coexist():
    frames = bytearray()
    for i in range(16_000):
        v = int(0.3 * 32767 * math.sin(2.0 * math.pi * 180.0 * i / 16_000))
        frames += struct.pack("<h", v)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(bytes(frames))

    class Recognizer:
        async def transcribe(self, audio, *, session_id):
            return "test integration"

    class Synthesizer:
        async def synthesize(self, text, *, session_id):
            return b""

    class Player:
        async def play(self, audio, *, session_id):
            return None
        async def stop(self, *, session_id):
            return None

    async def scenario():
        events = EventBus()
        observed = []
        events.subscribe("*", observed.append)
        manager = FullDuplexSessionManager(
            recognizer=Recognizer(), synthesizer=Synthesizer(),
            player=Player(), event_bus=events,
            prosody_analyzer=VoiceProsodyService(event_bus=events),
        )
        await manager.start("voice-session")
        assert await manager.ingest_audio(buffer.getvalue()) == "test integration"
        while events.snapshot()["queued_total"]:
            await events.dispatch_once()
        emitted = [x.event_type for x in observed]
        assert "SpeechProsodyCues" in emitted
        assert "SpeechProsodyAnalysisCompleted" in emitted
        assert "SpeechTranscript" in emitted
        assert all("raw_audio" not in ev.payload for ev in observed)
        await manager.close()
        assert manager.snapshot().state == "idle"

    asyncio.run(scenario())
