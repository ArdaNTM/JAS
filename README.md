# JARVIS Architecture Specification (JAS)

Official architecture specification and implementation repository for the JARVIS / AURA system.

This repository contains:

- the JAS architecture and version-governance source of truth;
- AURA Core implementation under `core/`;
- AURA desktop/web UI under `aura-ui/`;
- acquisition, ADR, documentation, templates, and version-lock material;
- deterministic release-lock artifacts.

## Architecture

JAS remains the architecture and version-governance authority.

AURA Core provides the deterministic execution foundation:

`Kernel → ServiceRegistry / CapabilityRegistry / ProviderRegistry → PermissionEngine → MCP Gateway → Provider`

Provider implementations are not allowed to bypass the capability and authorization boundary.

The local inference baseline is Ollama with the locked Qwen3 configuration defined by the JAS version-lock documents.

## Repository layout

- `core/` — AURA Core runtime, APIs, security, MCP, agent execution, tests, and release tooling.
- `aura-ui/` — AURA React/Vite/Electron user interface.
- `docs/` — architecture and approved-stack documentation.
- `version_lock/` — version-lock and release-governance source material.
- `acquisition/` — host and acquisition evidence.
- `adr/` — architecture decision records.
- `release-manifest.final.json` — deterministic SHA-256 release lock for the selected implementation files.

## Local STT acceleration and bounded background reflection

Local speech recognition uses `faster-whisper`. Runtime selection is configurable:

- `AURA_STT_MODEL=medium` selects the default quality model; choose `small` for lower latency or another installed Whisper model when appropriate.
- `AURA_STT_DEVICE=auto` detects a CTranslate2 CUDA device and otherwise uses CPU. Set `cuda` to require CUDA or `cpu` to disable GPU use.
- `AURA_STT_COMPUTE_TYPE=auto` selects `float16` for CUDA and `int8` for CPU. Supported explicit values include `float16`, `int8`, `int8_float16`, `float32`, and `bfloat16` (subject to device support).
- `AURA_STT_BEAM_SIZE=3` controls the bounded beam size (1–10); raise it to trade latency for possible accuracy gains.
- `AURA_STT_CPU_THREADS=8` bounds CPU thread use (1–16) when the CPU path is selected.
- `AURA_STT_INITIAL_PROMPT` overrides the Turkish base prompt.
- `AURA_STT_PRINCIPAL_ID=local_default` selects the isolated episodic-memory scope used for optional context terms; `AURA_STT_CONTEXT_CACHE_SECONDS=60` bounds how often terms are refreshed.

The context-aware adapter extracts a short, sanitized list of domain terms from the selected principal's existing episodic memories. It does not pass recalled memory instructions to the recognizer, invoke another model for each recording, or train/fine-tune Whisper. If memory is unavailable, transcription falls back to the static Turkish prompt. Context can help with names and jargon, but cannot guarantee recognition or eliminate model latency.

Continuous background reflection is opt-in and disabled by default. To enable bounded idle-time suggestions, set:

- `AURA_BACKGROUND_THINKING_ENABLED=1`
- `AURA_BACKGROUND_THINKING_PRINCIPAL_ID=local_default`
- `AURA_BACKGROUND_THINKING_IDLE_SECONDS=300`
- `AURA_BACKGROUND_THINKING_INTERVAL_SECONDS=900`
- `AURA_REFLECTION_DB=./data/background-reflection.sqlite3`

The worker examines at most 20 existing records per cycle and stores at most five deterministic, lexical candidate links. It does not rewrite source memories, call an inference provider, grant permissions, invoke tools, or execute actions. Suggestions are reviewable data available from `/api/background-thinking/proposals`; status is available from `/api/background-thinking/status`. Both endpoints are local-client-only. This is bounded memory housekeeping, not unconstrained autonomous reasoning or model self-training.

CUDA availability and precision depend on the installed CTranslate2 build, NVIDIA driver, CUDA runtime, and hardware. Automatic mode safely selects CPU INT8 when CUDA is unavailable. Measure end-to-end latency on the target machine before deciding whether GPU acceleration is active.

### STT runtime fallback

If CUDA model initialization fails (including unsupported `float16` or missing runtime libraries), Core logs a safe diagnostic and retries model loading with CPU `int8`. If CUDA initializes but fails during inference or lazy segment decoding, Core retries that recording once with CPU `int8`. The retry is bounded to one CPU attempt to avoid loops. A context-adapter, episodic-memory, or invalid context-cache setting failure falls back to `AURA_STT_INITIAL_PROMPT` (or the built-in Turkish prompt) and does not prevent transcription. The API continues to hide raw exception strings and local paths from UI responses.

## Validation

The implementation is validated by the Core Python test suite, frontend production build, and release-lock verification scripts.

The release lock covers the implementation files selected by `core/scripts/generate_final_lock.py`. Generated caches, virtual environments, dependency installation directories, build output, and backup artifacts are excluded.

## Status

The repository contains implementation code. Real-world infrastructure/provider validation remains separate from deterministic source-level validation; live PostgreSQL/Qdrant, Ollama inference, browser/voice/vision/computer providers, and final environment-specific deployment checks must be validated on the target host before claiming full production deployment readiness.
