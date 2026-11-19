# Feature #33 — real durable explicitly reviewed command sequences

Draft #152 stacked on #151 (Docker terminal) and canonical #150 (#26).

## Runtime
- The existing TaskStateMachine (SQLite on local, PostgreSQL on remote)
  stores a genuine dependency chain of 1–6 UUID task records. Each task
  includes a trusted-format command ID and an HMAC-SHA256 proof bound
  to the current principal, task UUID, previous dependency and command.
  This prevents unrelated/forged TaskStateMachine goals becoming executable.
  HMAC key is supplied by trusted Owner composition, minimum 32 bytes.
- Separate Core Service/Capability/Provider registration:
  workflow.commands.plan (MEDIUM, exact workflow/commands/plan)
  workflow.commands.advance (HIGH, exact workflow/commands/advance).
  Both require their own explicit PermissionEngine ALLOW.
- Advance uses the real local/remote TaskStateMachine state: only READY
  tasks can request terminal approval. On confirmation it records RUNNING
  *before* invoking the independently governed #27 terminal. Only the
  terminal's independently consumed single-use human approval can
  dispatch the fixed image/command profile. SUCCEEDED frees the next
  dependency; nonzero exit/exception blocks dependents. Ambiguous
  outcomes stay RUNNING, never automatically retried.
- Nothing autonomously advances the next step, even after SUCCESS.
  No model-generated shell, direct provider calls or foreign-owner task
  edits. Errors and tool output are not saved into the task ledger.
  EventBus publishes bounded state-change metadata.
- Optional AURA_COMMAND_SEQUENCES_ENABLED requires #27 enabled and
  an independent AURA_COMMAND_SEQUENCE_HMAC_KEY (64 hex chars). HTTP
  endpoints require the existing bearer principal plus Gateway policy.

## CI evidence
- cd core && uv run pytest -q tests/test_governed_command_sequences.py
- cd core && uv run pytest -q
- cd core && uv run python scripts/verify_final_lock.py

Real SQLite tests cover persisted plans and dependency edges, restart,
nested Gateway approvals, no automatic action, replay refusal,
cross-owner denial, tampered HMAC/task rejection, default deny and
separate plan/advance policies, real subprocess failure propagation
and HTTP 401/403/422. A state-machine SUCCESS branch uses a test
replacement for external execution; **this is not a live Docker smoke**.
Actual Docker isolation requires separate pinned local-image and
broker/Owner acceptance from feature #27.

## Acceptance blockers
This is manually stepped bounded command orchestration, not an autonomous
unrestricted OS agent. Real Docker execution success, authenticated
cross-process attestation, concurrent multi-process plan creation
atomicity, crash recovery/Owner reset of RUNNING, signed manifest and
Windows process/sandbox acceptance remain missing. The F2.7 sealed
broker security contract is unchanged; PR #64–#111 full cumulative
release integration is not proven. TESTING/PARTIAL_VERIFIED only after
exact-head CI, never COMPLETED.
