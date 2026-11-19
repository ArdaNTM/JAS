"""Consent-bound offline wake phrase gate over *already transcribed* speech.

The trusted speech adapter supplies text after an explicitly confirmed local
microphone session. This module cannot open microphones, start sessions,
dispatch tools, or grant permission. A match publishes an EventBus signal only.
It is not an acoustic wake-word model or independent user authentication.
"""
from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from aura_core.kernel.events import EventBus, KernelEvent, EventPriority

_MAX_TRANSCRIPT = 256
_MAX_SESSION_ID = 128
_ALLOWED_PHRASES = frozenset({"hey aura", "aura"})
_EDGE_PUNCTUATION = " \t.,!?。！？"


@dataclass(frozen=True, slots=True)
class WakeWordSnapshot:
    session_id: str
    armed: bool
    activation_count: int


def _session(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= _MAX_SESSION_ID
            or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value)):
        raise ValueError("Invalid confirmed speech session")
    return value


def _phrase(transcript: object) -> str | None:
    if not isinstance(transcript, str) or not 1 <= len(transcript) <= _MAX_TRANSCRIPT:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in transcript):
        return None
    normalized = unicodedata.normalize("NFKC", transcript).casefold()
    normalized = " ".join(normalized.strip(_EDGE_PUNCTUATION).split())
    if normalized in _ALLOWED_PHRASES:
        return normalized
    return None


class ConsentedWakeWordGate:
    """Single-session event-only wake signal with explicit consent and cooldown.

    A trusted Core speech composition must authenticate principal/session and
    call arm() only after affirmative microphone consent. A raw client request
    to this helper is not proof of consent; it is never exposed as an endpoint.
    """

    def __init__(
        self,
        events: EventBus,
        *,
        clock: Callable[[], float] = time.monotonic,
        min_rearm_seconds: float = 2.0,
    ) -> None:
        if not isinstance(events, EventBus):
            raise TypeError("The existing Core EventBus is required")
        if (not isinstance(min_rearm_seconds, (int, float))
                or isinstance(min_rearm_seconds, bool)
                or not math.isfinite(min_rearm_seconds)
                or not 0.25 <= min_rearm_seconds <= 60.0):
            raise ValueError("Wake cooldown must be between 0.25 and 60 seconds")
        self._events = events
        self._clock = clock
        self._cooldown = float(min_rearm_seconds)
        self._lock = threading.RLock()
        self._session_id: str | None = None
        self._armed = False
        self._activation_count = 0
        self._last_activation: float | None = None

    def arm(self, *, session_id: str, microphone_confirmed: bool) -> WakeWordSnapshot:
        session = _session(session_id)
        if microphone_confirmed is not True:
            raise PermissionError("Explicit microphone consent is required")
        with self._lock:
            if self._session_id is not None and self._session_id != session:
                raise PermissionError("Another speech session owns the wake gate")
            # A new arm never resets the cooldown or cumulative count.
            self._session_id = session
            self._armed = True
            return self._snapshot()

    def disarm(self, *, session_id: str) -> WakeWordSnapshot:
        session = _session(session_id)
        with self._lock:
            if session != self._session_id:
                raise PermissionError("Speech session mismatch")
            self._armed = False
            self._session_id = None
            return self._snapshot()

    def observe_transcript(self, transcript: object, *, session_id: str) -> bool:
        """Consume exact standalone phrase once; never dispatch an action."""
        session = _session(session_id)
        phrase = _phrase(transcript)
        if phrase is None:
            return False
        with self._lock:
            if not self._armed or session != self._session_id:
                return False
            try:
                now = float(self._clock())
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(now):
                return False
            if self._last_activation is not None:
                # Clock rollback and rapid duplicate STT segments fail closed.
                if now < self._last_activation or now - self._last_activation < self._cooldown:
                    return False
            self._last_activation = now
            self._armed = False  # one signal per *explicit* arm
            self._activation_count += 1
            # Event metadata deliberately excludes principal identifiers,
            # transcript, arguments, audio, URLs or any new permission grant.
            self._events.publish(KernelEvent(
                event_type="WakeWordDetected",
                source_component="aura.wake_word_gate",
                session_id=session,
                correlation_id=session,
                priority=EventPriority.NORMAL,
                payload={"session_id": session, "phrase": phrase, "requires_owner_action": True},
            ))
            return True

    def snapshot(self) -> WakeWordSnapshot:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> WakeWordSnapshot:
        return WakeWordSnapshot(
            session_id=self._session_id or "",
            armed=self._armed,
            activation_count=self._activation_count,
        )
