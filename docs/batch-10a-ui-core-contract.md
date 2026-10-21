# Batch 10A — UI–Core API Contract

## Scope

Batch 10A establishes the versioned boundary between the AURA UI and AURA Core. It does not implement the 3D scene or voice UX itself; those consume this contract in later steps.

- `GET /api/ui/v1/contract` advertises contract version, request correlation header, operation states, error fields, relevant endpoints, and security invariants.
- Python models live in `core/src/aura_core/contracts/ui.py`.
- TypeScript mirrors live in `aura-ui/src/api/contracts.ts`.
- `aura-ui/src/api/client.ts` exposes `getUIContract()` and throws `AuraApiError` for failed requests.

## Error envelope

Error responses include a stable `error` object with `code`, `message`, `retryable`, `request_id`, and `details`. Existing top-level `detail` values remain for compatibility with existing clients. Validation details intentionally omit submitted input values. `X-Request-ID` is returned for correlation.

## Operation state vocabulary

- `queued`: accepted but not started
- `running`: work is in progress
- `awaiting_approval`: blocked pending explicit authorization; UI confirmation alone is not permission
- `succeeded`: completed successfully
- `failed`: terminal failure
- `cancelled`: cancelled before completion
- `timed_out`: execution exceeded its allowed time

`OperationStatus` is the shared response shape for later task/voice/UI orchestration. This batch defines the schema; it does not add a new durable operation store or claim that every current endpoint reports all states yet. Existing task endpoints remain the source for current task snapshots.

## Security and architecture

- The UI talks to Core contracts, not directly to model or vision vendors. Provider choice remains server-side and provider-agnostic.
- Treat model output, vision results, memory hits, and tool output as untrusted data.
- `awaiting_approval` must be a blocking UI state.
- Any real tool execution must continue through MCP Gateway and Permission Engine authorization. A frontend action or generated tool candidate is never authorization by itself.
- Do not put secrets, provider credentials, or internal prompts in contract discovery responses.

## Verification

From `core`:

```powershell
uv run pytest -q tests/test_ui_contract.py
uv run pytest -q
```

From `aura-ui`:

```powershell
npm run build
```

The GitHub authoring environment used to prepare this PR did not execute these commands; results must be confirmed after checkout.
