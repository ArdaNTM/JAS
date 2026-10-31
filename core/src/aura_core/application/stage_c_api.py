"""Local authenticated Stage C control surface. HUD cannot approve an action."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aura_core.security.http_auth import authenticated_principal
from aura_core.application.stage_c_runtime import StageCError

router = APIRouter(prefix="/api/stage-c", tags=["stage-c"])


def _controller(request: Request):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Stage C requires loopback client")
    controller = getattr(request.app.state, "stage_c_controller", None)
    if controller is None:
        raise HTTPException(status_code=503, detail="Stage C disabled by default")
    return controller


class StartRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)
    confirmed: bool = False


@router.get("/status")
async def status(request: Request, principal: str = Depends(authenticated_principal)):
    controller = _controller(request)
    return {
        "enabled": True,
        "kill_switch_engaged": controller.ledger.stopped(),
        "max_actions": 8, "deadline_seconds": 120,
        "approval_authority": "separate_owner_control_plane",
        "browser_network_production_approved": False,
    }


@router.post("/runs", status_code=202)
async def start(body: StartRequest, request: Request,
                principal: str = Depends(authenticated_principal)):
    controller = _controller(request)
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Explicit user confirmation required")
    try:
        run_id = controller.ledger.create(principal, body.goal, "local_default")
        controller.start(run_id, principal)
    except StageCError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return controller.ledger.public(run_id, principal)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request,
                  principal: str = Depends(authenticated_principal)):
    controller = _controller(request)
    try:
        return controller.ledger.public(run_id, principal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@router.post("/runs/{run_id}/resume", status_code=202)
async def resume(run_id: str, request: Request,
                 principal: str = Depends(authenticated_principal)):
    controller = _controller(request)
    try:
        record = controller.ledger.get(run_id, principal)
        if record["state"] != "awaiting_approval":
            raise HTTPException(status_code=409, detail="Run is not awaiting separate Owner approval")
        # No approval material is provided by HUD. The Gateway will consume the
        # exact externally approved fingerprint already persisted for this step.
        controller.start(run_id, principal, resume=True)
        return controller.ledger.public(run_id, principal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except StageCError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/kill-switch")
async def kill_switch(request: Request,
                      principal: str = Depends(authenticated_principal)):
    controller = _controller(request)
    await controller.kill()
    return {"kill_switch_engaged": True,
            "reset_via_api": False, "note": "All future Stage C action dispatch denied"}
