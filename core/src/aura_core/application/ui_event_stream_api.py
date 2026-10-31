"""Local-only SSE projection for explicitly approved UI event types."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from aura_core.application.live_events import LiveEventBroker
from aura_core.security.local_only import require_local_http_request


router = APIRouter(tags=["ui-live-events"])

# Never expose the unrestricted Kernel EventBus to browser clients.
_UI_EVENT_ALLOWLIST = frozenset({
    "SpeechAudioReady",
    "SpeechAudioStop",
    "ProactiveNotificationReady",
    "HUDPanelShown",
    "HUDVisionScanStarted",
    "HUDVisionScanEnded",
})
SSE_HEARTBEAT_SECONDS = 15.0


@router.get("/api/events/stream")
async def ui_event_stream(request: Request) -> StreamingResponse:
    require_local_http_request(request)
    broker = getattr(request.app.state, "live_events", None)
    if not isinstance(broker, LiveEventBroker):
        # Keep the route available during degraded startup, but fail closed.
        async def unavailable() -> AsyncIterator[str]:
            yield "event: error\ndata: {\"error\":\"event_stream_unavailable\"}\n\n"
        return StreamingResponse(unavailable(), media_type="text/event-stream", status_code=503)

    async def stream() -> AsyncIterator[str]:
        connected_at = datetime.now(UTC)
        event_iterator = broker.stream().__aiter__()
        pending_event: asyncio.Task[dict[str, object]] | None = None
        try:
            # Tell clients immediately that the stream is established. This is an
            # SSE comment, not an application event, and does not expose Kernel events.
            yield ": connected\n\n"
            pending_event = asyncio.create_task(event_iterator.__anext__())
            while True:
                done, _ = await asyncio.wait(
                    {pending_event},
                    timeout=SSE_HEARTBEAT_SECONDS,
                )
                if not done:
                    if await request.is_disconnected():
                        break
                    # Heartbeats make idle connections observable and prevent
                    # intermediaries from treating a healthy stream as stalled.
                    yield ": keep-alive\n\n"
                    continue

                try:
                    event = pending_event.result()
                except StopAsyncIteration:
                    break
                pending_event = asyncio.create_task(event_iterator.__anext__())

                if await request.is_disconnected():
                    break
                if event.get("event") not in _UI_EVENT_ALLOWLIST:
                    continue
                try:
                    event_time = datetime.fromisoformat(str(event.get("timestamp", "")))
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=UTC)
                    if event_time < connected_at:
                        continue
                except ValueError:
                    continue
                payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"data: {payload}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            if pending_event is not None and not pending_event.done():
                pending_event.cancel()
                await asyncio.gather(pending_event, return_exceptions=True)
            close_iterator = getattr(event_iterator, "aclose", None)
            if close_iterator is not None:
                await close_iterator()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
