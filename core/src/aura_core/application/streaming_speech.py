"""Provider-independent incremental speech synthesis orchestration.

This module provides bounded sentence assembly, inference/TTS overlap, and
cancellation. It deliberately performs no provider selection or tool calls:
the caller must supply an authorized speech synthesizer, normally the existing
GatewaySpeechSynthesizer, so model text cannot execute tools or grant authority.

Not a voice endpoint or a benchmark: native ASR, Web Audio playback and a
specific ONNX model are provisioned separately by their registered providers.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter

from aura_core.tts.text import clean_for_speech


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    sequence: int
    text: str
    audio: bytes


@dataclass(frozen=True, slots=True)
class StreamingSpeechStats:
    elapsed_ms: float
    first_text_ms: float | None
    first_audio_ms: float | None
    speech_segments: int
    characters: int
    interrupted: bool


class SentenceAccumulator:
    """Bounded punctuation-aware assembler; no token-by-token TTS requests."""

    def __init__(self, *, min_chars: int = 28, max_chars: int = 260) -> None:
        if not 1 <= min_chars <= max_chars <= 1024:
            raise ValueError("Invalid sentence thresholds")
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""

    @staticmethod
    def _boundary(value: str, limit: int, minimum: int) -> int:
        for index, char in enumerate(value[:limit]):
            if char in ".!?…;\n" and index + 1 >= minimum:
                # Avoid splitting decimals and basic abbreviations.
                if char == "." and index > 0 and index + 1 < len(value):
                    if value[index - 1].isdigit() and value[index + 1].isdigit():
                        continue
                return index + 1
        if len(value) > limit:
            # Backpressure without splitting words when possible.
            split = max(value.rfind(" ", minimum, limit + 1),
                        value.rfind("\n", minimum, limit + 1))
            return split if split > 0 else limit
        return 0

    def feed(self, delta: str) -> tuple[str, ...]:
        if not isinstance(delta, str) or len(delta) > 4096:
            raise ValueError("Streaming text delta must be at most 4096 characters")
        self._buffer += delta
        if len(self._buffer) > 8192:
            raise ValueError("Speech buffer exceeds hard bound")
        ready: list[str] = []
        while self._buffer:
            endpoint = self._boundary(self._buffer, self.max_chars, self.min_chars)
            if not endpoint:
                break
            candidate = clean_for_speech(self._buffer[:endpoint])
            if candidate:
                ready.append(candidate)
            self._buffer = self._buffer[endpoint:].lstrip()
        return tuple(ready)

    def finish(self) -> tuple[str, ...]:
        remaining = clean_for_speech(self._buffer)
        self._buffer = ""
        return (remaining,) if remaining else ()


class StreamingSpeechCoordinator:
    """Overlap model token ingestion with authorized per-segment TTS.

    Producer and consumer operate concurrently with a bounded queue. Playback
    remains ordered. Cancelling the consumer cancels the producer and drops
    buffered segments. Audio never enters global EventBus or persistent memory.
    """

    def __init__(
        self,
        synthesizer: Callable[[str], Awaitable[bytes]],
        *,
        queue_capacity: int = 3,
        max_segments: int = 96,
        max_total_chars: int = 24000,
        max_audio_bytes: int = 4_000_000,
    ) -> None:
        if not callable(synthesizer):
            raise TypeError("synthesizer must be an authorized async callable")
        if not 1 <= queue_capacity <= 12 or not 1 <= max_segments <= 512:
            raise ValueError("Queue limits are invalid")
        if not 1 <= max_total_chars <= 50000 or not 1 <= max_audio_bytes <= 16_000_000:
            raise ValueError("Content and audio limits are invalid")
        self._synthesizer = synthesizer
        self._queue_capacity = queue_capacity
        self._max_segments = max_segments
        self._max_total_chars = max_total_chars
        self._max_audio_bytes = max_audio_bytes
        self.last_stats: StreamingSpeechStats | None = None

    async def render(
        self,
        tokens: AsyncIterable[str],
        *,
        interrupt: asyncio.Event | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> AsyncIterator[SpeechSegment]:
        started = perf_counter()
        first_text_ms: float | None = None
        first_audio_ms: float | None = None
        chars = 0
        produced = 0
        rendered = 0
        interrupted = False
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self._queue_capacity)
        stop_event = interrupt or asyncio.Event()
        producer_error: list[Exception] = []

        async def produce() -> None:
            nonlocal chars, produced, first_text_ms
            builder = SentenceAccumulator()
            try:
                async for delta in tokens:
                    if stop_event.is_set():
                        break
                    if first_text_ms is None and delta:
                        first_text_ms = (perf_counter() - started) * 1000
                    chars += len(delta)
                    if chars > self._max_total_chars:
                        raise ValueError("Streaming speech text budget exceeded")
                    if on_text is not None:
                        on_text(delta)
                    for text in builder.feed(delta):
                        produced += 1
                        if produced > self._max_segments:
                            raise ValueError("Streaming speech segment budget exceeded")
                        await queue.put(text)
                if not stop_event.is_set():
                    for text in builder.finish():
                        produced += 1
                        if produced > self._max_segments:
                            raise ValueError("Streaming speech segment budget exceeded")
                        await queue.put(text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                producer_error.append(exc)
            finally:
                await queue.put(None)

        producer_task = asyncio.create_task(produce())
        try:
            while True:
                if stop_event.is_set():
                    interrupted = True
                    break
                # Wakes periodically even when an external interruption happens.
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                except TimeoutError:
                    continue
                if item is None:
                    if producer_error:
                        raise producer_error[0]
                    break
                if stop_event.is_set():
                    interrupted = True
                    break
                audio = await self._synthesizer(item)
                if not isinstance(audio, bytes) or not audio or len(audio) > self._max_audio_bytes:
                    raise ValueError("Speech synthesizer returned invalid/oversized bytes")
                if stop_event.is_set():
                    interrupted = True
                    break
                if first_audio_ms is None:
                    first_audio_ms = (perf_counter() - started) * 1000
                rendered += 1
                yield SpeechSegment(sequence=rendered, text=item, audio=audio)
        finally:
            producer_task.cancel()
            await asyncio.gather(producer_task, return_exceptions=True)
            self.last_stats = StreamingSpeechStats(
                elapsed_ms=(perf_counter() - started) * 1000,
                first_text_ms=first_text_ms, first_audio_ms=first_audio_ms,
                speech_segments=rendered, characters=chars,
                interrupted=interrupted or stop_event.is_set(),
            )
