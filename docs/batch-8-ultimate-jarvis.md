# Batch 8 — Ultimate JARVIS Intelligence

## FastAPI lifecycle

The telemetry daemon now starts and stops through FastAPI's `lifespan` context manager. The deprecated `@app.on_event` hooks have been removed from `create_api`.

## Deep semantic memory

`EpisodicMemoryStore.recall_related` performs bounded, deterministic local concept/tag retrieval scoped by `principal_id`. It ranks shared concepts, tags, importance, and memory kind, including preferences and `reasoning` records. It is a lightweight lexical-semantic association layer, not a claim that embeddings or a remote vector database are used by this path. The existing SQLite schema is extended compatibly because `kind` is stored as text.

Local endpoints:

- `POST /api/jarvis/memory` — persist preference, fact, episode, goal, lesson, or reasoning.
- `GET /api/jarvis/memory/related?principal_id=...&query=...` — retrieve related records.
- `DELETE /api/jarvis/memory/{memory_id}?principal_id=...` — explicitly delete a scoped record.

Memory text is always untrusted context, not instructions. Retrieval never crosses principal scopes. Automatic assistant memory remains opt-in with `AURA_CHAT_MEMORY_ENABLED=1`.

## Cross-capability reasoning

`POST /api/reasoning/cross-capability` accepts 1–16 already-collected evidence items tagged with capability and provider IDs, then synthesizes agreement, conflicts, uncertainty, and a bounded decision through the configured inference service. This endpoint does not execute tools itself. Its evidence must originate from tool calls that have already traversed `MCPGateway` and `PermissionEngine`. The endpoint is local-client-only, caps evidence payload sizes, and can enrich synthesis from the same principal's scoped semantic memory when chat memory is enabled. Successful syntheses can be saved as `reasoning` memories.

## Test

Run from `core`:

```powershell
uv run pytest -q tests/test_batch8_ultimate_jarvis.py tests/test_jarvis_api.py tests/test_batch6_api.py
uv run pytest -q
```

The repository changes were committed and pushed via GitHub API. Tests were not executed in the authoring environment; use the local suite as the merge gate.
