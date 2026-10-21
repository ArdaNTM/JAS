"""Local endpoints for explicitly consented screen perception and proactive delivery."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/perception", tags=["controlled-perception"])


def _require_local(request: Request) -> None:
    client = request.client
    host = client.host if client is not None else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Local client required")


class VisionRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(default="Describe the visible screen.", max_length=1000)
    confirmed: bool = False


class ProactiveRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    opted_in: bool = False


@router.post("/screen/describe")
async def describe_screen(body: VisionRequest, request: Request) -> dict[str, object]:
    _require_local(request)
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Explicit consent is required for every screen capture")
    service = getattr(request.app.state, "controlled_vision_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="No approved screen-capture and vision provider is configured")
    try:
        description = await service.describe_screen(
            principal_id=body.principal_id, prompt=body.prompt,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Screen capture consent was denied") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "description": description,
        "authority": "untrusted_perceptual_context_only",
        "tool_execution": "requires MCP Gateway and Permission Engine authorization",
    }


@router.post("/proactive/notify")
async def proactive_notify(body: ProactiveRequest, request: Request) -> dict[str, object]:
    _require_local(request)
    notifier = getattr(request.app.state, "proactive_notifier", None)
    if notifier is None:
        raise HTTPException(status_code=503, detail="Proactive notification service is unavailable")
    delivered = await notifier.notify(
        principal_id=body.principal_id, message=body.message,
        opted_in=body.opted_in, now=datetime.now().astimezone(),
    )
    return {
        "delivered": delivered,
        "reason": "delivered_or_allowed" if delivered else "not_opted_in_quiet_hours_or_budget_exhausted",
    }
