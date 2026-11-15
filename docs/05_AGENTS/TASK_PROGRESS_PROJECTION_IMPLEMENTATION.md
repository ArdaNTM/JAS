# Feature #5 — bounded task status projection

The existing `TaskStateMachine` now exposes `status_projection(principal_id, limit=20)`: a **read-only**, principal-scoped aggregation of counts by existing `TaskState` and the most recently updated task status metadata (maximum 50). It performs only parameterized SQLite SELECT queries and does not include task goals, results, errors, tools or prompts in the output.

This is a local interface for future task status/HUD components, not a new scheduler or permissions system. `authorization_checked=False` accurately declares that this low-level store does not authenticate a principal; callers **must** enforce the existing app and Permission Engine boundary. Records are labelled `untrusted` to prevent status metadata being used as instructions.

Feature #5 is partial: no user-facing goals panel, long-term priority scheduler, independent owner acceptance or live UI E2E yet. Existing task state transitions and events are unchanged. Feature #97 live dashboard not claimed.

Tests: `cd core && uv run pytest -q tests/test_task_status_projection.py`; full Core Assurance and Release Lock must pass. No real hardware test.
