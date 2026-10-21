# Batch 9 — Local Ultimate Intelligence

## Scope and safety posture

Batch 9 adds local-first building blocks. No paid cloud API is required by these paths. Ollama endpoints are constrained to loopback; embeddings use a local model directory and local_files_only=True. These modules do not replace AURA Core's deterministic Kernel, registries, Permission Engine, EventBus, or MCP Gateway.

## Local semantic vector memory

- LocalSentenceTransformerEmbedder loads a sentence-transformers model from a pre-existing local directory and refuses model downloads.
- LocalVectorMemory stores vectors in SQLite and ranks them with cosine similarity.
- Records are filtered by principal_id; returned memory is marked untrusted_reference_data.
- Install the optional open-source runtime package only when needed: uv pip install sentence-transformers. Manually obtain a compatible model directory beforehand, then configure:
  - AURA_EMBEDDING_LOCAL_PATH — local directory for the model
  - AURA_EMBEDDING_DEVICE=cpu — CPU default
  - AURA_VECTOR_MEMORY_DB=./data/local_vector_memory.sqlite3
- APIs: POST /api/memory/vector and POST /api/memory/vector/recall. They are local-client-only and return 503 when no local model path is configured.

## Local vision

- LocalOllamaVisionProvider supports Ollama-compatible local vision models, such as Qwen-VL or LLaVA.
- POST /api/vision/analyze accepts base64 image bytes and a bounded prompt. The image is capped at 8 MiB.
- Configure AURA_VISION_MODEL and AURA_VISION_BASE_URL (default http://127.0.0.1:11434). Non-loopback and cloud URLs are rejected; no cloud fallback is attempted.
- Pull/install the model locally using your Ollama installation before using this endpoint. Vision is exposed through an explicit local provider adapter; actual external tool calls remain governed by the existing Gateway path.

## Self-tool synthesis

- POST /api/tools/synthesize asks the configured local inference backend for a candidate Python helper.
- POST /api/tools/proposals validates a submitted candidate.
- Candidates must provide a top-level run(data) function, have bounded source length, and pass a restrictive AST policy.
- Important: Python AST checks are not a secure sandbox. Batch 9 does not execute candidate code and does not register it in Capability Registry. It reports sandbox_execution=not_performed and requires a future OS-isolated runner, human approval, tests, and registry/gateway integration before execution can be enabled. This is intentionally fail-closed.

## Predictive prefetching

- PredictivePrefetchPlanner learns repeated event/capability/hour patterns in a local SQLite database and emits bounded, principal-scoped proposals.
- POST /api/prefetch/observe accepts explicit observations; GET /api/prefetch/proposals lists proposals for one principal.
- Optional Kernel EventBus observation is enabled with AURA_PREFETCH_ENABLED=1. It only learns from events explicitly carrying principal_id, prefetch_capability_id, and local_hour (optionally prefetch_event_key). No provider call is made from an event handler.
- Every proposal remains pending approval. Speculative fetches are not automatically dispatched; a future approved dispatcher must construct a real MCPGatewayRequest and invoke MCPGateway so Permission Engine authorization remains mandatory.

## API and configuration

All new endpoints require a loopback client. Automatic prefetch observation is off by default. Vector memory is opt-in by configuring a local model path. No dependency was added to the default install or lockfile.

## Tests

Run from core:

```powershell
uv run pytest -q tests/test_batch9_local_intelligence.py tests/test_batch9_api.py
uv run pytest -q
```

The repository authoring environment cannot execute the user's local Python environment. Run these tests before merging the PR; do not treat the commit itself as evidence of passing tests.