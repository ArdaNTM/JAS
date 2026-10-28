# Remote persistence adapter status

The `PostgreSQLRepository` in `aura_core.persistence.repository` is a generic
JSONB record adapter with atomic revision increments. It is intentionally not
yet wired into the existing workflow, approval, memory, or artifact stores.
That integration is required before remote mode can be enabled.

- Call `initialize()` explicitly as part of controlled schema provisioning.
- Configure a PostgreSQL DSN through `AURA_DATABASE_URL`; SQLite URLs are
  rejected by this adapter.
- Use TLS and scoped credentials in deployed environments; never commit DSNs.
- Call `close()` for an adapter-created engine during application shutdown.
- Do not use this generic adapter to bypass domain-specific validation,
  principal isolation, approval state transitions, or MCP Gateway authorization.

The `AURA_STORAGE_MODE=remote` startup gate remains in place until specialized
stores and durable artifact writes use verified remote adapters. A successful
generic repository test does not prove that the whole application is disk-free.
