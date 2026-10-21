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
})


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
        try:
            async for event in broker.stream():
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

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
