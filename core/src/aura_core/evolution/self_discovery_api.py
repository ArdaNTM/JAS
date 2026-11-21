"""Authenticated, local-only read-only public discovery endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request
from aura_core.security.http_auth import authenticated_principal

router = APIRouter(prefix="/api/evolution/discovery", tags=["evolution-discovery"])


def engine(request: Request, principal_id: str):
    client = request.client.host if request.client else ""
    if client not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Local discovery only")
    active = getattr(request.app.state, "self_discovery_engine", None)
    if active is None:
        raise HTTPException(status_code=503, detail="Local read-only discovery is not configured")
    if principal_id != active.principal_id:
        raise HTTPException(status_code=403, detail="Discovery scope mismatch")
    return active


@router.get("/proposals")
async def list_proposals(
    request: Request, principal_id: str = Depends(authenticated_principal)
):
    active = engine(request, principal_id)
    return {**active.status(), "items": active.proposals(20)}


@router.post("/run")
async def run_discovery(
    request: Request, principal_id: str = Depends(authenticated_principal)
):
    active = engine(request, principal_id)
    return await active.run_once()
