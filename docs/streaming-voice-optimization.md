# Local Turkish spoken replies and Ollama token streaming

AURA retains its provider-agnostic Core inference abstraction and the
PermissionEngine -> MCP Gateway boundary for real TTS execution. No frontend
direct access to Ollama or Piper and no browser remote TTS fallback.

## Voice text preparation

The HTTP/UI assistant's Markdown is *not* a speech transcript. AURA now
normalizes Markdown emphasis/headings/fenced code, hyperlinks, residual URLs,
citation markers, and whitespace before local speech generation. The
normalization is repeated inside the Piper MCP provider to protect other
Gateway callers. Original assistant text and research evidence remain intact.

The browser splits speech into bounded, ordered pieces (up to 700 chars) and
plays them sequentially; it never slices and discards the unsaid remainder.
Outside full-duplex sessions, speech for completed sentences can begin while
Ollama continues generating. With an active full-duplex session, replies of
up to 3900 characters use the existing interruptible SSE player; longer
replies use the ordered direct chunks. Barge-in for the longer direct route
is not yet equivalent to the full-duplex SSE player.

The Piper provider keeps one ONNX voice cached, validates the local `tr_TR`
voice, and accepts bounded optional synthesis tuning through environment
variables: `AURA_PIPER_LENGTH_SCALE` (0.7–1.6, default 0.96),
`AURA_PIPER_NOISE_SCALE` (0.2–1.2, default 0.72), and
`AURA_PIPER_NOISE_W_SCALE` (0.2–1.2, default 0.85).
Parameters come from upstream Piper's [Python API](
https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).
Natural prosody is still constrained by the specific licensed voice.

## Local model and UI streaming

The Windows launcher sets `AURA_OLLAMA_FAST_MAX_TOKENS=1024` when absent;
the interactive adapter bounds this setting to 128..2048. An explicitly
configured `AURA_MAX_TOKENS` still takes precedence. This trades some
response latency for **complete** multi-point summaries compared with the
previous 384-token default. For longer answers, set `AURA_MAX_TOKENS`
in `core/.env.local` and restart.

AURA's new `/api/assistant/respond/stream` route requires the existing
authenticated principal, reuses the same bounded assistant context,
uses the existing `InferenceService` → runtime → transport chain, and
returns line-delimited JSON tokens. The Ollama HTTP transport requests
`stream=true` and parses bounded NDJSON; thinking traces are not returned.
It does not dispatch MCP tools directly. Errors are generic to the browser
and logged in the Core. On generator cancellation the HTTP stream is closed;
a stream that never sends a terminal completion is rejected.

The UI streams text to the speech queue, so the time to first speech can
improve without waiting for the full answer. Ollama upstream protocol:
https://github.com/ollama/ollama/blob/main/docs/capabilities/streaming.mdx

**Limits:** GitHub CI uses mock local inference and mock TTS, not the Windows
RTX GPU or the real Turkish ONNX voice. The actual end-to-end latency,
naturalness, acoustics and full-duplex interruption remain local acceptance
tests. No specific ChatGPT/Claude/Gemini speed or quality parity is claimed.
The legacy non-streaming endpoint remains available for other API clients.
