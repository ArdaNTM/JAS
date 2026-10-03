from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from .events import EventConnection, LiveEventHub
from ..security.auth import verify_ws_token

router = APIRouter()
event_hub = LiveEventHub()

@router.websocket("/ws/tasks/{task_id}")
async def task_events(
    websocket: WebSocket,
    task_id: UUID,
    token: str | None = Query(default=None),
) -> None:
    verify_ws_token(token)
    await websocket.accept()
    connection = EventConnection()
    await event_hub.connect(task_id, connection)
    try:
        while True:
            event = await connection.receive()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
