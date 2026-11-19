# Principal-bound governed episodic memory — feature #104 (partial)

**Existing source of truth:** `aura_core.application.episodic_memory.EpisodicMemoryStore` (SQLite principal-scoped `remember`, `recall`, `forget`) and the authoritative Core `PermissionEngine`. The new opt-in `aura_core.memory.governed_access.GovernedEpisodicMemory` adapter adds per-operation authorization without creating a second memory store, provider, PermissionEngine, MCP tool or implicit policy.

## Trust and authorization contract
- Trusted Core composition supplies the **already authenticated** principal ID when creating a bound adapter. Public `recall`, `remember`, `forget` methods cannot accept a different caller-chosen principal.
- Every operation builds a bounded `AuthorizationRequest` with distinct request ID, exact `memory/episodic/<percent-encoded-principal>` scope, `memory.episodic.read`/`memory.episodic.write` capability and separate `memory.recall`, `memory.remember`, `memory.forget` operation IDs.
- Existing `PermissionEngine.authorize` must return explicit `ALLOW`. Missing/unregistered capability, denied/deferred/requires-approval decision, misconfigured policy or engine failure denies before the SQLite store is touched. The adapter does **not** consume human approvals or execute any external tool; MCP tool invocations still require MCP Gateway.
- Writes return only a metadata-only receipt. Reads return immutable `MemoryEvidence` with `trust='UNTRUSTED'`; memory text is never an instruction or a permission grant. Forgetting an ID owned by another principal yields the same `False` as a nonexistent ID from this caller's scope.
- API input, result counts, tags, memory kind/UUID and text sizes are bounded. Actual sqlite database errors are wrapped without file paths/record content in exposed messages.

## Verification
`cd core && uv run pytest -q tests/test_governed_memory_access.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Positive/negative tests use **real** SQLite database files, Core ServiceRegistry/CapabilityRegistry, PermissionEngine, policies, denial auditing, cross-principal data, scoped deletion, malformed requests and exception redaction. Do not claim full production acceptance from tests alone.

## Outstanding production and security gaps
- **Not encryption at rest.** The underlying SQLite store still persists cleartext content. No OS/TPM key custody, SQLCipher, secure deletion from backups, storage ACL attestation, audit-proof retention, owner identity verification or application-wide key rotation exists in this PR.
- A privileged process with direct access to SQLite or an unguarded existing memory store can bypass this optional adapter. All production entry points and MCP tools must be wired to authenticated principal and appropriate PermissionEngine/Gateway boundaries; the composition root is **not** changed in this isolated slice.
- Human permission prompts, consent records, session lifecycle, real multi-user identity, backup/restore, privacy audit and Owner acceptance are still unverified. Feature #104 remains TESTING/PARTIAL_VERIFIED, not COMPLETED.
- No new dependencies, external provider, model/API/license terms or automatic permission rules. Main pinned and all existing PRs remain unmerged.
