# Feature 008 — bounded, review-only memory conflict candidates

Status: **partial implementation; pending CI and human review**. This is an implementation note, not a replacement for JAS memory architecture or authorization policy.

`EpisodicMemoryStore.find_conflict_candidates(principal_id=..., limit=20, scan_limit=500)` uses the existing scoped SQLite table. Only records of kind `fact` with **exactly one explicit** `fact:<key>` tag (lowercase ASCII alphanumeric plus `_.-`, max 48 characters) are compared. For each key, the newest and first older *different literal* values are returned as a potential discrepancy.

- Results include bounded 160-character previews, record IDs, `NEEDS_HUMAN_REVIEW`, and `untrusted=true`; they are **not** proof of semantic contradiction.
- No records are changed, deleted, preferred or promoted. `last_accessed_at` is unchanged by review.
- No LLM, cloud provider, tools, PermissionEngine decisions, MCP authorization or other principals' memory are accessed.
- Caller authentication/authorization remains the responsibility of the existing application boundary; this store method does **not** expose a new network route or grant a capability.
- Data are still potentially sensitive; an authorized caller must not forward previews outside the principal's boundary.

Limitations: literal matching misses paraphrases and temporal facts; historical scan is capped and may miss older facts. Conflict resolution, source confidence, versioned updates, human approval and downstream index propagation remain future, separately reviewed work.

Test: `cd core && uv run pytest -q tests/test_memory_conflict_candidates.py`; full CI and release-lock verification must also pass. No hardware claim.
