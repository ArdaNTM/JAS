# Private SQLite visual memory — feature #82 (partial)

**Stacked on Draft PR #137**. This is an actual local SQLite persistence feature for **untrusted text descriptions and SHA-256 image digests**, never raw images. It composes the already authenticated `GovernedImageUnderstanding` local Ollama MCP Gateway reader with a separate permission-checked Core memory storage service. It does not introduce cloud storage, model weights, camera capture, arbitrary file access or executable instructions.

## Production path and Owner boundary

1. Trusted Core composition creates `SQLiteVisualMemoryStore(Path('/absolute/owner-private/visual.sqlite3'))`. The parent must exist and be private on POSIX; the database is created with mode `0600`. Database symlinks and weak file permissions are rejected. Windows needs **independent NTFS ACL verification** from F2.7's existing Owner security layer, not provided by this feature.
2. `register_visual_memory_capabilities(store, services, capabilities)` registers one existing Core `ServiceRegistry` service plus **three distinct** Core `CapabilityRegistry` entries: `memory.visual.write` (high), `memory.visual.read` (medium), `memory.visual.delete` (high). No implicit `PermissionEngine` grant is installed. The SQLite store is a Core internal service, not an external MCP tool.
3. `GovernedVisualMemory` requires the same bound authenticated principal and the **exact same PermissionEngine** used by the existing `GovernedImageUnderstanding` / MCP Gateway model reader. Principal is never provided by public read/write/delete operations. Resource scope is an escaped per-principal `memory/visual/<principal>`.
4. `remember_image(image, capture_confirmed=True)` checks its explicit scoped **write policy before** local model inference, calls the existing `MCPGateway` Ollama tool with separate consent and `vision.image.describe` policy, and **rechecks write authorization after the await** to reduce revocation races. It stores only validated bounded, untrusted model text plus content hash, model provider name, scoped principal, UTC timestamp and opaque UUID. Never raw image pixels.
5. `recall(query, limit)` requires a distinct exact-scoped read policy, runs actual parameterized SQLite searches limited to 20 results, and returns immutable `UNTRUSTED_VISUAL_MEMORY` evidence. `forget(memory_id)` independently requires delete authorization, performs a scoped SQL DELETE and never deletes another principal's records. No permission means no database mutation; REQUIRE_APPROVAL without a consumed approval is DENY.
6. The store has a 500-record cap per principal, duplicate-image hash deduplication, bounded queries/text, SQLite busy timeout and `PRAGMA secure_delete=ON`. EventBus receives **metadata-only** store/delete events. The same raw description is never converted into policy, executable instructions, memories of identity or automated actions.

## Unit and integration tests

`cd core && uv run pytest -q tests/test_visual_sqlite_gateway.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests instantiate the **real** Core `ServiceRegistry`, `CapabilityRegistry`, `ProviderRegistry`, `PermissionEngine`, `MCPGateway`, local Ollama HTTP/JSON code with `httpx.MockTransport` and **actual on-disk SQLite**. Cases cover allowed image->Gateway->SQLite write, read and delete, write/read/delete policy independence, default-deny, absent image consent, model policy denial, cross-principal isolation, idempotent duplicate digest, literal SQL search, malicious IDs, untrusted prompt injection content, unconsumed approval denial, mismatched identities/policy engines, symlink and weak file ACL denial, metadata-only EventBus and per-owner storage quota.

## Missing full production acceptance

- SQLite metadata is **plaintext on the trusted owner's local disk**, **NOT encrypted**; disk encryption/key management, Windows NTFS ACL checks, backups, WAL retention and true secure erasure on SSDs need deployment validation. `secure_delete=ON` is not a reliable cryptographic deletion guarantee.
- Actual Ollama/Qwen-VL model installed, real camera/screen authorization, image parser sandbox and Windows storage path have not been exercised in CI. Test HTTP transport uses the actual production code but a deterministic local endpoint replacement for CI.
- This creates explicit opt-in **Core composition interfaces**. There is no user-facing memory dashboard, cloud sync, autonomous retrieval injection, cross-PR production wiring or long-term retention/consent UX yet.
- #82 remains **TESTING / PARTIAL_VERIFIED** only after exact-head Core Assurance/Persistence/Final Release Lock CI and cannot be marked COMPLETED without real Owner/device/backup/privacy acceptance. PR #137 is a mandatory prerequisite; no branch is merged automatically.

The deterministic Kernel/Gateway remains authoritative for all inference/provider tool execution, and the existing Core PermissionEngine remains authoritative for local persistent state.
