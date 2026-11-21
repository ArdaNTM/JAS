"""Local authenticated, read-only discovery review endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from aura_core.security.http_auth import authenticated_principal
from aura_core.evolution.self_discovery import DiscoveryUnavailable

router = APIRouter(prefix="/api/evolution/discovery", tags=["self-discovery"])


def _engine(request: Request, principal: str):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Discovery requires loopback client")
    if principal != "local_owner":
        raise HTTPException(status_code=403, detail="Local Owner identity required")
    if str(getattr(request.app.state.storage_mode, "value",
                   request.app.state.storage_mode)).lower() != "local":
        raise HTTPException(status_code=503, detail="Local-only discovery unavailable")
    engine = getattr(request.app.state, "self_discovery", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Discovery not configured")
    return engine


@router.get("")
async def list_proposals(request: Request, principal: str = Depends(authenticated_principal)):
    engine = _engine(request, principal)
    return {"items": engine.proposals(20), "proposal_count": engine.count(),
            "mode": "review_only", "approval_granted": False,
            "activation_performed": False}


@router.post("/run")
async def run_discovery(request: Request, principal: str = Depends(authenticated_principal)):
    engine = _engine(request, principal)
    try:
        return await asyncio.wait_for(engine.run_once(full_scan=True), timeout=90)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="GitHub discovery timed out") from exc
    except DiscoveryUnavailable as exc:
        message = str(exc)[:180]
        status = 429 if "rate limit" in message.lower() else 503
        raise HTTPException(status_code=status, detail=message) from exc
    except (OSError, PermissionError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:180]) from exc
