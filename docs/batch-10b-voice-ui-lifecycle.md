# Batch 10B — 3D UI and voice lifecycle

## Scope

Batch 10B connects the existing 3D dashboard and voice response bridge to the shared UI–Core API client and the versioned contract introduced in Batch 10A.

- On startup, the dashboard requests `GET /api/ui/v1/contract` through `getUIContract()` and reports the negotiated contract version.
- `AuraApiError` is used to display structured error codes and request IDs rather than reducing failures to uncorrelated strings.
- `aura-ui/src/voice/sessionState.ts` maps microphone capture and Core operation states into a UI lifecycle: `idle`, `listening`, `processing`, `awaiting_approval`, `responding`, `speaking`, and `error`.
- The 3D reactor/hologram activity and status label follow that lifecycle.
- The voice bridge reports response generation, playback, and failure states through a stable callback.

## State and safety behavior

- Voice transcription only fills the command field. The user must explicitly press ENTER before a directive is submitted.
- `awaiting_approval` is a blocking state: command submission and voice capture remain disabled, and the UI does not auto-approve, retry, or dispatch the pending operation.
- `failed`, `cancelled`, and `timed_out` are terminal UI states; the UI does not automatically rerun the task.
- Provider selection remains server-side. The UI calls AURA Core's API client and does not call Ollama or another provider directly.
- All real tool execution remains behind MCP Gateway and Permission Engine authorization. This UI state machine is not an authorization mechanism.
- The UI does not claim an approval is complete merely because the user interacted with the page. Resolving approvals remains the responsibility of the authorized Core flow.

## Manual verification

From `aura-ui`:

```powershell
npm run build
```

Suggested smoke checks against a running local Core:

1. Start the UI with Core available; confirm telemetry reports `UI CONTRACT v1.0 READY`.
2. Start voice capture; confirm the 3D status reports listening, then processing while transcription runs.
3. Confirm the transcript only populates the command field; it must not execute until ENTER is pressed.
4. Submit a valid directive; confirm the UI shows processing, then response/speaking if assistant speech is available.
5. Force an API error and confirm the visible error includes the structured error code and request ID when returned.
6. Simulate or observe an `awaiting_approval` task response; confirm command/voice controls remain blocked and the UI explicitly says execution is waiting for authorization.
7. Confirm failed/cancelled/timed-out tasks do not trigger an automatic retry.

The GitHub authoring environment did not run `npm run build` or browser-level smoke tests; those results must be confirmed locally after checkout.
