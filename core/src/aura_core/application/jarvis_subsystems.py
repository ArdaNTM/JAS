"""Compose additional JARVIS providers without changing Gateway or Owner trust."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aura_core.application.briefing_service import (
    BriefingService, BRIEFING_CAP, BRIEFING_TOOL, BRIEFING_SCOPE, BRIEFING_PROVIDER,
)
from aura_core.application.iot_gateway import load_smart_devices, project_iot_event
from aura_core.application.live_events import LiveEventBroker
from aura_core.application.semantic_consolidation import (
    SemanticConsolidationMCP, local_consolidation_model,
    CONSOLIDATE_CAP, CONSOLIDATE_TOOL, CONSOLIDATE_SCOPE, CONSOLIDATE_PROVIDER,
)
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.events import KernelEvent
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionPolicy, RiskLevel,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.mcp.provider import ProviderDefinition
from aura_core.security.face_id import (
    FaceVerificationGate, OpenCVFaceVerifier, FACE_CAP, FACE_TOOL, FACE_SCOPE, FACE_PROVIDER,
)
from aura_core.security.http_auth import authenticated_principal
from aura_core.security.local_only import require_local_http_request, is_local_websocket
from aura_core.security.ws_ticket import WebSocketTicketManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jarvis", tags=["jarvis-local-subsystems"])
_IOT_TICKET_SUBJECT = "aura-iot"


def _enabled(name: str) -> bool:
    return os.getenv(name, "0").strip().casefold() in {"1", "true", "yes", "on"}


def register_jarvis_provider(kernel, provider_id: str, provider, definitions):
    """Registry publication is not itself an authorization grant."""
    service = kernel.service_registry.register(ServiceDefinition(
        name=provider_id, version="1.0.0", provider="aura",
        category=ServiceCategory.MCP, capabilities=frozenset(d[0] for d in definitions),
    ), provider)
    kernel.provider_registry.register(ProviderDefinition(
        provider_id=provider_id, name=provider_id, version="1.0.0", service_id=service.service_id,
    ), provider)
    for cap, tool, risk, category in definitions:
        kernel.capability_registry.register(CapabilityDefinition(
            capability_id=cap, name=tool, version="1.0.0",
            description="Local opt-in Gateway-governed JARVIS capability",
            provider_id=provider_id, provider_type=ProviderType.MCP,
            category=category, tool_name=tool, risk_level=risk,
            required_permissions=frozenset({cap}),
        ))


def _policy(kernel, cap: str, scope: str, *, level: AuthorizationLevel, decision: AuthorizationDecision):
    # Only for explicitly enabled local features. Existing deny and enterprise
    # policy bundle remain authoritative; physical/camera actions require approval.
    kernel.permission_engine.add_policy(PermissionPolicy(
        policy_id="local-owner:jarvis:" + cap, policy_version="1.0.0",
        principal_id="local_owner", capability_id=cap, operation_id=cap,
        resource_scope=scope, authorization_level=level, decision=decision,
    ))


async def _invoke(gateway, principal, cap, tool, scope, risk, arguments, approval_id=None):
    return await gateway.invoke(MCPGatewayRequest(
        request_id="jarvis:" + str(uuid4()), principal_id=principal,
        capability_id=cap, operation_id=cap, resource_scope=scope,
        risk_level=risk, tool_name=tool, arguments=arguments, approval_id=approval_id,
    ))


def compose_jarvis_subsystems(app, *, kernel, gateway, tasks, workflows, memory,
                              local: bool, principal: str, bearer_token, approval_store):
    app.state.jarvis_briefing = None
    app.state.jarvis_face = None
    app.state.jarvis_iot = {}
    app.include_router(router)
    if not local or principal != "local_owner" or not bearer_token:
        return

    if _enabled("AURA_MORNING_BRIEFING_ENABLED"):
        briefing = BriefingService(tasks, workflows, memory)
        register_jarvis_provider(kernel, BRIEFING_PROVIDER, briefing,
            ((BRIEFING_CAP, BRIEFING_TOOL, "low", CapabilityCategory.PLANNING),))
        _policy(kernel, BRIEFING_CAP, BRIEFING_SCOPE, level=AuthorizationLevel.READ,
                decision=AuthorizationDecision.ALLOW)
        app.state.jarvis_briefing = briefing

    reflection = getattr(app.state, "background_thinking", None)
    if reflection is not None and _enabled("AURA_BACKGROUND_THINKING_ENABLED"):
        try:
            model = local_consolidation_model(
                os.getenv("AURA_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                os.getenv("AURA_SEMANTIC_CONSOLIDATION_MODEL", "qwen3"),
            )
        except ValueError:
            logger.warning("Semantic consolidation disabled: invalid local inference configuration")
        else:
            provider = SemanticConsolidationMCP(
                memory.store, model, principal_id=principal,
                is_idle=lambda: time.monotonic() - app.state.last_user_activity >= max(300, reflection.idle_seconds),
            )
            register_jarvis_provider(kernel, CONSOLIDATE_PROVIDER, provider,
                ((CONSOLIDATE_CAP, CONSOLIDATE_TOOL, "medium", CapabilityCategory.MEMORY),))
            _policy(kernel, CONSOLIDATE_CAP, CONSOLIDATE_SCOPE, level=AuthorizationLevel.WRITE,
                    decision=AuthorizationDecision.ALLOW)

            async def consolidate():
                response = await _invoke(gateway, principal, CONSOLIDATE_CAP, CONSOLIDATE_TOOL,
                                         CONSOLIDATE_SCOPE, RiskLevel.MEDIUM, {})
                if response.decision is not AuthorizationDecision.ALLOW:
                    return 0
                if response.provider_id != CONSOLIDATE_PROVIDER or not isinstance(response.result, dict):
                    raise RuntimeError("Invalid semantic consolidation response")
                saved = response.result.get("saved")
                if type(saved) is not int or not 0 <= saved <= 3:
                    raise RuntimeError("Invalid semantic consolidation count")
                if saved:
                    kernel.event_bus.publish(KernelEvent(
                        event_type="JarvisSemanticConsolidated", source_component="aura.jarvis.memory",
                        payload={"principal_id": principal, "saved": saved, "untrusted": True},
                    ))
                return saved

            reflection.semantic_consolidation = consolidate

    if _enabled("AURA_FACE_VERIFICATION_ENABLED") and approval_store is not None:
        gate = FaceVerificationGate(OpenCVFaceVerifier(
            reference=os.getenv("AURA_FACE_REFERENCE_PATH", ""),
            detector=os.getenv("AURA_FACE_DETECTOR_PATH", ""),
            recognizer=os.getenv("AURA_FACE_RECOGNIZER_PATH", ""),
            camera_index=int(os.getenv("AURA_FACE_CAMERA_INDEX", "0")),
        ))
        register_jarvis_provider(kernel, FACE_PROVIDER, gate,
            ((FACE_CAP, FACE_TOOL, "high", CapabilityCategory.SECURITY),))
        _policy(kernel, FACE_CAP, FACE_SCOPE, level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
                decision=AuthorizationDecision.REQUIRE_APPROVAL)
        app.state.jarvis_face = gate

    if _enabled("AURA_IOT_ENABLED"):
        if approval_store is None:
            raise RuntimeError("IoT requires existing durable Owner approval store")
        devices = load_smart_devices(event_bus=kernel.event_bus, face_gate=app.state.jarvis_face)
        for device in devices.values():
            register_jarvis_provider(kernel, device.provider_id, device, (
                (device.actuate_capability, "physical_actuate", "critical", CapabilityCategory.AUTOMATION),
                (device.status_capability, "physical_sensor", "high", CapabilityCategory.AUTOMATION),
            ))
            for cap in (device.actuate_capability, device.status_capability):
                _policy(kernel, cap, device.scope, level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
                        decision=AuthorizationDecision.REQUIRE_APPROVAL)
        app.state.jarvis_iot = devices


def _local_owner(request: Request, principal: str) -> None:
    require_local_http_request(request)
    if principal != "local_owner":
        raise HTTPException(403, "Local Owner required")


async def _response(request, principal, cap, tool, scope, risk, arguments, provider_id, approval_id=None):
    _local_owner(request, principal)
    gateway = getattr(request.app.state, "mcp_gateway", None)
    if gateway is None:
        raise HTTPException(503, "Gateway unavailable")
    try:
        response = await _invoke(gateway, principal, cap, tool, scope, risk, arguments, approval_id)
    except PermissionError as exc:
        raise HTTPException(403, "Provider rejected scoped request") from exc
    except Exception as exc:
        raise HTTPException(503, "Local provider unavailable") from exc
    if response.decision is AuthorizationDecision.REQUIRE_APPROVAL:
        return JSONResponse(status_code=202, content={
            "status": "approval_required", "approval_id": response.approval_id,
        }, headers={"Cache-Control": "no-store"})
    if response.decision is not AuthorizationDecision.ALLOW:
        raise HTTPException(403, "Gateway authorization denied")
    if (response.provider_id != provider_id or response.tool_name != tool
            or not isinstance(response.result, dict) or response.result.get("status") == "failed"):
        raise HTTPException(503, "Invalid local provider response")
    return JSONResponse(content=response.result, headers={"Cache-Control": "private, no-store"})


@router.get("/briefing")
async def morning_briefing(request: Request, principal: str = Depends(authenticated_principal)):
    _local_owner(request, principal)
    if getattr(request.app.state, "jarvis_briefing", None) is None:
        raise HTTPException(503, "Morning briefing disabled")
    return await _response(request, principal, BRIEFING_CAP, BRIEFING_TOOL,
                           BRIEFING_SCOPE, RiskLevel.LOW, {}, BRIEFING_PROVIDER)


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.post("/face/verify")
async def verify_face(body: ApprovalInput, request: Request,
                      principal: str = Depends(authenticated_principal)):
    _local_owner(request, principal)
    if getattr(request.app.state, "jarvis_face", None) is None:
        return {"status": "unavailable", "authority_granted": False, "owner_signature_verified": False}
    return await _response(request, principal, FACE_CAP, FACE_TOOL, FACE_SCOPE,
                           RiskLevel.HIGH, {}, FACE_PROVIDER, body.approval_id)


class DeviceCommand(ApprovalInput):
    action: Literal["on", "off", "status"]
    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@router.post("/iot/{device_id}/command")
async def device_command(device_id: str, body: DeviceCommand, request: Request,
                         principal: str = Depends(authenticated_principal)):
    _local_owner(request, principal)
    device = getattr(request.app.state, "jarvis_iot", {}).get(device_id)
    if device is None:
        raise HTTPException(404, "Device not provisioned")
    if body.action == "status":
        cap, tool, risk, arguments = device.status_capability, "physical_sensor", RiskLevel.HIGH, {"device_id": device_id}
    else:
        cap, tool, risk = device.actuate_capability, "physical_actuate", RiskLevel.CRITICAL
        arguments = {"device_id": device_id, "command": body.action,
                     "value": int(body.action == "on"), "request_id": body.request_id}
    return await _response(request, principal, cap, tool, device.scope, risk,
                           arguments, device.provider_id, body.approval_id)


@router.post("/iot/ticket")
async def iot_ticket(request: Request, principal: str = Depends(authenticated_principal)):
    _local_owner(request, principal)
    manager = getattr(request.app.state, "ws_ticket_manager", None)
    if not isinstance(manager, WebSocketTicketManager) or not getattr(request.app.state, "jarvis_iot", {}):
        raise HTTPException(503, "IoT event stream unavailable")
    ticket = manager.issue(subject=_IOT_TICKET_SUBJECT)
    return JSONResponse({"ticket": ticket.value, "expires_at": ticket.expires_at},
                        headers={"Cache-Control": "no-store"})


@router.websocket("/iot/events")
async def iot_events(websocket: WebSocket, ticket: str = ""):
    manager = getattr(websocket.app.state, "ws_ticket_manager", None)
    principal = getattr(websocket.app.state, "http_principal_id", None)
    broker = getattr(websocket.app.state, "live_events", None)
    if (not is_local_websocket(websocket) or principal != "local_owner"
            or not getattr(websocket.app.state, "jarvis_iot", {})
            or not isinstance(manager, WebSocketTicketManager)
            or not manager.verify(ticket, subject=_IOT_TICKET_SUBJECT)
            or not isinstance(broker, LiveEventBroker)):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    stream = broker.stream()
    pending = asyncio.create_task(anext(stream))
    receive = asyncio.create_task(websocket.receive())
    try:
        while True:
            done, _ = await asyncio.wait({pending, receive}, return_when=asyncio.FIRST_COMPLETED)
            if receive in done:
                if receive.result().get("type") == "websocket.disconnect":
                    break
                receive = asyncio.create_task(websocket.receive())
            if pending in done:
                event = project_iot_event(pending.result(), principal)
                pending = asyncio.create_task(anext(stream))
                if event is not None and event["data"]["device_id"] in websocket.app.state.jarvis_iot:
                    await websocket.send_json(event)
    except (WebSocketDisconnect, StopAsyncIteration):
        pass
    finally:
        for task in (pending, receive):
            task.cancel()
        await asyncio.gather(pending, receive, return_exceptions=True)
        await stream.aclose()
