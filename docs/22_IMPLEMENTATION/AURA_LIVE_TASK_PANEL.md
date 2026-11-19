# Feature #97 — live durable task-state panel (Draft stacked on #146)

This is an actual opt-in, zero-cloud FastAPI JSON endpoint backed by the
existing AURA TaskStateMachine, not static or fabricated task data.

## Composition and security
- AURA_LIVE_TASK_PANEL_ENABLED=1 registers a real MCP provider and capability
  visualization.tasks.read in the existing Service, Provider, Capability
  registries. No policy is automatically granted.
- GET /api/runtime/tasks requires configured HTTP bearer authentication,
  exact principal binding, and a new PermissionEngine ALLOW through the
  existing MCP Gateway on every request.
- The provider requires a short-lived actual Gateway dispatch grant. Owner
  identity is extracted from the grant only. Caller filters cannot widen it.
- Existing SQLite and PostgreSQL task stores now implement bounded SQL
  SELECTs filtered by principal_id, sorted by update time, LIMIT 64.
- Real EventBus TaskCreated/TaskReady/TaskStateChanged messages provide
  refresh notifications only; they cannot overwrite authoritative DB state.
- Only safe task IDs, state, timestamps and revision are returned.
  Goals, errors, results, token material and tool arguments are excluded.
  HTTP JSON uses no-store, nosniff and restrictive CSP.

## Tests
- cd core && uv run pytest -q tests/test_live_task_panel.py
- cd core && uv run pytest -q
- cd core && uv run python scripts/verify_final_lock.py

Positive tests exercise actual in-memory SQLite and task state transitions,
Core EventBus, registrations, PermissionEngine, MCPGateway and FastAPI.
Negative tests include default DENY, REQUIRE_APPROVAL, cross-owner data,
unconsumed dispatch, forged events/rows, injection, wrong bearer and HTTP
403/503, provider secret redaction and SQL query limit enforcement.

## Unverified acceptance
Real native Electron transparent multi-monitor panel, visual rendering,
screen-reader accessibility, cross-process authenticated event provenance,
Windows performance, production Owner enrollment and acceptance are not
verified. This is a genuine working data source for a future HUD, but
feature #97 must stay TESTING/PARTIAL_VERIFIED after exact-head green CI.
No physical or computer control authority is added.
