"""Runtime 117-feature index and authorized MCP Tool Center.

The source index mirrors the canonical governance tracker. A feature entry
documents an implemented bounded-v1 source module; it is NOT an executable
provider or permission grant. Only actual registered MCP tool definitions can
reach MCPGateway.invoke. Never infer tool access from the 117 status ledger.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry,
    CapabilityState, ProviderType,
)
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.security.http_auth import authenticated_principal


logger = logging.getLogger("aura_core.capability_center")
router = APIRouter(tags=["capability-center"])
_PHASES = {
    1: ("Bellek ve Güvenlik", CapabilityCategory.MEMORY),
    2: ("Ses ve Konuşma", CapabilityCategory.VOICE),
    3: ("Masaüstü ve Sistem", CapabilityCategory.AUTOMATION),
    4: ("Araştırma ve Kaynaklar", CapabilityCategory.RESEARCH),
    5: ("Kodlama ve Ajanlar", CapabilityCategory.CODING),
    6: ("Görüntü ve HUD", CapabilityCategory.VISION),
    7: ("Bilim ve Mühendislik", CapabilityCategory.REASONING),
    8: ("Akıllı Ev ve Robotik", CapabilityCategory.AUTOMATION),
    9: ("Kişisel Araçlar", CapabilityCategory.STORAGE),
}
# Existing actual MCP bindings only; no "117 tools" fabrication.
# Capability resolution below independently checks the live Registry/Provider.
_FEATURE_BINDINGS: dict[int, tuple[str, ...]] = {
    1: ("memory.core.read", "memory.archival.search"),
    2: ("memory.graph.query", "memory.graph.insert"),
    23: ("ScreenRead",),
    24: ("ScreenControl",),
    25: ("filesystem.read_test_data",),
    35: ("internet.search",),
    95: ("visualization.telemetry.read",),
}
_SOURCE_FILE = Path(__file__).with_name("feature_index.json")
_SOURCE_CAPABILITY = "aura.feature."


def feature_index() -> tuple[dict[str, Any], ...]:
    index = json.loads(_SOURCE_FILE.read_text(encoding="utf-8"))
    rows = index.get("features")
    if (index.get("schema") != "aura.runtime-feature-index.v1"
            or not isinstance(rows, list) or len(rows) != 117
            or [item.get("id") for item in rows] != list(range(1, 118))
            or any(item.get("phase") not in _PHASES
                   or not isinstance(item.get("name"), str)
                   or not item["name"] for item in rows)):
        raise ValueError("Invalid pinned 117-feature runtime index")
    return tuple(rows)


class FeatureCatalog:
    """Read-only metadata service registered in all three Kernel registries."""

    def __init__(self) -> None:
        self.features = feature_index()
        self._service_id: str | None = None

    def register(self, *, services: ServiceRegistry,
                 capabilities: CapabilityRegistry,
                 providers: ProviderRegistry) -> None:
        service = ServiceDefinition(
            name="feature_catalog", version="1.0.0", provider="aura",
            category=ServiceCategory.KERNEL,
            capabilities=frozenset(f"{_SOURCE_CAPABILITY}{f['id']:03d}"
                                   for f in self.features),
            tags=frozenset({"catalog", "read-only", "no-execution"}),
        )
        services.register(service, self)
        # ProviderRegistry records real FeatureCatalog only. The individual
        # metadata capabilities below never become callable MCP providers.
        providers.register(ProviderDefinition(
            provider_id=service.service_id, name="AURA canonical feature catalog",
            version="1.0.0", service_id=service.service_id,
            description="Read-only feature metadata, not a tool executor",
        ), self)
        self._service_id = service.service_id
        for feature in self.features:
            cap_id = f"{_SOURCE_CAPABILITY}{feature['id']:03d}"
            category = _PHASES[feature["phase"]][1]
            if 99 <= feature["id"] <= 107:
                category = CapabilityCategory.SECURITY
            if 91 <= feature["id"] <= 98:
                category = CapabilityCategory.VISUALIZATION
            capabilities.register(CapabilityDefinition(
                capability_id=cap_id,
                name=feature["name"], version="1.0.0",
                description="Governance feature source present; no execution binding",
                provider_id=service.service_id, provider_type=ProviderType.CORE,
                category=category, required_permissions=frozenset({cap_id}),
            ))
            # Fail closed: none of 117 informational records can be resolved as
            # an active executable capability. Existing real MCP registrations
            # remain separate and fully governed.
            capabilities.update_state(cap_id, service.service_id,
                                      CapabilityState.REGISTERED)
            capabilities.update_health(cap_id, service.service_id,
                                       available=False, healthy=False)

    def describe(self, kernel: Any) -> dict[str, Any]:
        cap_registry = getattr(kernel, "capability_registry", None)
        provider_registry = getattr(kernel, "provider_registry", None)
        if cap_registry is None or provider_registry is None:
            raise RuntimeError("Kernel registries not initialized")
        tools: list[dict[str, Any]] = []
        registered: set[str] = set()
        for record in cap_registry.records():
            definition = record.definition
            if definition.provider_type is not ProviderType.MCP or not definition.tool_name:
                continue
            try:
                provider = provider_registry.get(definition.provider_id)
            except KeyError:
                continue
            available = (
                record.available and record.healthy
                and provider.available and provider.healthy
            )
            registered.add(definition.capability_id)
            tools.append({
                "capability_id": definition.capability_id,
                "tool_name": definition.tool_name,
                "provider_id": definition.provider_id,
                "risk_level": definition.risk_level,
                "category": definition.category.value,
                "gateway_registered": bool(available),
                # A live authorization check is still required at dispatch.
                "authorization": "required_at_dispatch",
            })
        features = [{
            "id": feature["id"], "name": feature["name"],
            "category": _PHASES[feature["phase"]][0],
            "phase": feature["phase"],
            "status": "source_complete_bounded_v1",
            "runtime_status": ("mcp_registered"
                               if any(cap in registered for cap in _FEATURE_BINDINGS.get(feature["id"], ()))
                               else "metadata_only"),
            "mcp_capability_ids": [
                cap for cap in _FEATURE_BINDINGS.get(feature["id"], ()) if cap in registered
            ],
        } for feature in self.features]
        return {
            "schema": "aura.capability-center.v1",
            "feature_count": len(features),
            "features": features,
            "tools": sorted(tools, key=lambda item: item["capability_id"]),
            "policy": "metadata_is_not_authorization; every executable tool traverses MCPGateway",
        }


class CenterInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    capability_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z][a-zA-Z0-9._-]+$")
    resource_scope: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$")
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.get("/api/capabilities/center")
async def capability_center_list(
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, Any]:
    center = getattr(request.app.state, "feature_catalog", None)
    kernel = getattr(request.app.state, "kernel", None)
    if center is None or kernel is None:
        raise HTTPException(status_code=503, detail="Runtime capability catalog unavailable")
    return center.describe(kernel)


@router.post("/api/capabilities/center/invoke")
async def capability_center_invoke(
    data: CenterInvocation, request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, Any]:
    """Call an existing MCP tool by exact server-owned binding, never by URL.

    No UI-provided principal, operation, tool, risk, provider or policy. The
    gateway does the *only* authorization and approval consumption.
    """
    kernel = getattr(request.app.state, "kernel", None)
    gateway = getattr(request.app.state, "mcp_gateway", None)
    if kernel is None or gateway is None or kernel.capability_registry is None:
        raise HTTPException(status_code=503, detail="MCP Gateway unavailable")
    try:
        record = kernel.capability_registry.resolve(data.capability_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Executable MCP capability unavailable")
    definition = record.definition
    if definition.provider_type is not ProviderType.MCP or not definition.tool_name:
        raise HTTPException(status_code=403, detail="Feature metadata cannot execute tools")
    if len(json.dumps(data.arguments, allow_nan=False).encode("utf-8")) > 8192:
        raise HTTPException(status_code=422, detail="MCP arguments exceed input budget")
    try:
        response = await gateway.invoke(MCPGatewayRequest(
            request_id=str(uuid4()), principal_id=principal_id,
            capability_id=definition.capability_id,
            operation_id=definition.capability_id,
            tool_name=definition.tool_name,
            resource_scope=data.resource_scope,
            risk_level=RiskLevel(definition.risk_level),
            arguments=data.arguments,
            approval_id=data.approval_id,
        ))
    except (KeyError, LookupError, OSError, ConnectionError, TimeoutError):
        raise HTTPException(status_code=503, detail="MCP provider not available")
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid tool arguments")
    except Exception:
        logger.exception("Governed MCP dispatch failed", extra={
            "request_id": getattr(request.state, "request_id", None),
            "capability_id": definition.capability_id,
        })
        raise HTTPException(status_code=502, detail="MCP provider dispatch failed")
    if response.decision is not AuthorizationDecision.ALLOW:
        return {
            "status": "approval_required" if response.decision is AuthorizationDecision.REQUIRE_APPROVAL else "denied",
            "result": None,
            "approval_id": response.approval_id,
            "reason": "Gateway authorization or separate Owner approval required",
        }
    try:
        value = jsonable_encoder(response.result)
        if len(json.dumps(value, allow_nan=False).encode("utf-8")) > 32768:
            raise ValueError("output too large")
    except (ValueError, TypeError):
        raise HTTPException(status_code=502, detail="MCP output cannot be safely delivered")
    return {
        "status": "executed", "result": value, "approval_id": None,
        "reason": "MCP Gateway authorized",
    }
