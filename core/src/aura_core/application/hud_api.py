"""Opt-in HUD events and one-time Windows-approved ScreenRead endpoint.

No UI-supplied principal, no auto-approval, no screenshot bytes in events.
The local native Yes/No prompt is an explicit human action distinct from
the requesting HTTP principal. Every call consumes an ApprovalStore record.
"""
from __future__ import annotations

import asyncio
import ctypes
import inspect
import logging
import sys
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aura_core.enterprise.approval_store import ApprovalStatus
from aura_core.kernel.events import KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest
from aura_core.security.http_auth import authenticated_principal
from aura_core.security.local_only import require_local_http_request

logger = logging.getLogger("aura_core.screenread")

router = APIRouter(prefix="/api/hud", tags=["local-hud"])


class HUDPanelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="object", pattern="^(object|research|notice)$")


class ScreenReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=400)
    confirmed: bool = False


def windows_operator_approval(prompt: str) -> bool:
    if sys.platform != "win32":
        return False
    # MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST.\n    # The explicit operator dialog must remain visible above the HUD.
    result = ctypes.windll.user32.MessageBoxW(
        None,
        "AURA ScreenRead: Allow ONE screenshot of your current desktop for "
        "LOCAL Ollama vision analysis?\n\n"
        "No screenshot will be stored or sent to the HUD.\n\n"
        "Question: " + prompt[:220],
        "AURA — ScreenRead approval",
        0x0004 | 0x0030 | 0x0100 | 0x00040000,
    )
    return result == 6


@router.post("/panel")
async def show_hud_panel(
    body: HUDPanelRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, str]:
    require_local_http_request(request)
    kernel = getattr(request.app.state, "kernel", None)
    bus = getattr(kernel, "event_bus", None)
    if bus is None:
        raise HTTPException(status_code=503, detail="HUD event bus unavailable")
    bus.publish(KernelEvent(
        event_type="HUDPanelShown",
        source_component="aura.hud",
        payload={"title": body.title, "kind": body.kind},
    ))
    return {"status": "display_queued"}


@router.post("/screen/read")
async def read_screen(
    body: ScreenReadRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    require_local_http_request(request)
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="ScreenRead requires explicit per-request consent")
    if not getattr(request.app.state, "screen_read_enabled", False):
        raise HTTPException(status_code=503, detail="ScreenRead is disabled")
    gateway = getattr(request.app.state, "mcp_gateway", None)
    store = getattr(request.app.state, "approval_store", None)
    kernel = getattr(request.app.state, "kernel", None)
    bus = getattr(kernel, "event_bus", None)
    if gateway is None or store is None or bus is None:
        raise HTTPException(status_code=503, detail="ScreenRead approval components unavailable")

    invocation = MCPGatewayRequest(
        request_id=str(uuid4()),
        principal_id=principal_id,
        capability_id="ScreenRead",
        operation_id="ScreenRead",
        resource_scope="local_default",
        risk_level=RiskLevel.HIGH,
        tool_name="screen_read",
        arguments={"prompt": body.prompt},
    )
    first = await gateway.invoke(invocation)
    if first.decision is not AuthorizationDecision.REQUIRE_APPROVAL or not first.approval_id:
        raise HTTPException(status_code=403, detail="ScreenRead authorization policy denied capture")

    # A visible Windows native dialog is the human approval boundary.
    # Never create/approve requests in unattended sessions.
    prompt_fn = getattr(request.app.state, "screen_read_operator_approval", windows_operator_approval)
    try:
        accepted = await asyncio.to_thread(prompt_fn, body.prompt)
        record = store.get(first.approval_id)
        if inspect.isawaitable(record):
            record = await record
        if record is None:
            raise RuntimeError("Approval record disappeared")
        outcome = ApprovalStatus.APPROVED if accepted else ApprovalStatus.DENIED
        decision = store.decide(
            first.approval_id,
            expected_version=record.version,
            approver_id="human:windows-interactive-dialog",
            decision=outcome,
        )
        if inspect.isawaitable(decision):
            await decision
        if not accepted:
            raise HTTPException(status_code=403, detail="Screen capture was declined by the operator")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Interactive screen approval unavailable") from exc

    from dataclasses import replace
    bus.publish(KernelEvent(
        event_type="HUDVisionScanStarted", source_component="aura.screenread",
        payload={"state": "scanning"},
    ))
    try:
        final = await gateway.invoke(replace(invocation, approval_id=first.approval_id))
    except Exception as exc:
        bus.publish(KernelEvent(
            event_type="HUDVisionScanEnded", source_component="aura.screenread",
            payload={"state": "failed"},
        ))
        # Fail closed. Log only the exception *type*, never screenshot bytes,
        # prompts, model responses, credentials or underlying remote URLs.
        logger.warning("ScreenRead dispatch failed: %s", type(exc).__name__)
        name = type(exc).__name__
        code = (
            "CAPTURE_DEPENDENCY_MISSING" if isinstance(exc, ImportError) or "Pillow" in str(exc)
            else "VISION_TIMEOUT" if "Timeout" in name
            else "VISION_ENDPOINT_FAILURE" if "HTTPStatusError" in name or "ConnectError" in name
            else "SCREENREAD_PROVIDER_FAILURE"
        )
        raise HTTPException(
            status_code=502,
            detail={"code": code, "message": "Local ScreenRead failed after authorization"},
        ) from exc
    if final.decision is not AuthorizationDecision.ALLOW or not isinstance(final.result, dict):
        bus.publish(KernelEvent(
            event_type="HUDVisionScanEnded", source_component="aura.screenread",
            payload={"state": "denied"},
        ))
        raise HTTPException(status_code=403, detail="ScreenRead approval was not consumed")
    bus.publish(KernelEvent(
        event_type="HUDVisionScanEnded", source_component="aura.screenread",
        payload={"state": "complete"},
    ))
    # Only the authenticated requesting UI receives description.
    return {
        "description": final.result.get("description", ""),
        "bounding_boxes_verified": False,
        "regions": final.result.get("regions", []),
        "authority": "untrusted_local_screen_perception",
    }
