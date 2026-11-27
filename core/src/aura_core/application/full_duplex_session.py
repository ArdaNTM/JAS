"""Full-duplex voice, controlled vision, and governed proactive session primitives.

Hardware/model backends are injected protocols. TTS tool execution must use the MCP
Gateway; this module does not treat speech, vision, or proactive signals as authority.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import threading
import time as clock
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.voice.metrics import VoiceLatencyMetrics


class SpeechRecognizer(Protocol):
    async def transcribe(self, audio: bytes, *, session_id: str) -> str: ...


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str, *, session_id: str) -> Any: ...


class AudioPlayer(Protocol):
    async def play(self, audio: Any, *, session_id: str) -> None: ...

    async def stop(self, *, session_id: str) -> None: ...


logger = logging.getLogger(__name__)


class SpeechModelLoadError(RuntimeError):
    """The configured local faster-whisper model could not be initialized."""


class SpeechTranscriptionError(RuntimeError):
    """The local STT inference engine failed."""


class SpeechDecodeError(ValueError):
    """The supplied recording could not be decoded into PCM."""


def resolve_whisper_runtime(device: str, compute_type: str) -> tuple[str, str]:
    requested, precision = device.strip().lower(), compute_type.strip().lower()
    if requested not in {"auto", "cuda", "cpu"}:
        raise ValueError("AURA_STT_DEVICE must be auto, cuda, or cpu")
    if precision not in {"auto", "int8", "float16", "int8_float16", "float32", "bfloat16"}:
        raise ValueError("Unsupported AURA_STT_COMPUTE_TYPE")
    cuda = False
    if requested != "cpu":
        try:
            import ctranslate2
            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            logger.warning("STT CUDA probe failed; using CPU INT8")
    if requested == "cuda" and not cuda:
        raise RuntimeError("CUDA was explicitly requested but no CUDA device is available")
    if cuda:
        return "cuda", "float16" if precision == "auto" else precision
    return "cpu", "int8" if precision in {"auto", "float16", "int8_float16", "bfloat16"} else precision


def configured_whisper_model(device: str, explicit: str | None = None) -> str:
    # Explicit model paths (including offline mode) take precedence; do not
    # silently download another model when an operator selected a local one.
    name = explicit if explicit is not None else os.getenv("AURA_STT_MODEL")
    if name is None:
        name = os.getenv("AURA_STT_CPU_MODEL", "small") if device == "cpu" else "small"
    if not name.strip():
        raise ValueError("AURA_STT_MODEL / AURA_STT_CPU_MODEL must not be empty")
    return name.strip()


def whisper_cpu_threads() -> int:
    return max(1, min(16, int(os.getenv("AURA_STT_CPU_THREADS", str(min(8, os.cpu_count() or 4))))))


class FasterWhisperRecognizer:
    """Shared local STT runtime: one decode, serialized inference, sticky CPU retry."""

    def __init__(self, *, model_size: str | None = None, device: str = "auto", compute_type: str = "auto") -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None
        # A cancelled coroutine cannot interrupt native inference. Serialize
        # the worker itself so another utterance cannot race the model cache.
        self._worker_lock = threading.Lock()
        self._active_device: str | None = None
        self._cpu_only = False

    @staticmethod
    def _decode_audio(audio_bytes: bytes):
        """Decode arbitrary supported audio bytes to a 16 kHz mono float32 array.

        Passing samples instead of a file path avoids faster-whisper's internal
        decode_audio call, which may pass unsupported keyword arguments to PyAV.
        """
        import av
        import numpy as np

        with av.open(io.BytesIO(audio_bytes), mode="r") as container:
            audio_stream = next(
                (stream for stream in container.streams if stream.type == "audio"),
                None,
            )
            if audio_stream is None:
                raise ValueError("Audio payload contains no audio stream")

            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            chunks = []
            for frame in container.decode(audio=audio_stream.index):
                chunks.extend(resampler.resample(frame))
            # Flush any buffered samples from the resampler.
            chunks.extend(resampler.resample(None))

        if not chunks:
            raise ValueError("Audio payload contains no decodable samples")
        samples = np.concatenate(
            [frame.to_ndarray().reshape(-1) for frame in chunks]
        ).astype(np.float32, copy=False)
        if samples.size == 0:
            raise ValueError("Audio payload contains no decodable samples")
        return samples

    def _runtime(self) -> tuple[str, str]:
        if self._cpu_only:
            return "cpu", "int8"
        try:
            return resolve_whisper_runtime(self._device, self._compute_type)
        except RuntimeError:
            self._cpu_only = True
            logger.warning("STT runtime unavailable; using CPU INT8")
            return "cpu", "int8"

    def _load_model(self, device: str, precision: str):
        from faster_whisper import WhisperModel

        return WhisperModel(
            configured_whisper_model(device, self._model_size),
            device=device, compute_type=precision, cpu_threads=whisper_cpu_threads(),
        )

    def _load(self, device: str, precision: str) -> None:
        try:
            self._model = self._load_model(device, precision)
            self._active_device = device
        except ImportError:
            raise
        except Exception as exc:
            self._model = None
            self._active_device = None
            raise SpeechModelLoadError("Unable to initialize the local faster-whisper model") from exc

    def _fallback(self) -> None:
        # Keep the latch set even if CPU model initialization itself fails.
        self._cpu_only = True
        self._model = None
        self._active_device = None
        self._load("cpu", "int8")

    def transcribe_bytes(self, audio: bytes, *, language: str, options: Mapping[str, Any],
                         force_cpu: bool = False) -> tuple[str, str]:
        if not audio or len(audio) > 20_000_000:
            raise SpeechDecodeError("Audio payload is empty or exceeds the 20 MB limit")
        with self._worker_lock:
            # Decode errors are input/codec failures, not CUDA failures. The
            # same PCM buffer is retained if native inference fails lazily.
            try:
                samples = self._decode_audio(audio)
            except ImportError:
                raise
            except ValueError as exc:
                raise SpeechDecodeError(str(exc)) from exc
            except Exception as exc:
                raise SpeechDecodeError("Unable to decode the audio container") from exc

            if force_cpu and not self._cpu_only:
                self._cpu_only = True
                self._model = None
                self._active_device = None
            if self._model is None:
                device, precision = self._runtime()
                try:
                    self._load(device, precision)
                except SpeechModelLoadError:
                    if device != "cuda":
                        raise
                    logger.warning("STT CUDA model load failed; using CPU INT8", exc_info=True)
                    self._fallback()

            def infer() -> tuple[str, str]:
                try:
                    segments, info = self._model.transcribe(samples, language=language, **options)
                    # Native errors may be deferred until segment iteration.
                    text = " ".join(segment.text.strip() for segment in segments).strip()
                    return text, getattr(info, "language", None) or language
                except Exception as exc:
                    raise SpeechTranscriptionError("Local faster-whisper inference failed") from exc

            try:
                return infer()
            except SpeechTranscriptionError:
                if self._active_device != "cuda":
                    raise
                logger.warning("STT CUDA inference failed; retrying same samples on CPU INT8", exc_info=True)
                self._fallback()
                return infer()

    def _transcribe_sync(self, audio: bytes) -> str:
        text, _ = self.transcribe_bytes(
            audio, language="tr",
            options={
                "beam_size": max(1, min(5, int(os.getenv("AURA_STT_BEAM_SIZE", "3")))),
                "vad_filter": True,
                "vad_parameters": {"min_silence_duration_ms": 300, "speech_pad_ms": 300},
                "temperature": 0.0, "condition_on_previous_text": False,
            },
        )
        return text[:8000]

    async def transcribe(self, audio: bytes, *, session_id: str) -> str:
        return await asyncio.to_thread(self._transcribe_sync, audio)


_shared_whisper: FasterWhisperRecognizer | None = None
_shared_whisper_lock = threading.Lock()


def shared_whisper_recognizer() -> FasterWhisperRecognizer:
    """Process-owned recognizer shared by HTTP and full-duplex composition."""
    global _shared_whisper
    with _shared_whisper_lock:
        if _shared_whisper is None:
            from aura_core.tts.offline_voice import OfflineVoiceConfig

            offline = OfflineVoiceConfig.from_environment()
            _shared_whisper = FasterWhisperRecognizer(
                model_size=offline.stt_model_path if offline is not None else os.getenv("AURA_STT_MODEL"),
                device=os.getenv("AURA_STT_DEVICE", "auto"),
                compute_type=os.getenv("AURA_STT_COMPUTE_TYPE", "auto"),
            )
        return _shared_whisper


class EventBusAudioPlayer:
    """Deliver TTS audio to the authorized local UI over the existing event bridge."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus

    async def play(self, audio: Any, *, session_id: str) -> None:
        payload = getattr(audio, "structured_content", None)
        if payload is None:
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
        response = await asyncio.wait_for(self._gateway.invoke(MCPGatewayRequest(
            request_id=str(uuid4()), principal_id=self._principal,
            capability_id=self._capability, operation_id=self._operation,
            resource_scope=self._scope, risk_level=RiskLevel.LOW,
            tool_name=self._tool, arguments={"text": text},
            session_id=session_id,
        )), timeout=20)
        if response.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError(f"TTS authorization denied: {response.reason}")
        return response.result


class FullDuplexSessionManager:
    """Single-session speech state machine with interruptible TTS playback."""

    def __init__(
        self, *, recognizer: SpeechRecognizer, synthesizer: SpeechSynthesizer,
        player: AudioPlayer, event_bus: EventBus | None = None,
        prosody_analyzer: Any | None = None,
        latency_metrics: VoiceLatencyMetrics | None = None,
    ) -> None:
        self._recognizer = recognizer
        self._synthesizer = synthesizer
        self._player = player
        self._events = event_bus
        self._prosody_analyzer = prosody_analyzer
        self._latency_metrics = latency_metrics or VoiceLatencyMetrics()
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
            # Closing/restarting the session while interrupt() awaited cannot
            # resurrect a recognizer bound to the former session identity.
            if self._session_id != session_id or self._state == "idle":
                raise RuntimeError("Speech session ended before recognition started")
            self._state = "recognizing"
            generation = self._generation
        if self._prosody_analyzer is not None:
            try:
                cues = await asyncio.to_thread(
                    self._prosody_analyzer.analyze_consented_audio,
                    audio,
                    session_id=session_id,
                )
            except (ValueError, RuntimeError):
                # Malformed prosody hints must not interrupt a valid STT session.
                async with self._lock:
                    if (self._generation == generation
                            and self._session_id == session_id
                            and self._state == "recognizing"):
                        self._emit("SpeechProsodyAnalysisUnavailable", {})
            else:
                async with self._lock:
                    # Advisory events must never leak from a closed/replaced session.
                    if (self._generation == generation
                            and self._session_id == session_id
                            and self._state == "recognizing"):
                        self._emit("SpeechProsodyAnalysisCompleted", {
                            "delivery_style": cues.delivery_style,
                            "confidence": cues.confidence,
                        })
            async with self._lock:
                if (self._generation != generation
                        or self._session_id != session_id
                        or self._state != "recognizing"):
                    raise RuntimeError("Speech recognition was superseded during prosody")
        try:
            started = clock.perf_counter()
            transcript = (await self._recognizer.transcribe(audio, session_id=session_id)).strip()
            self._latency_metrics.record("stt_complete", (clock.perf_counter() - started) * 1000)
        except BaseException:
            # Cancellation or a failing recognizer must not change a newer
            # session's state or a newer active speech playback.
            async with self._lock:
                if (self._generation == generation
                        and self._session_id == session_id
                        and self._state == "recognizing"):
                    self._state = "listening"
            raise
        async with self._lock:
            if (self._generation != generation
                    or self._session_id != session_id
                    or self._state != "recognizing"):
                raise RuntimeError("Speech recognition was superseded")
            self._transcript = transcript[:8000]
            self._state = "listening"
            self._emit("SpeechTranscript", {"characters": len(self._transcript)})
        return self._transcript

    async def ingest_pcm(self, payload: bytes, *, end: bool = False) -> dict[str, object]:
        """Decode independent 100ms PCM frames in the configured sherpa provider.

        This path does not promote the microphone to tool authority or replay
        wake-word audio into ASR. Interrupted TTS is managed separately.
        """
        sid = self._require_session()
        if not hasattr(self._recognizer, "consume_pcm"):
            raise RuntimeError("Streaming PCM provider is unavailable")
        started = clock.perf_counter()
        result = await self._recognizer.consume_pcm(payload, session_id=sid, end=end)
        if end:
            self._latency_metrics.record("stt_complete", (clock.perf_counter() - started) * 1000)
        if result.get("wake_detected"):
            self._emit("SpeechWakeDetected", {"provider": "sherpa-onnx"})
        transcript = str(result.get("transcript") or "").strip()[:8000]
        if transcript and end:
            async with self._lock:
                self._transcript = transcript
                self._emit("SpeechTranscript", {"characters": len(transcript)})
        return {"wake_detected": bool(result.get("wake_detected")),
                "transcript": transcript if end else "",
                "listening": bool(result.get("listening")), "complete": end}

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
            started = clock.perf_counter()
            audio = await self._synthesizer.synthesize(text, session_id=session_id)
            self._latency_metrics.record("tts_first_audio", (clock.perf_counter() - started) * 1000)
            async with self._lock:
                if generation != self._generation or self._state != "speaking":
                    return
            await self._player.play(audio, session_id=session_id)

        async with self._lock:
            # Install the task under the same lock used by interrupt()/close().
            # Otherwise a close between task creation and assignment misses
            # cancellation and may leave an orphaned synthesize operation.
            if (generation != self._generation
                    or self._session_id != session_id
                    or self._state != "speaking"):
                raise RuntimeError("Speech playback was superseded")
            task = asyncio.create_task(playback())
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
        sid = self._session_id
        await self.interrupt(reason="session_closed", keep_listening=False)
        if sid is not None and hasattr(self._recognizer, "close_session"):
            await self._recognizer.close_session(sid)
        async with self._lock:
            self._state = "idle"
            self._session_id = None
            self._transcript = ""

    def snapshot(self) -> SpeechSnapshot:
        return SpeechSnapshot(
            session_id=self._session_id or "", state=self._state,
            last_transcript=self._transcript, generation=self._generation,
        )

    def latency_snapshot(self) -> dict[str, dict[str, float | int]]:
        """Measured local samples; these are observations, never latency guarantees."""
        return self._latency_metrics.snapshot()

    def record_client_latency(self, stage: str, milliseconds: float) -> None:
        if stage in {"llm_first_token", "browser_first_audio", "end_to_end"}:
            self._latency_metrics.record(stage, milliseconds)

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
