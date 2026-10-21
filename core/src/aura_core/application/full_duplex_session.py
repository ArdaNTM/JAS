"""Full-duplex voice, controlled vision, and governed proactive session primitives.

Hardware/model backends are injected protocols. TTS tool execution must use the MCP
Gateway; this module does not treat speech, vision, or proactive signals as authority.
"""
from __future__ import annotations

import asyncio
import base64
import io
import tempfile
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel


class SpeechRecognizer(Protocol):
    async def transcribe(self, audio: bytes, *, session_id: str) -> str: ...


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str, *, session_id: str) -> Any: ...


class AudioPlayer(Protocol):
    async def play(self, audio: Any, *, session_id: str) -> None: ...

    async def stop(self, *, session_id: str) -> None: ...


class FasterWhisperRecognizer:
    """Lazy local STT adapter; audio is decoded from an in-memory payload."""

    def __init__(self, *, model_size: str = "small", device: str = "cpu", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._lock = asyncio.Lock()

    async def transcribe(self, audio: bytes, *, session_id: str) -> str:
        if not audio or len(audio) > 20_000_000:
            raise ValueError("Audio payload is empty or exceeds the 20 MB limit")
        async with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel
                self._model = await asyncio.to_thread(
                    WhisperModel, self._model_size, device=self._device,
                    compute_type=self._compute_type,
                )
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=True) as handle:
                handle.write(audio)
                handle.flush()
                segments, _info = await asyncio.to_thread(
                    self._model.transcribe, handle.name, beam_size=1,
                    vad_filter=True,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
        return text[:8000]


class EventBusAudioPlayer:
    """Deliver TTS audio to the authorized local UI over the existing event bridge."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus

    async def play(self, audio: Any, *, session_id: str) -> None:
        payload = getattr(audio, "structuredContent", None)
        if not isinstance(payload, Mapping):
            payload = audio if isinstance(audio, Mapping) else None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("audio_base64"), str):
            raise RuntimeError("TTS provider returned no structured audio payload")
        encoded = payload["audio_base64"]
        if len(encoded) > 16_000_000:
            raise ValueError("Synthesized audio exceeds configured delivery limit")
        # Validate before emitting; the browser remains responsible for playback.
        base64.b64decode(encoded, validate=True)
        self._events.publish(KernelEvent(
            event_type="SpeechAudioReady", source_component="aura.audio_player",
            correlation_id=session_id,
            payload={"session_id": session_id, "mime_type": payload.get("mime_type", "audio/wav"),
                     "audio_base64": encoded},
        ))

    async def stop(self, *, session_id: str) -> None:
        self._events.publish(KernelEvent(
            event_type="SpeechAudioStop", source_component="aura.audio_player",
            correlation_id=session_id, payload={"session_id": session_id},
        ))


class ScreenCapture(Protocol):
    async def capture(self) -> bytes: ...


class VisionProvider(Protocol):
    async def describe(self, image: bytes, *, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class SpeechSnapshot:
    session_id: str
    state: str
    last_transcript: str
    generation: int


class GatewaySpeechSynthesizer:
    """TTS adapter which always crosses the Kernel MCP authorization boundary."""

    def __init__(
        self, *, gateway: MCPGateway, principal_id: str,
        capability_id: str = "speech.synthesize",
        operation_id: str = "speech.synthesize",
        tool_name: str = "synthesize", resource_scope: str = "local_default",
    ) -> None:
        self._gateway = gateway
        self._principal = principal_id
        self._capability = capability_id
        self._operation = operation_id
        self._tool = tool_name
        self._scope = resource_scope

    async def synthesize(self, text: str, *, session_id: str) -> Any:
        if not text.strip() or len(text) > 8000:
            raise ValueError("Speech text is empty or exceeds the configured bound")
        response = await self._gateway.invoke(MCPGatewayRequest(
            request_id=str(uuid4()), principal_id=self._principal,
            capability_id=self._capability, operation_id=self._operation,
            resource_scope=self._scope, risk_level=RiskLevel.LOW,
            tool_name=self._tool, arguments={"text": text},
            session_id=session_id,
        ))
        if response.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError(f"TTS authorization denied: {response.reason}")
        return response.result


class FullDuplexSessionManager:
    """Single-session speech state machine with interruptible TTS playback."""

    def __init__(
        self, *, recognizer: SpeechRecognizer, synthesizer: SpeechSynthesizer,
        player: AudioPlayer, event_bus: EventBus | None = None,
    ) -> None:
        self._recognizer = recognizer
        self._synthesizer = synthesizer
        self._player = player
        self._events = event_bus
        self._session_id: str | None = None
        self._state = "idle"
        self._transcript = ""
        self._generation = 0
        self._playback: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self, session_id: str) -> SpeechSnapshot:
        if not session_id.strip():
            raise ValueError("session_id is required")
        async with self._lock:
            if self._state != "idle" and self._session_id != session_id:
                raise RuntimeError("A different speech session is already active")
            self._session_id = session_id
            self._state = "listening"
            self._emit("SpeechSessionStarted", {})
            return self.snapshot()

    async def ingest_audio(self, audio: bytes) -> str:
        if not audio:
            raise ValueError("audio payload is empty")
        session_id = self._require_session()
        # A fresh incoming audio chunk interrupts ongoing speech immediately.
        await self.interrupt(reason="user_barge_in", keep_listening=True)
        async with self._lock:
            self._state = "recognizing"
        try:
            transcript = (await self._recognizer.transcribe(audio, session_id=session_id)).strip()
        except Exception:
            async with self._lock:
                self._state = "listening"
            raise
        async with self._lock:
            self._transcript = transcript[:8000]
            self._state = "listening"
            self._emit("SpeechTranscript", {"characters": len(self._transcript)})
        return self._transcript

    async def speak(self, text: str) -> None:
        session_id = self._require_session()
        async with self._lock:
            self._generation += 1
            generation = self._generation
            previous = self._playback
            if previous is not None and not previous.done():
                previous.cancel()
                self._playback = None
            self._state = "speaking"
            self._emit("SpeechPlaybackStarted", {"generation": generation})
        if previous is not None and not previous.done():
            await asyncio.gather(previous, return_exceptions=True)

        async def playback() -> None:
            audio = await self._synthesizer.synthesize(text, session_id=session_id)
            async with self._lock:
                if generation != self._generation or self._state != "speaking":
                    return
            await self._player.play(audio, session_id=session_id)

        task = asyncio.create_task(playback())
        async with self._lock:
            self._playback = task
        try:
            await task
        except asyncio.CancelledError:
            raise
        finally:
            async with self._lock:
                if self._playback is task:
                    self._playback = None
                    if self._state == "speaking":
                        self._state = "listening"
                        self._emit("SpeechPlaybackCompleted", {"generation": generation})

    async def interrupt(self, *, reason: str = "interrupted", keep_listening: bool = True) -> None:
        session_id = self._session_id
        async with self._lock:
            self._generation += 1
            task = self._playback
            self._playback = None
            if self._state != "idle":
                self._state = "listening" if keep_listening else "idle"
            self._emit("SpeechPlaybackInterrupted", {"reason": reason})
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if session_id is not None:
            try:
                await self._player.stop(session_id=session_id)
            except Exception:
                # Player failure cannot restore stale playback or grant authority.
                self._emit("SpeechPlayerStopFailed", {})

    async def close(self) -> None:
        await self.interrupt(reason="session_closed", keep_listening=False)
        async with self._lock:
            self._state = "idle"
            self._session_id = None
            self._transcript = ""

    def snapshot(self) -> SpeechSnapshot:
        return SpeechSnapshot(
            session_id=self._session_id or "", state=self._state,
            last_transcript=self._transcript, generation=self._generation,
        )

    def _require_session(self) -> str:
        if self._session_id is None or self._state == "idle":
            raise RuntimeError("Speech session is not active")
        return self._session_id

    def _emit(self, event_type: str, extra: Mapping[str, object]) -> None:
        if self._events is not None:
            self._events.publish(KernelEvent(
                event_type=event_type, source_component="aura.full_duplex_session",
                correlation_id=self._session_id,
                payload={"session_id": self._session_id, "state": self._state, **extra},
            ))


class ControlledVisionService:
    """Screen perception gated by explicit user consent for every capture."""

    def __init__(
        self, *, capture: ScreenCapture, provider: VisionProvider,
        consent: Callable[[str], bool] | Callable[[str], Any], max_image_bytes: int = 8_000_000,
    ) -> None:
        if max_image_bytes < 1:
            raise ValueError("max_image_bytes must be positive")
        self._capture = capture
        self._provider = provider
        self._consent = consent
        self._max_bytes = max_image_bytes

    async def describe_screen(self, *, principal_id: str, prompt: str = "Describe the visible screen.") -> str:
        if not principal_id.strip() or len(prompt) > 1000:
            raise ValueError("Invalid principal or vision prompt")
        allowed = self._consent(principal_id)
        if asyncio.iscoroutine(allowed):
            allowed = await allowed
        if not allowed:
            raise PermissionError("Screen capture requires explicit user consent")
        image = await self._capture.capture()
        if not image or len(image) > self._max_bytes:
            raise ValueError("Screen image is empty or exceeds configured bounds")
        # Image content is untrusted context, never authorization or instructions.
        return (await self._provider.describe(image, prompt=prompt[:1000]))[:8000]


class ProactiveNotifier:
    """Quiet-hours and budget aware opt-in notification gate."""

    def __init__(
        self, *, deliver, budget_per_day: int = 5,
        quiet_start: time = time(22, 0), quiet_end: time = time(8, 0),
    ) -> None:
        if budget_per_day < 0:
            raise ValueError("budget_per_day cannot be negative")
        self._deliver = deliver
        self._budget = budget_per_day
        self._quiet_start = quiet_start
        self._quiet_end = quiet_end
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    async def notify(
        self, *, principal_id: str, message: str, opted_in: bool,
        now: datetime | None = None,
    ) -> bool:
        if not principal_id.strip() or not message.strip() or len(message) > 2000:
            return False
        if not opted_in:
            return False
        local_now = now or datetime.now().astimezone()
        clock = local_now.timetz().replace(tzinfo=None)
        if self._in_quiet_hours(clock):
            return False
        day = local_now.date().isoformat()
        async with self._lock:
            key = (principal_id, day)
            if self._counts.get(key, 0) >= self._budget:
                return False
            self._counts[key] = self._counts.get(key, 0) + 1
        try:
            await self._deliver(principal_id=principal_id, message=message)
        except Exception:
            async with self._lock:
                self._counts[key] = max(0, self._counts.get(key, 1) - 1)
            return False
        return True

    def _in_quiet_hours(self, clock: time) -> bool:
        if self._quiet_start == self._quiet_end:
            return True
        if self._quiet_start < self._quiet_end:
            return self._quiet_start <= clock < self._quiet_end
        return clock >= self._quiet_start or clock < self._quiet_end
