from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from aura_core.application.events import EventConnection, LiveEventHub
from aura_core.security.local_only import is_local_websocket
from aura_core.security.ws_ticket import WebSocketTicketManager

router = APIRouter(tags=["live"])
event_hub = LiveEventHub()


@router.websocket("/ws/tasks/{task_id}")
async def task_events(
    websocket: WebSocket,
    task_id: UUID,
    ticket: str | None = Query(default=None),
) -> None:
    if not is_local_websocket(websocket):
        await websocket.close(code=1008, reason="Local-only access")
        return

    manager = getattr(websocket.app.state, "ws_ticket_manager", None)
    if not isinstance(manager, WebSocketTicketManager):
        await websocket.close(code=1011)
        return

    if not manager.verify(ticket or ""):
        await websocket.close(code=1008, reason="Invalid or expired ticket")
        return

    task_service = getattr(websocket.app.state, "task_service", None)
    if task_service is None:
        await websocket.close(code=1011, reason="Task service unavailable")
        return

    try:
        task_service.get_for_owner(str(task_id), "local_owner")
    except KeyError:
        await websocket.close(code=1008, reason="Unknown task")
        return

    await websocket.accept()
    connection = EventConnection()
    await event_hub.connect(task_id, connection)

    try:
        while True:
            event = await connection.receive()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        await event_hub.disconnect(task_id, connection)


@router.websocket("/api/ws/events")
async def global_events(
    websocket: WebSocket,
    ticket: str | None = Query(default=None),
) -> None:
    # Kernel event payloads and metadata have no safe public projection yet.
    # Do not expose the unfiltered global event history or live stream.
    await websocket.close(
        code=1008,
        reason="Global event stream is disabled in local-only mode",
    )
