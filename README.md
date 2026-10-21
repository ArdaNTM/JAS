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

## Bounded autonomy, experiments, and continuous listening

The autonomy work follows the research patterns in [ReAct](https://arxiv.org/abs/2210.03629) (interleaved reasoning and observations), [Generative Agents](https://arxiv.org/abs/2304.03442) (memory/reflection/planning), [Voyager](https://arxiv.org/abs/2305.16291) (reusable skills with feedback and verification), and [SWE-agent](https://arxiv.org/abs/2405.15793) (a purpose-built, constrained agent-computer interface). These papers describe useful design patterns, not a guarantee of general intelligence.

### Restricted autonomy laboratory

- `POST /api/autonomy/plan/validate` validates a bounded, acyclic task graph. It does not schedule or execute the graph.
- `POST /api/autonomy/experiment` evaluates a small pure-expression language over JSON input. It rejects imports, function calls, attributes/introspection, assignments, comprehensions, and arbitrary Python. Input, syntax-tree, depth, time, exponent, and result sizes are bounded.
- Both endpoints require a local client. This is an experiment harness for deterministic calculations, not an OS-level sandbox for arbitrary generated programs. Do not treat it as a safe general-purpose Python execution environment.
- The response explicitly states that no tool execution or memory mutation took place. Real capabilities must still pass the Permission Engine and MCP Gateway. Proposed plans and experimental outcomes are not automatically promoted into trusted skills or memory.

### Opt-in continuous listening

The UI now exposes an explicit `SÜREKLİ DİNLE` control. It uses browser microphone permission, local Web Audio RMS voice-activity detection, and a bounded in-memory audio ring buffer to segment speech. Speech segments are sent to the configured local Core transcription endpoint. The user can stop listening at any time; leaving the page also releases the microphone. Captured speech only fills the directive field: it does not submit or execute the directive. ENTER remains a separate explicit execution step.

Microphone access is opt-in and visible, not secretly enabled on startup. Browser/device VAD thresholds vary; this is an initial local prototype, not a guarantee of studio-quality or always-correct detection. A later production hardening step should add browser-level tests for permission denial, device removal, long speech, and repeated segmentation.



### Proposed next architecture steps (not yet implemented)

#### Hierarchical memory

The next memory increment should separate three lifetimes rather than expanding the prompt indefinitely:

1. **Working context:** a bounded, task-scoped buffer holding the current goal, recent observations, active plan, unresolved questions, and references to relevant episodic records. Apply token/byte and age limits; summarize or evict by explicit policy.
2. **Short-term context window:** only the selected, sanitized working context is assembled into each model request. Retrieved text is data, never authority; recalled instructions must not override system policy or permissions.
3. **Long-term episodic memory (SQLite):** append-only task episodes with principal/task scope, timestamps, provenance, retention metadata, and explicit review/deletion behavior. Indexes and retrieval should be bounded; memory promotion or summarization must be auditable and must not grant capabilities.

A task checkpoint should persist the plan state and episode references so a long-running task can resume without treating old model output as trusted state. Before implementation, define schema migrations, isolation/retention rules, context-selection budgets, and tests for prompt injection in recalled content.

#### Isolated Python experiment runner

The restricted expression evaluator remains the only implemented experiment path; it is not arbitrary Python execution. A future runner should be a separate, opt-in capability behind the Permission Engine and MCP Gateway, with a narrow job API and no direct access to host credentials, user files, network, or production memory.

- **Pyodide/WebAssembly** is a possible first option for deterministic, browser-side experiments where supported packages and execution limits are sufficient. It still needs explicit CPU/time and memory limits, package allow-listing, and a clear boundary around browser-origin data.
- **Docker or another OS-level isolation boundary** may support backend Python tests, but only with a non-root user, read-only base filesystem, disposable per-job workspace, no host mounts or Docker socket, network disabled by default, resource/time quotas, pinned images/dependencies, and process cleanup. Containers alone should not be described as a complete security boundary.
- Both options need authorization before launch, bounded input/output, cancellation, audit events, and adversarial tests. Experiment results remain untrusted proposals until independently verified; they must not auto-edit trusted code, mutate memory, or promote skills.

These are design directions only. Neither Pyodide execution nor a Docker-backed Python runner is currently implemented.

### Research links

- ReAct — https://arxiv.org/abs/2210.03629
- Generative Agents — https://arxiv.org/abs/2304.03442
- Voyager — https://arxiv.org/abs/2305.16291
- SWE-agent — https://arxiv.org/abs/2405.15793
- OWASP Excessive Agency — https://genai.owasp.org/llmrisk/llm062025-excessive-agency/

## Validation

The implementation is validated by the Core Python test suite, frontend production build, and release-lock verification scripts.

The release lock covers the implementation files selected by `core/scripts/generate_final_lock.py`. Generated caches, virtual environments, dependency installation directories, build output, and backup artifacts are excluded.

## Status

The repository contains implementation code. Real-world infrastructure/provider validation remains separate from deterministic source-level validation; live PostgreSQL/Qdrant, Ollama inference, browser/voice/vision/computer providers, and final environment-specific deployment checks must be validated on the target host before claiming full production deployment readiness.
