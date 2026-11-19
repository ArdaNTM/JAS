# Consented offline ambient PCM signal-level observation — feature #20 (partial)

This PR adds `core/src/aura_core/application/ambient_signal.py`, a real bounded 16kHz mono little-endian PCM16 energy analyzer plus an optional `EventBus` signal-level observer. The data must come from an already authenticated, explicitly confirmed **local speech session**. This module cannot open microphones, record in the background, identify voices/sounds, call networks, launch tools or grant PermissionEngine/MCP Gateway privileges.

## Bounded behavior
- Pure `analyze_pcm16_signal(audio: bytes, sample_rate=16000)`: accepts exactly 160..32000 PCM16 samples (10..2000ms), validates even-length raw bytes, computes normalized RMS/peak/clipped fraction with Python standard library, and returns only `quiet`, `activity`, or `clipping` based on fixed thresholds. `classification` always identifies the output as **signal energy only**, not an actual sound identity.
- `ConsentedAmbientSignalObserver` starts only after trusted composition calls `start(session_id, microphone_confirmed=True)`; mismatched session, missing consent or stopped session fails closed. A generation counter blocks stale events after stop during parsing.
- On coarse level changes only, emits `AmbientSignalLevelChanged` to the **existing Core EventBus** with bounded numeric metrics and session ID. It never publishes or retains raw audio samples, transcripts, personal memory or any inferred speech content.
- No new provider, automatic microphone control, ambient listening startup, network/model dependency, MCP capability, Owner grant or permission policy.

## Verification
`cd core && uv run pytest -q tests/test_ambient_signal.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

## Outstanding acceptance
- This is deliberately **not** environment sound recognition (doorbell, siren, dog, speaker identity, location). No acoustic classification model, calibration, real microphone device, consent UI, streaming runtime wiring, noise/false-positive evaluation, sample-rate conversion or hardware acceptance is provided.
- Upstream speech composition and Owner must authenticate sessions/recording consent. EventBus observations are untrusted hints, not commands, policies or evidence of successful tool execution. Any active tool still routes through MCP Gateway and PermissionEngine.
- Feature #20 can be TESTING/PARTIAL_VERIFIED only after exact-head Core, Persistence and Release Lock PASS; not COMPLETED.
- Standard library only, no new licensing requirements.
