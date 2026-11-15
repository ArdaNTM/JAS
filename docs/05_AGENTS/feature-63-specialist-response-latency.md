# Feature #63 — scoped specialist response latency (partial)

`aura_core.application.specialist_performance` pairs real JAS
`SwarmStepRequested` / `SwarmStepCompleted` KernelEvent observations
by exact principal/task, step index and specialist role. It reports
bounded nearest-rank p50/p95 **Gateway response** latency, request/response
counts, incomplete steps, denied/approval-required decisions, and
individual coder/researcher partitions. No event payload, principal ID,
task ID or tool argument is exported in the report.

Trust boundaries:
- KernelEvent timestamp is caller-supplied and **not independently
  attested**. The tool validates chronological ordering and bounded
  duration, but cannot certify actual runtime clocks.
- A `SwarmStepCompleted` event only observes a Gateway response,
  NOT a successful external tool execution, finished job or Owner grant.
- Every result keeps `authorization_checked=False`,
  `clock_provenance_verified=False`,
  `actual_execution_verified=False`,
  `performance_certified=False`.
- The collector must first authenticate principal/task and authorize
  event access; this module neither subscribes to EventBus nor invokes
  MCP tools, modifies scheduling, collects new privileged metrics or
  creates an autonomous evaluator.
- Maximum 512 records and 32 step indices. Duplicates, invalid decisions,
  role changes, negative or >1h clock intervals, naive timestamps and
  malformed scopes fail closed. No unrelated principal events are included.

Feature #63 is TESTING/PARTIAL pending signed/verified telemetry,
benchmarked live agent outcomes, provider-integrated traces, consent and
independent performance acceptance. Tests cover real KernelEvent
construction, percentile calculations, role isolation, incomplete
responses, mismatched scopes and bad clocks.

`cd core && uv run pytest -q tests/test_specialist_performance.py`,
full Core Assurance, Remote Persistence and Final Release Lock.
