# Batch 4 — live integration

## Live MCP capability discovery

When the application lifespan has successfully registered the research and TTS MCP providers, it lists tools from each connected provider and stores validated proposals in `DynamicCapabilityDiscovery`. A discovery failure is logged and does not make an otherwise healthy provider fail startup.

The API surfaces are:

- `POST /api/capabilities/discover/{provider_id}` with `{"category":"research"}`: query a currently registered, connected MCP provider and create proposals.
- `GET /api/capabilities/proposals`: list current in-memory proposals.
- `POST /api/capabilities/proposals/{proposal_id}/approve` with `{"confirmed":true}`: register the capability metadata after an explicit confirmation from a local client.

Proposals are in-memory and disappear on restart. Approval registers metadata only. It does **not** add an allow policy, grant permissions, or guarantee the tool is executable. The existing `PermissionEngine` remains authoritative and `MCPGateway` checks each invocation. Newly discovered tools need a reviewed capability-to-operation mapping and an explicit policy before any execution can be allowed. The approval endpoint is restricted to loopback clients, but this local API is not a substitute for authentication if the server is exposed beyond the local machine.

## Adaptive reasoning execution

`POST /api/reasoning/execute` now uses `AdaptiveTaskOrchestrator`. Each attempt creates a new task and submits it through the existing `AgentTaskService`, so all tool calls continue through `AgentExecutor` and `MCPGateway`.

- Maximum one recovery/replan by default.
- Clearly transient `TimeoutError`, `ConnectionError`, or `OSError` may be retried once.
- Unknown exceptions are not retried.
- A failed result whose reason indicates authorization/permission denial stops immediately.
- Successful execution with no result may trigger one bounded replan.
- The response includes a `recovery` decision trace.

This is a bounded research adapter, not a general-purpose self-modifying agent. It does not retry side-effecting actions.

## Proactive context and UI/API feed

The Kernel's existing `EventBusLiveBridge` now feeds the read-only `ProactiveSuggestionStore` as well as the live event broker. `AgentExecutor` publishes `TaskSucceeded` or `TaskFailed` with task/plan identifiers and failed step IDs. The store applies an allow-listed observer, deduplicates by event/correlation, and retains at most 100 recent suggestions in memory.

- `GET /api/proactive/suggestions?limit=50` returns a bounded read-only feed.
- Existing WebSocket live events continue to stream through `LiveEventBroker`.
- Suggestions require user review and cannot invoke tools.

The suggestion feed is in-memory, not durable task history. Durable context, per-user isolation, retention/deletion, and cross-session memory remain separate work.

## Windows verification

Run the new focused tests first:

```powershell
cd D:\AURA\JAS\core
uv run pytest -q tests/test_batch4_api.py tests/test_adaptive_orchestrator.py tests/test_proactive_store.py tests/test_capability_discovery.py tests/test_adaptive_execution.py
```

Then run the full suite:

```powershell
uv run pytest -q
```

Live provider discovery is exercised only when the normal application lifespan starts connected MCP servers. Use the local AURA instance to verify that proposals appear after startup, that an unconfirmed approval returns HTTP 409, and that `confirmed=true` registers metadata without granting execution permission. Check that task completion/failure appears once in `/api/proactive/suggestions` and that denied Gateway calls do not trigger retries.
