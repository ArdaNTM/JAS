# Concurrent voice session generation safety — feature #14 (partial)

Modifies the **existing** `FullDuplexSessionManager` in `core/src/aura_core/application/full_duplex_session.py`, rather than adding a second STT/TTS engine. No new model, provider, device privilege or PermissionEngine/MCP Gateway permission is introduced.

## Problem
While asynchronous speech recognition was running, `ingest_audio()` could finish after the user closed/restarted the session or another speech operation began, and unconditionally write the old transcript and reset state to `listening`. This could overwrite a newer session's state and return stale input in the wrong context. During speech replacement, `speak()` also installed its playback task outside its state lock, permitting a close/interrupt to miss the not-yet-recorded task.

## Fix
- Each `ingest_audio()` captures the same `_generation` used by the manager's `interrupt()`/`speak()` lifecycle, after verifying the original `session_id` is still active. After the recognizer awaits, **the generation, session ID and expected `recognizing` state must all match** before accepting transcription or changing state.
- Canceled or failed recognition changes state only when still the same generation/session, never overwriting a later speech or restarted session.
- `speak()` now installs its playback task **inside the existing session lock** after verifying generation/session/state are unchanged, so a close/interrupt cannot miss a newly created playback task.
- Superseded STT returns an explicit `RuntimeError` (not a leaked transcript); callers should treat this as a canceled turn and never persist it as evidence.

## Tests
`cd core && uv run pytest -q tests/test_voice_session_generation_guard.py tests/test_full_duplex_session.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Regression tests use async barriers, a fake recognizer and a cancelable fake player. They cover (1) late transcript after close/restart must not leak into next session, (2) old transcription cannot stop newer TTS, (3) recognizer cancellation correctly restores listening for the same generation, (4) overlapping audio only records the newest transcript and (5) existing barge-in cancels playback.

## Security and acceptance limits
- Model-backed microphone privacy, wake word, diarization, GPU inference and full natural language turn-taking **are not implemented or verified** here. No physical audio/microphone tests or trusted user identity enrollment.
- This fixes state concurrency only inside the existing manager; production UI/MCP event routing still needs real user/device/Owner acceptance. STT audio, transcripts and TTS results remain untrusted data until separately authorized.
- Feature #14 stays `TESTING/PARTIAL_VERIFIED` after exact CI; no COMPLETED claim or automatic merge. The original MCP Gateway remains the sole external tool authorization boundary.