from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from aura_core.security.local_only import require_local_http_request

router = APIRouter(tags=["live"])


@router.post("/api/ws/ticket")
async def issue_websocket_ticket(request: Request) -> dict[str, object]:
    require_local_http_request(request)

    manager = getattr(request.app.state, "ws_ticket_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="WebSocket authentication is not configured",
        )

    ticket = manager.issue()
    return {"ticket": ticket.value, "expires_at": ticket.expires_at}
