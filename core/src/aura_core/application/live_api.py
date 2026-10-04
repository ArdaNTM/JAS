from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from aura_core.application.events import EventConnection, LiveEventHub
from aura_core.security.ws_ticket import WebSocketTicketManager


router = APIRouter(tags=["live"])

event_hub = LiveEventHub()


@router.websocket("/ws/tasks/{task_id}")
async def task_events(
    websocket: WebSocket,
    task_id: UUID,
    ticket: str | None = Query(default=None),
) -> None:
    manager = getattr(
        websocket.app.state,
        "ws_ticket_manager",
        None,
    )

    if not isinstance(manager, WebSocketTicketManager):
        await websocket.close(code=1011)
        return

    if not manager.verify(ticket or ""):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    connection = EventConnection()

    await event_hub.connect(
        task_id,
        connection,
    )

    try:
        while True:
            event = await connection.receive()

            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass

    except asyncio.CancelledError:
        raise

    finally:
        await event_hub.disconnect(
            task_id,
            connection,
        )


@router.websocket("/api/ws/events")
async def global_events(
    websocket: WebSocket,
    ticket: str | None = Query(default=None),
) -> None:
    manager = getattr(
        websocket.app.state,
        "ws_ticket_manager",
        None,
    )

    broker = getattr(
        websocket.app.state,
        "live_events",
        None,
    )

    if manager is None or broker is None:
        await websocket.close(code=1011)
        return

    if not manager.verify(ticket or ""):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        await websocket.send_json(
            {
                "event": "AURA_CONNECTED",
                "source": "live_event_gateway",
                "data": {
                    "status": "connected",
                },
            }
        )

        async for event in broker.stream():
            await websocket.send_json(event)

    except WebSocketDisconnect:
        pass

    except asyncio.CancelledError:
        raise