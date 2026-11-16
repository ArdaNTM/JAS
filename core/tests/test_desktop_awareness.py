from __future__ import annotations

import asyncio

import pytest

from aura_core.application.desktop_awareness import (
    DesktopAwarenessService, ForegroundWindow, register_desktop_awareness_service,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry


class FakeWindowProvider:
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return ForegroundWindow("Private document title", "editor.exe", 42, 10, 20, 900, 700)


def make_service(*, allowed: bool):
    bus = EventBus()
    services = ServiceRegistry(bus)
    capabilities = CapabilityRegistry(services, bus)
    permissions = PermissionEngine(capabilities, bus)
    provider = FakeWindowProvider()
    service = register_desktop_awareness_service(
        service_registry=services, capability_registry=capabilities,
        permission_engine=permissions, event_bus=bus, provider=provider,
    )
    if allowed:
        permissions.add_policy(PermissionPolicy(
            policy_id="owner-desktop-read", policy_version="1",
            principal_id="local-user",
            capability_id=DesktopAwarenessService.CAPABILITY_ID,
            operation_id=DesktopAwarenessService.OPERATION_ID,
            resource_scope=DesktopAwarenessService.RESOURCE_SCOPE,
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
    return service, provider, bus


def test_default_deny_prevents_provider_access():
    service, provider, _ = make_service(allowed=False)
    with pytest.raises(PermissionError):
        service.read_foreground(principal_id="local-user")
    assert provider.calls == 0


def test_explicit_permission_reads_window_and_emits_redacted_event():
    service, provider, bus = make_service(allowed=True)
    events = []
    bus.subscribe("DesktopForegroundObserved", events.append)
    snapshot = service.read_foreground(principal_id="local-user", session_id="desktop-session")
    assert snapshot.title == "Private document title"
    assert provider.calls == 1
    assert asyncio.run(bus.dispatch_once()) is True
    payload = events[0].payload
    assert payload["process_name"] == "editor.exe"
    assert payload["window_title_in_event"] is False
    assert payload["screen_pixels_captured"] is False
    assert payload["input_injected"] is False
    assert "Private document title" not in str(payload)


def test_window_metadata_rejects_unbounded_values():
    with pytest.raises(ValueError):
        ForegroundWindow("x" * 513, "editor.exe", 42, 0, 0, 100, 100)
    with pytest.raises(ValueError):
        ForegroundWindow("title", "editor.exe", 42, 0, 0, 0, 100)


def test_requires_valid_principal_before_authorization():
    service, provider, _ = make_service(allowed=True)
    with pytest.raises(ValueError):
        service.read_foreground(principal_id="")
    assert provider.calls == 0
