# Portable installation and remote persistence rollout

## Target

AURA may be installed or run from a portable application directory, while
durable user/task/workflow/memory/artifact state is stored in explicitly
configured remote services. Local application binaries and bounded temporary
runtime files are not the same as local persistent state.

The kernel and authorization path is invariant:

`Kernel → Service/Capability/Provider registries → Permission Engine → MCP Gateway → Provider`

No storage adapter or provider may execute a real tool directly. Tool execution
must continue through the MCP Gateway authorization boundary.

## Current inventory (main branch)

- `SQLiteWorkflowStore` in `core/src/aura_core/enterprise/workflow_store.py`.
- `SQLiteApprovalStore` is composed by `core/src/aura_core/main.py` and defaults
  to a per-user local application-data path when approval fingerprinting is enabled.
- `EpisodicMemoryStore` in `core/src/aura_core/application/episodic_memory.py`
  defaults to `~/.aura/episodic-memory.sqlite3`.
- Background reflection and other memory/application services have their own
  persistence/configuration paths and need a full call-site inventory before
  the remote mode can be enabled.
- Speech transcription uses bounded temporary files; these should remain
  ephemeral and be removed after use, with no durable audio retention by default.
- The filesystem MCP provider is an explicitly local capability and must remain
  separately authorized; it is not a substitute for remote object storage.
- Ollama/Qwen inference may remain a separately configured inference provider;
  it is not AURA Core and does not imply that durable AURA state is local.

## Fail-closed rollout

`AURA_STORAGE_MODE` accepts `local` or `remote`. The default remains `local`
for existing development/test installations during migration. When set to
`remote`, startup currently fails deliberately. This is a safety gate, not a
claim that remote persistence is already implemented: accepting remote endpoint
variables before every durable store is migrated would still leave hidden local
SQLite writes.

Do not set `AURA_STORAGE_MODE=remote` in production until the migration steps
below are complete and the gate is replaced with verified adapter composition.

## Migration steps

1. Inventory all durable writes and filesystem/temp-file call sites, including
   less frequently used background, learning, approval, task, workflow and
   memory services.
2. Define repository and object-storage contracts. Preserve transaction,
   idempotency, optimistic concurrency, tenant/principal isolation and deletion
   semantics.
3. Implement and test remote PostgreSQL-compatible adapters and S3-compatible
   object storage, with TLS, scoped credentials, timeouts and explicit health
   checks. No silent SQLite/in-memory fallback in remote mode.
4. Route every durable store through the composition root and fail startup if
   any required adapter is missing or not remote-backed.
5. Add a one-time, audited migration utility with dry-run, counts/checksums,
   backup, idempotent retry and rollback instructions. Never delete source data
   automatically.
6. Add integration tests against disposable remote services and a portable
   package smoke test. Verify local data directories are not created in remote
   mode.
7. Only after all tests pass, change the rollout gate to allow remote mode.

## Configuration contract (reserved until adapters are integrated)

- `AURA_STORAGE_MODE=remote`
- `AURA_DATABASE_URL` — remote PostgreSQL-compatible DSN; credentials from
  environment/secret manager, never source control.
- `AURA_OBJECT_STORAGE_ENDPOINT` — HTTPS endpoint for S3-compatible storage.
- `AURA_OBJECT_STORAGE_BUCKET` — bucket/container name.
- `AURA_OBJECT_STORAGE_ACCESS_KEY_ID` and
  `AURA_OBJECT_STORAGE_SECRET_ACCESS_KEY` — scoped credentials from a secret
  manager or runtime environment.

These variables are documented as the target contract; they do not currently
activate remote adapters. Startup is intentionally blocked in remote mode until
adapter integration is complete.
