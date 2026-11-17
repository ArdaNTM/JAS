"""Real dynamic, redacted SVG telemetry via EventBus and MCP Gateway.

Trusted Core events are projected only as bounded numeric latencies. No raw
event payloads, secrets, service identifiers or HTTP user strings are rendered.
The SVG is generated locally from validated numbers, not provider-owned markup.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.security.http_auth import authenticated_principal

_CAP = "visualization.telemetry.read"
_PROVIDER = "visualization.telemetry.local"
_TOOL = "read_latency_samples"
_SCOPE = "visualization/gateway-latency/read-only"
_MAX_SAMPLES = 120


class LiveChartDenied(PermissionError):
    """Explicit authorized, principal-bound telemetry read is required."""


class LiveChartUnavailable(RuntimeError):
    """Gateway or returned numeric telemetry is unavailable."""


@dataclass(frozen=True, slots=True)
class SVGChartEvidence:
    svg: str
    sample_count: int
    provider_id: str = _PROVIDER
    trust: str = "REDACTED_UNTRUSTED_TELEMETRY"
    read_only: bool = True


def _render_svg(samples: tuple[float, ...]) -> str:
    """Static trusted XML template; only bounded formatted floats enter paths."""
    if not samples:
        points = ""
    else:
        path = []
        for index, duration_ms in enumerate(samples):
            x = 40 + index * 560 / max(1, len(samples) - 1)
            y = 190 - min(duration_ms, 2000.0) * 150 / 2000.0
            path.append(f"{'M' if index == 0 else 'L'}{x:.1f},{y:.1f}")
        points = " ".join(path)
    # No SVG <script>, foreignObject, URLs, style, event handlers or dynamic text.
    # CSP on the HTTP surface separately forbids script/external references.
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 240" '
        'role="img" aria-label="Gateway latency in milliseconds">'
        '<rect width="640" height="240" fill="#111827"/>'
        '<path d="M40 24 V190 H600" fill="none" stroke="#6b7280" stroke-width="1"/>'
        '<path d="' + points + '" fill="none" stroke="#34d399" '
        'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
        '<text x="40" y="218" fill="#d1d5db" font-size="13">'
        'MCP Gateway latency (0-2000 ms)</text>'
        '</svg>'
    )


class LocalGatewayLatencyMCP:
    """Captures numeric RuntimeProfiler EventBus measurements only."""

    def __init__(self, event_bus: EventBus) -> None:
        if not isinstance(event_bus, EventBus):
            raise TypeError("Existing authoritative EventBus required")
        self._samples: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self._lock = RLock()
        self._unsubscribe = event_bus.subscribe(
            "Telemetry.MCPGatewayExecution", self._on_measurement,
        )

    def _on_measurement(self, event: KernelEvent) -> None:
        if (event.event_type != "Telemetry.MCPGatewayExecution"
                or event.source_component != "aura.mcp.gateway"):
            return
        duration = event.payload.get("duration_ms")
        if (type(duration) not in (int, float) or not math.isfinite(duration)
                or not 0 <= duration <= 60_000):
            return
        with self._lock:
            self._samples.append(round(float(duration), 3))

    def close(self) -> None:
        self._unsubscribe()

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL, description="Read redacted numeric Gateway latency samples",
            input_schema={"type": "object", "properties": {},
                          "required": [], "additionalProperties": False},
        ),)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict[str, object]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != _CAP
                or grant.tool_name != _TOOL or grant.risk_level != "low"
                or name != _TOOL):
            raise LiveChartDenied("Authorized MCP Gateway dispatch required")
        if arguments not in ({}, None):
            raise ValueError("Telemetry chart accepts no provider arguments")
        with self._lock:
            samples = tuple(self._samples)
        return {
            "samples": list(samples),
            "trust": "REDACTED_UNTRUSTED_TELEMETRY",
        }


def register_live_svg_chart(
    *, services: ServiceRegistry, providers: ProviderRegistry,
    capabilities: CapabilityRegistry, event_bus: EventBus,
) -> LocalGatewayLatencyMCP:
    """Opt-in registration; does not grant a user read permission."""
    if not (isinstance(services, ServiceRegistry)
            and isinstance(providers, ProviderRegistry)
            and isinstance(capabilities, CapabilityRegistry)
            and isinstance(event_bus, EventBus)):
        raise TypeError("Existing authoritative Core registries and EventBus required")
    if any(row.definition.provider_id == _PROVIDER for row in providers.records()):
        raise ValueError("Gateway chart provider already exists")
    if capabilities.providers(_CAP):
        raise ValueError("Gateway chart capability already exists")
    provider = LocalGatewayLatencyMCP(event_bus)
    try:
        service = services.register(ServiceDefinition(
            name="aura-local-gateway-chart", version="1.0.0",
            provider="mcp", category=ServiceCategory.MCP,
        ), object())
        providers.register(ProviderDefinition(
            provider_id=_PROVIDER, name="Redacted latency visualization",
            version="1.0.0", service_id=service.service_id,
        ), provider)
        capabilities.register(CapabilityDefinition(
            capability_id=_CAP, name="MCP Gateway latency visualization",
            version="1.0.0", description="Read-only numeric chart samples",
            provider_id=_PROVIDER, provider_type=ProviderType.MCP,
            category=CapabilityCategory.DIAGNOSTICS, risk_level="low",
            tool_name=_TOOL,
        ))
    except Exception:
        provider.close()
        raise
    return provider


def _principal(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or value.strip() != value
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError("Invalid authenticated telemetry principal")
    return value


class GovernedLiveSVGChart:
    """Pure SVG rendering after explicit per-read MCP Gateway authorization."""

    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCPGateway required")
        self._gateway = gateway
        self.principal_id = _principal(authenticated_principal_id)

    async def render(self) -> SVGChartEvidence:
        try:
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id="live-svg-chart:" + str(uuid4()),
                principal_id=self.principal_id,
                capability_id=_CAP, operation_id=_CAP,
                resource_scope=_SCOPE, risk_level=RiskLevel.LOW,
                tool_name=_TOOL, arguments={},
            ))
        except Exception as exc:
            raise LiveChartUnavailable("Gateway telemetry unavailable") from exc
        if response.decision is not AuthorizationDecision.ALLOW:
            raise LiveChartDenied("Explicit telemetry read policy required")
        value = response.result
        if (response.provider_id != _PROVIDER or not isinstance(value, dict)
                or value.get("status") == "failed"
                or value.get("trust") != "REDACTED_UNTRUSTED_TELEMETRY"):
            raise LiveChartUnavailable("Invalid Gateway telemetry result")
        raw = value.get("samples")
        if not isinstance(raw, list) or len(raw) > _MAX_SAMPLES:
            raise LiveChartUnavailable("Unsafe telemetry sample count")
        numbers: list[float] = []
        for item in raw:
            if (type(item) not in (int, float) or not math.isfinite(item)
                    or not 0 <= item <= 60_000):
                raise LiveChartUnavailable("Invalid telemetry sample")
            numbers.append(float(item))
        return SVGChartEvidence(svg=_render_svg(tuple(numbers)), sample_count=len(numbers))


live_svg_chart_router = APIRouter(tags=["governed-live-svg-chart"])


@live_svg_chart_router.get("/api/runtime/gateway-latency.svg")
async def read_gateway_latency_svg(
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> Response:
    """Actual authenticated HTTP SVG output, no client-controlled strings."""
    service = getattr(request.app.state, "live_svg_chart", None)
    if not isinstance(service, GovernedLiveSVGChart):
        raise HTTPException(status_code=503, detail="Live visualization not configured")
    if principal_id != service.principal_id:
        raise HTTPException(status_code=403, detail="Telemetry session scope mismatch")
    try:
        snapshot = await service.render()
    except LiveChartDenied as exc:
        raise HTTPException(status_code=403, detail="Telemetry read not authorized") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Live visualization unavailable") from exc
    return Response(
        content=snapshot.svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; script-src 'none'; object-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )
