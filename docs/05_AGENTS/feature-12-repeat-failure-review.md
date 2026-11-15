# Feature #12 — repeating failure review

Status: PARTIAL implementation. Extends existing `SelfAdaptationEngine`
without creating a new agent, scheduler, executive capability or policy.

`repeated_failure_reviews(min_occurrences=2, limit=10)` scans at most the
current 500 observations. Only a hard-coded allowlist of failure classes can
appear in output; free-form error strings, prompts, task IDs and secrets are
never returned. Evidence count is the number of distinct failed task IDs,
not retries or repeated reports for one task. Observations without task ID
cannot establish repeated independent tasks.

The output is *review-only*: permission and validation denials never
suggest any bypass. Timeout/provider hints do not authorize execution;
approval remains external, and the method neither calls `propose()`,
`approve()`, nor `MCPGateway`.

Known limitation: existing `SelfAdaptationEngine` is per-instance and
does not provide principal-identity isolation or durable learning records.
Instantiate only inside an already scoped, authenticated service; do not
expose or aggregate this in a multi-principal API without further identity
partitioning, privacy and retention tests. This does not complete feature
#12's longer-term goal of demonstrated improvement across task outcomes.

Tests: `cd core && uv run pytest -q tests/test_repeat_failure_reviews.py`
plus full Core Assurance and release-lock gate. No external packages or cloud.
