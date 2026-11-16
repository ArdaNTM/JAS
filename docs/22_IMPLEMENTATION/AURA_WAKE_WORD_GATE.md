# Consent-bound offline wake phrase gate — feature #13 (partial)

Implements an **EventBus-only** wake phrase recognizer over already-transcribed local speech. `core/src/aura_core/application/wake_word_gate.py` consumes **trusted upstream** STT text after a separately authenticated, explicitly confirmed microphone session. It cannot open the microphone, activate an existing `FullDuplexSessionManager`, launch an MCP tool, alter the PermissionEngine, or execute user instructions.

## Behavior
- The trusted application composition creates one `ConsentedWakeWordGate` with the Core EventBus and calls `arm(session_id=..., microphone_confirmed=True)` only after session/microphone consent. False or absent consent rejects activation; the helper itself is not an identity provider.
- Matches only **standalone** normalized `Aura` / `Hey Aura` phrases. Command-like speech after the phrase, embedded punctuation, markup/prompt-looking content, oversized, control-character or malformed Unicode transcripts do not match.
- On match, publishes only `WakeWordDetected` through the existing EventBus with session ID, canonical phrase and `requires_owner_action=True`, **never** the complete transcript, audio bytes, sensitive memory or a tool authorization.
- One activation disarms immediately; re-arm must be explicit and a monotonic 2-second default cooldown prevents duplicate activations. Wrong session IDs and clock rollback fail closed. No automatic action follows the event.

## Tests
`cd core && uv run pytest -q tests/test_wake_word_gate.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

## Acceptance limitations
- This is a transcript phrase gate, **not** acoustic wake-word detection and not a true microphone hotword model. No integration into real live microphone audio, no VAD/acoustic false-positive study, noise testing, speaker verification, speech interruption or always-on hardware acceptance.
- Integration with `FullDuplexSessionManager` and Owner-approved speech UI is not provided; the current `SpeechSessionManager` still owns microphone lifecycle and MCP Gateway controls any speech tool execution. A downstream subscriber must not treat this event as permission or an Owner identity proof.
- Phase #13 remains TESTING/PARTIAL_VERIFIED only after exact-head Core, Persistence and Release Lock PASS. It is not COMPLETED.
- No new network, model download, package dependency or commercial license.
