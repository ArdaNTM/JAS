"""Permission-gated, read-only foreground desktop metadata.

This service never captures pixels, reads keyboard input, clicks, types, or
changes windows. Window titles are returned only to the authorized caller and
are deliberately omitted from EventBus telemetry.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import uuid4

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry,
    LatencyClass, ProviderType, QualityClass,
)
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationRequest, PermissionEngine, RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry


@dataclass(frozen=True, slots=True)
class ForegroundWindow:
    title: str
    process_name: str
    process_id: int
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if not self.title or len(self.title) > 512:
            raise ValueError("Window title must contain 1..512 characters")
        if not self.process_name or len(self.process_name) > 128:
            raise ValueError("Process name must contain 1..128 characters")
        if not 0 < self.process_id <= 0xFFFFFFFF:
            raise ValueError("Invalid process id")
        if any(abs(value) > 100_000 for value in (self.x, self.y)):
            raise ValueError("Window position exceeds bounds")
        if not 0 < self.width <= 32_768 or not 0 < self.height <= 32_768:
            raise ValueError("Window dimensions exceed bounds")


class ForegroundWindowProvider(Protocol):
    def snapshot(self) -> ForegroundWindow: ...


class WindowsForegroundWindowProvider:
    """Read the foreground HWND and basic metadata through documented Win32 APIs."""

    def snapshot(self) -> ForegroundWindow:
        if os.name != "nt":
            raise NotImplementedError("Foreground desktop metadata is supported on Windows only")
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            raise RuntimeError("No visible foreground window is available")

        title_length = min(512, max(0, user32.GetWindowTextLengthW(hwnd)))
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("Unable to read foreground window bounds")
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        handle = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not handle:
            raise RuntimeError("Unable to query foreground process")
        try:
            image_buffer = ctypes.create_unicode_buffer(1024)
            image_length = wintypes.DWORD(len(image_buffer))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, image_buffer, ctypes.byref(image_length)):
                raise RuntimeError("Unable to read foreground process name")
            process_name = image_buffer.value.replace("\\", "/").rsplit("/", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)

        title = re.sub(r"[\\x00-\\x1f\\x7f]", " ", title_buffer.value).strip()[:512]
        return ForegroundWindow(
            title=title or "(untitled)",
            process_name=process_name[:128],
            process_id=int(process_id.value),
            x=int(rect.left), y=int(rect.top),
            width=int(rect.right - rect.left), height=int(rect.bottom - rect.top),
        )


class DesktopAwarenessService:
    CAPABILITY_ID = "desktop.foreground.read"
    OPERATION_ID = "desktop.foreground.read"
    RESOURCE_SCOPE = "desktop:foreground"

    def __init__(self, *, provider: ForegroundWindowProvider,
                 permission_engine: PermissionEngine, event_bus: EventBus) -> None:
        self._provider = provider
        self._permissions = permission_engine
        self._events = event_bus

    def read_foreground(self, *, principal_id: str, session_id: str | None = None) -> ForegroundWindow:
        if not isinstance(principal_id, str) or not principal_id.strip() or len(principal_id) > 128:
            raise ValueError("A valid authenticated principal is required")
        decision = self._permissions.authorize(AuthorizationRequest(
            request_id=str(uuid4()), principal_id=principal_id,
            capability_id=self.CAPABILITY_ID, operation_id=self.OPERATION_ID,
            resource_scope=self.RESOURCE_SCOPE, risk_level=RiskLevel.MEDIUM,
            session_id=session_id,
        ))
        if decision.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError("Foreground desktop read was not authorized")
        snapshot = self._provider.snapshot()
        self._events.publish(KernelEvent(
            event_type="DesktopForegroundObserved",
            source_component="aura.desktop_awareness",
            correlation_id=session_id,
            payload={
                "principal_id": principal_id,
                "process_name": snapshot.process_name,
                "process_id": snapshot.process_id,
                "bounds": {"x": snapshot.x, "y": snapshot.y,
                           "width": snapshot.width, "height": snapshot.height},
                "window_title_in_event": False,
                "screen_pixels_captured": False,
                "input_injected": False,
            },
        ))
        return snapshot


def register_desktop_awareness_service(*, service_registry: ServiceRegistry,
        capability_registry: CapabilityRegistry, permission_engine: PermissionEngine,
        event_bus: EventBus, provider: ForegroundWindowProvider | None = None) -> DesktopAwarenessService:
    service = DesktopAwarenessService(
        provider=provider or WindowsForegroundWindowProvider(),
        permission_engine=permission_engine, event_bus=event_bus,
    )
    definition = ServiceDefinition(
        name="desktop-awareness", version="1.0.0", provider="aura.local",
        category=ServiceCategory.CORE,
        capabilities=frozenset({DesktopAwarenessService.CAPABILITY_ID}),
        tags=frozenset({"desktop", "read-only", "permission-gated"}),
    )
    service_registry.register(definition, service)
    capability_registry.register(CapabilityDefinition(
        capability_id=DesktopAwarenessService.CAPABILITY_ID,
        name="Read foreground desktop metadata", version="1.0.0",
        description="Read current foreground window metadata after explicit PermissionEngine ALLOW.",
        provider_id=definition.service_id, provider_type=ProviderType.SERVICE,
        category=CapabilityCategory.INFRASTRUCTURE, priority=50,
        latency_class=LatencyClass.LOW, quality_class=QualityClass.BASIC,
        risk_level="medium",
    ))
    return service
