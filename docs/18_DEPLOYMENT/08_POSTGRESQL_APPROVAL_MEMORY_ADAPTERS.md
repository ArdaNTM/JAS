# Remote approval and memory adapters

This change adds PostgreSQL-backed async adapters for approval lifecycle and
episodic memory. SQLite implementations remain available for compatibility and
local development. The adapters are not automatically wired into production
composition by this change.

Before enabling `AURA_STORAGE_MODE=remote`, deployment work must:
- configure a PostgreSQL database and apply explicit schema initialization;
- configure S3-compatible object storage and a trusted pre-signed URL provider;
- route every approval, workflow, memory, task and artifact persistence call
  through remote implementations;
- test authorization, principal isolation, one-time approval consumption,
  expiration, concurrent transitions, restart durability and service outages
  against real PostgreSQL and an S3-compatible test service;
- verify fail-closed startup and prove no durable local files are created.
