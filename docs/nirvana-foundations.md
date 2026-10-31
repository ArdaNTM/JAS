# AURA Nirvana foundations — separate from HUD PR #51

This is the **first implementation slice of the next architectural release**,
based on `main` and intentionally independent of the experimental HUD branch.
It is *not* a shipped native wake-word, Kokoro ONNX, low-latency Web Audio,
GraphRAG index migration, desktop-autonomy or Home Assistant integration.

## Existing foundations (reuse instead of duplicate)

- Kernel registries, PermissionEngine, EventBus, MCP Gateway authorization.
- `/api/assistant/respond/stream` incremental token transport already exists.
- `GatewaySpeechSynthesizer` enforces the existing `speech.synthesize`
  capability; full-duplex interruptions are already implemented.
- PostgreSQL Graph Store in remote mode, local graph store only in local mode.
- Existing SearXNG research MCP provider and guarded autonomous loops.
- Remote PostgreSQL/MinIO storage remains fail-closed.

## This implementation slice

1. **Speech chunk orchestration contract** (`streaming_speech.py`):
   provider-neutral incremental text chunks, complete-sentence/bounded segments,
   backpressure, first-text/first-audio timestamps and interruption. The caller
   must inject a **pre-authorized TTS adapter**. No new tool dispatch authority.
   There is no browser playback wiring yet; no model weights are downloaded.
2. **Opt-in memory relevance budget** (`AURA_CONTEXT_MEMORY_SELECTION=relevance`):
   deterministic lexical relevance sorting and de-duplication of already
   scoped recalled memory, respecting existing context character budgets.
   Default `chronological` preserves the old behavior. Untrusted memory
   never becomes a system prompt or an executable instruction.

These primitives enable incremental evaluation but **are not live voice-to-voice
or benchmark claims**. A streaming UI integration must validate audio format,
buffer underruns and cancellation before enabling playback.

## Five streams of engineering work and integration gates

| Stream | Provider contract / implementation | Acceptance |
|---|---|---|
| Wake/STT | `wake.detect` + `speech.transcribe.streaming` with sherpa-onnx KWS or whisper.cpp backend, separate downloadable models | Document model provenance, local multilingual AURA wake accuracy, FAR/FRR, audio CPU load and privacy. Opt-in microphone |
| TTS | `speech.synthesize.chunks` via Gateway, ONNX Kokoro **optional** adapter; output sequence/mime/sample rate and audio buffer limits | Barge-in cancels pending synthesis, no late audio, stable Web Audio playback, language pronunciation & license |
| GraphRAG | Existing scoped PostgreSQL graph + local/global vector retrieval, evidence lineage, memory TTL, deterministic budgets | Principal isolation, citation accuracy, no prompt injection, p50/p95 recall and token reduction measurements |
| Autonomy | Existing governed task loop + model-role routing and opt-in OS/browser adapters; never raw Open Interpreter execution | Per-operation policy approval, credential/screenshot non-disclosure, browser domain allowlist, idempotent retries, no voice-as-permission |
| Inference/IoT | Profile-based Ollama/llama.cpp/vLLM backend selection; independent SearXNG and Home Assistant MCP tools | Capability registration, no silent remote endpoint, real runtime health, IoT entity allowlist and high-risk approvals |

### Backend/quality constraints

- GGUF `Q4_K_M` is a **candidate quantization**, not a universal optimum:
  compare accuracy, memory and latency with the same task set.
- vLLM and TensorRT-LLM have platform/hardware support restrictions; select
  them by provider capability, never by hardcoded device name.
- **TTFA under 500 ms** and **3–4x prompt acceleration** are experiment
  hypotheses, not guaranteed results. Measure p50/p95 (wake to detection,
  end-of-speech to transcript, LLM TTFT, TTS TTFA, first playback, p95
  end-to-end) for each installed backend without logging user audio/text.
- GraphRAG index generation can consume significant resources. Reuse
  existing AURA stores; do not require expensive offline reindexing on startup.
- SearXNG already exists; its JSON API must be enabled in the instance. Do
  not duplicate the permission-gated search capability.
- Home Assistant local API: secrets only server-side, hardcoded loopback or
  allowlisted private host, read-only inventory first, scoped `call_service`
  only after MCP Gateway authorization/approval. No general arbitrary URLs.

## Future PR merge order

1. Finish and manually validate HUD PR #51 on the user's Windows system.
2. Merge #51 only after operator acceptance and green CI.
3. Rebase this separate foundation onto updated main, verify release-lock
   manifest and Core tests, then wire native streaming providers and
   player into a new explicit capability release.
4. Benchmark under recorded, reproducible workloads before changing defaults.

### Reference implementations

- https://github.com/k2-fsa/sherpa-onnx
- https://github.com/ggml-org/whisper.cpp
- https://github.com/thewh1teagle/kokoro-onnx
- https://github.com/microsoft/graphrag
- https://github.com/ggml-org/llama.cpp
- https://docs.vllm.ai/en/latest/
- https://docs.searxng.org/dev/search_api.html
- https://developers.home-assistant.io/docs/api/rest/
