# Features #48 and #56 — runtime performance evaluation (partial)

This PR adds a deterministic Python standard-library aggregator on top of the
existing `RuntimeProfiler` and `RuntimeMeasurement`. It computes bounded
per-component/operation descriptive mean, p95, maximum latency, total CPU time,
and peak sampled RSS from already recorded observations. An optional latency
budget produces an *advisory* comparison flag only.

No new timer, agent, scheduler, API endpoint, tool execution, model call,
permission, external service or hardware access. Every result states
`hardware_verified=False`, `acceptance_verified=False`,
`can_execute=False`. Data are observational telemetry, not evidence that
AURA is reliable, energy-efficient, successful or production-ready.

Inputs are capped at 1,000 measurements and 50 operation identities; invalid
NaN/infinity, negative values, path-like component names, boolean-as-number
values, oversized collections and illegal budget values fail closed.
Energy/cost/FLOPs estimates from RuntimeProfiler are deliberately NOT
treated as measured results.

Test: `cd core && uv run pytest -q tests/test_runtime_evaluation_summary.py`
including an integration sample from the existing RuntimeProfiler publisher,
plus full Core Assurance and Final Release Lock. Real longitudinal quality
evaluation, persistence, actor scope, attribution and hardware acceptance
remain open. Features #48 and #56 are partial.
