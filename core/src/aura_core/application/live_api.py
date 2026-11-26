from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from aura_core.application.events import LiveEventHub
from aura_core.application.live_events import LiveEventBroker
from aura_core.security.local_only import is_local_websocket
from aura_core.security.ws_ticket import WebSocketTicketManager

router = APIRouter(tags=["live"])
event_hub = LiveEventHub()  # legacy import compatibility; not an authority

_TASK_EVENTS = frozenset({"PlanStepStarted", "PlanStepCompleted", "TaskSucceeded", "TaskFailed"})


def project_task_event(event: dict, task_id: str) -> dict | None:
    """Only bounded execution state; never raw arguments, results or metadata."""
    data = event.get("data")
    if (event.get("event") not in _TASK_EVENTS or event.get("source") != "agent_executor"
            or not isinstance(data, dict) or data.get("task_id") != task_id):
        return None
    projected = {"task_id": task_id}
    if isinstance(data.get("step_id"), str):
        projected["step_id"] = data["step_id"][:128]
    if data.get("state") in {"succeeded", "failed", "cancelled", "skipped", "running", "pending"}:
        projected["state"] = data["state"]
    if type(data.get("attempts")) is int and 0 <= data["attempts"] <= 100:
        projected["attempts"] = data["attempts"]
    return {"id": str(event.get("id", ""))[:128], "event": event["event"],
            "source": "agent_executor", "timestamp": str(event.get("timestamp", ""))[:64],
            "task_id": task_id, "data": projected}


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

    if not task_service.owns_task(str(task_id), "local_owner"):
        await websocket.close(code=1008, reason="Unknown task")
        return

    broker = getattr(websocket.app.state, "live_events", None)
    if not isinstance(broker, LiveEventBroker):
        await websocket.close(code=1011, reason="Task events unavailable")
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
                event = project_task_event(pending.result(), str(task_id))
                pending = asyncio.create_task(anext(stream))
                if event is not None:
                    await websocket.send_json(event)
    except (WebSocketDisconnect, StopAsyncIteration):
        pass
    finally:
        for task in (pending, receive):
            task.cancel()
        await asyncio.gather(pending, receive, return_exceptions=True)
        await stream.aclose()


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
