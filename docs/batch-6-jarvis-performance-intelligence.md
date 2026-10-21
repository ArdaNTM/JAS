# Batch 6 — JARVIS performance and intelligence

## Included

- **Bounded asynchronous inference:** `AsyncWorkCoordinator` offloads synchronous LLM inference to worker threads, caps concurrent operations using `AURA_MAX_CONCURRENT_INFERENCE` (default 4), and tracks active/completed/failed work. `/api/assistant/respond` is now async and no longer blocks the event loop during synchronous model inference. STT already runs off-thread; TTS continues through the asynchronous MCP Gateway.
- **Predictive preflight simulation:** `POST /api/reasoning/simulate` returns the deterministic reasoning plan and static risk findings before any tool execution. It identifies high-risk declared steps, missing dependencies, unusually large arguments, and large plans. It is deliberately conservative and does not replace permission checks or execute a tool.
- **System telemetry:** `GET /api/runtime/telemetry` samples CPU, memory, and network counters when optional `psutil` is installed. If unavailable, it returns a clear degraded status instead of failing. Configurable CPU/memory warning thresholds are `AURA_CPU_WARNING_PERCENT` and `AURA_MEMORY_WARNING_PERCENT`. Resource pressure can be published to the Kernel EventBus and converted into a proactive suggestion. Recommendations are advisory: the system does not kill or cancel user work.
- **Concurrency status:** `GET /api/runtime/concurrency` reports active/completed/failed work and configured capacity.
- **Context synthesis:** the assistant builds a bounded natural-language prompt from the current message, research evidence, semantic chat memory, and—when `AURA_CHAT_MEMORY_ENABLED=1`—the scoped SQLite episodic memory from Batch 5. Tone can be set using `AURA_CHAT_TONE=adaptive|concise|warm|formal|light`. Recalled memory is treated as untrusted reference data rather than higher-priority instructions.

## API examples

Simulate a research plan without executing it:

~~~http
POST /api/reasoning/simulate
Content-Type: application/json

{"directive":"Araştırma yap ve sonuçları karşılaştırıp özetle."}
~~~

Inspect runtime concurrency and telemetry:

~~~http
GET /api/runtime/concurrency
GET /api/runtime/telemetry
~~~

## Important boundaries

- Simulation is a deterministic heuristic, not a learned world model; it cannot guarantee real-world outcomes or discover undocumented side effects.
- Telemetry is sampled when the endpoint is called; this package does not yet run a continuous background sampler. Poll the endpoint from the UI for near-real-time updates.
- The coordinator bounds blocking inference and memory operations. It does not yet parallelize dependency-connected steps inside a single AgentExecutor plan; existing task execution and MCP Gateway authorization behavior are unchanged.
- No automatic permission changes, arbitrary code execution, provider installation, or background side-effecting action is introduced. Tool invocations remain subject to MCPGateway and PermissionEngine.
- The optional psutil dependency is not added as a mandatory install; install it in the environment to enable host metrics.

## Verification (PowerShell)

~~~powershell
cd D:\AURA\JAS\core
uv run pytest -q tests/test_batch6_intelligence.py tests/test_batch6_api.py
uv run pytest -q
~~~

Run the focused tests and full suite locally before merging. Also verify `/api/assistant/respond` against the configured local inference provider and enable `AURA_CHAT_MEMORY_ENABLED=1` only after selecting a protected local memory directory.
