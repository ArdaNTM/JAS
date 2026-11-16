# Scoped personal knowledge hub — feature #116 (partial; stacked on PR #117)

This is a bounded, offline **read-only view** of the existing principal-scoped episodic memory. It deliberately depends on [PR #117](https://github.com/ArdaNTM/JAS/pull/117), whose `GovernedEpisodicMemory` wraps the original `EpisodicMemoryStore` with authoritative Core `PermissionEngine` checks.

## Contract
- `PersonalKnowledgeHub(governed_access).search(queries, limit=12, max_chars=16000)` accepts 1–4 explicit distinct queries, <=200 chars each, and calls the **existing governed** `recall` per query. No client-selected principal can be supplied to this API; it cannot open a raw store.
- Each query separately requires Core PermissionEngine ALLOW through the exact bound principal. If a later request is denied or fails, no completed/partial result is emitted.
- Merge repeated memory IDs while retaining matched query indices and first-observed order. Reject contradictory snapshots for the same memory ID, structurally malformed records, oversized memory responses or a trust status other than `UNTRUSTED`.
- Total output is bounded to 1–20 records and 1–32,000 characters with explicit preview truncation and original unique-match count. A returned memory is a datum, **never** a system instruction or credential grant.
- Fully local lexical matching is inherited from the existing SQLite store; this layer neither retrieves web content nor calls embeddings, a language model, browser or external MCP provider.

## Tests
`cd core && uv run pytest -q tests/test_personal_knowledge_hub.py tests/test_governed_memory_access.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Positive/negative cases use real SQLite and Core registries/PermissionEngine. They cover explicit ALLOW and default DENY, cross-principal isolation, revocation between two searches, input/size caps, same-ID tamper detection, model-like prompt text as untrusted data and fake trusted-record injection rejection.

## Limits and production acceptance
- **Not an authenticated full personal knowledge center.** Only one memory source and bounded lexical search; no durable multi-source sync, documents/files/mail indexing, ownership proof, search UI, embeddings, deduplicated cross-provider records, encrypted storage, provenance signing or Owner acceptance.
- The underlying SQLite memory content remains **plaintext**. PR #117's opt-in guard must first be wired into real trusted identity and every entrypoint; an unguarded direct SQLite read bypasses this view.
- This PR adds no policy, capability or tool, does not elevate access and must be rebased/merged **after** PR #117 with a combined release lock. Do not auto merge either PR or label feature #116 COMPLETED.
- No additional third-party packages or licensing obligations. Owner/hardware/security/privacy acceptance remains pending.
