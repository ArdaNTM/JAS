# Governed Kokoro voice controls and complete WAV output — feature #18 (partial)

The existing Kokoro MCP service previously allowed unconstrained voice IDs, non-finite rates, unbounded text, arbitrary exception messages and returned only the **first** pipeline speech chunk. This PR provides actual voice choice, bounded speed, input sanitation and iterated WAV synthesis using the existing MCP provider rather than a second TTS authority.

## Scope
- `core/src/aura_core/tts/kokoro_guard.py` defines conservative supported English `af_*`/`am_*` voices for the current `KPipeline(lang_code='a')`, safe speed 0.75–1.35, <=4000 source characters and reuse of `clean_for_speech`.
- `core/scripts/kokoro_tts_mcp.py` calls the guard before lazy model import, supplies an explicit MCP JSON Schema, streams all returned audio chunks into a bounded 24kHz/mono PCM WAV (<=90 seconds), fails closed on malformed/oversized output, and returns only exception class in failed MCP tool response (no local paths or user text).
- `core/scripts/generate_final_lock.py` explicitly adds the executable Kokoro provider script to production release-lock inventory, alongside the new Core guard. Both source hashes are checked by existing Final Release Lock verifier.
- No new provider registry entry, tool execution policy or permission grant; actual audio still travels through existing registered MCP Gateway.

## Tests
`cd core && uv run pytest -q tests/test_kokoro_voice_controls.py tests/test_tts_provider_selection.py`
`cd core && uv run python scripts/verify_final_lock.py`

Positive/negative test coverage: allowlisted voices, safe speed and cleaned text, unknown voice, nonfinite/unsafe speed, malformed/URL-only text, mocked local multi-chunk speech, output over time cap, MCP schema, redacted errors and executable provider entry in the release lock. Mock voices and soundfile are tests only; actual Kokoro model synthesis is not claimed.

## Known limitations / further acceptance
- Current allowlist only describes selected English Kokoro voices for lang_code='a', not verified voices on every installation. Piper remains the independent local Turkish provider and is unchanged.
- Real model weights and their licenses, actual audio quality/latency, voice download/provenance, provider deployment and Owner acceptance remain unverified.
- Large/hostile model outputs can still consume resources inside a provider before duration guard; end-to-end MCP execution budgets and real voice tests remain necessary.
- This implements only part of #18 voice customization. Feature stays TESTING/PARTIAL_VERIFIED, not COMPLETED.
