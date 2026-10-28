from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from aura_core.application import ui_event_stream_api
from aura_core.application.live_events import LiveEventBroker
from aura_core.kernel.events import KernelEvent


class FakeLocalRequest:
    def __init__(self, broker: LiveEventBroker) -> None:
        self.client = SimpleNamespace(host="127.0.0.1")
        self.headers = {"host": "127.0.0.1:8765"}
        self.app = SimpleNamespace(state=SimpleNamespace(live_events=broker))

    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_sse_sends_initial_comment_heartbeat_and_allowlisted_events(monkeypatch) -> None:
    monkeypatch.setenv("AURA_CORE_PORT", "8765")
    monkeypatch.setattr(ui_event_stream_api, "SSE_HEARTBEAT_SECONDS", 0.01)
    broker = LiveEventBroker()
    response = await ui_event_stream_api.ui_event_stream(FakeLocalRequest(broker))
    iterator = response.body_iterator

    try:
        first = await anext(iterator)
        assert first == ": connected\n\n"

        heartbeat = await asyncio.wait_for(anext(iterator), timeout=0.2)
        assert heartbeat == ": keep-alive\n\n"

        broker.publish(KernelEvent(
            event_type="SpeechAudioReady",
            source_component="test",
            payload={"principal_id": "local_owner", "session_id": "test-session"},
        ))
        event_frame = await asyncio.wait_for(anext(iterator), timeout=0.2)
        assert event_frame.startswith("data: ")
        assert '"event":"SpeechAudioReady"' in event_frame
    finally:
        await iterator.aclose()


@pytest.mark.asyncio
async def test_sse_does_not_forward_non_allowlisted_kernel_events(monkeypatch) -> None:
    monkeypatch.setenv("AURA_CORE_PORT", "8765")
    monkeypatch.setattr(ui_event_stream_api, "SSE_HEARTBEAT_SECONDS", 0.01)
    broker = LiveEventBroker()
    response = await ui_event_stream_api.ui_event_stream(FakeLocalRequest(broker))
    iterator = response.body_iterator

    try:
        assert await anext(iterator) == ": connected\n\n"
        broker.publish(KernelEvent(
            event_type="TaskCreated",
            source_component="test",
            payload={"task_id": "private-task"},
        ))
        # The task event is deliberately filtered; the next frame is a heartbeat.
        frame = await asyncio.wait_for(anext(iterator), timeout=0.2)
        assert frame == ": keep-alive\n\n"
    finally:
        await iterator.aclose()
