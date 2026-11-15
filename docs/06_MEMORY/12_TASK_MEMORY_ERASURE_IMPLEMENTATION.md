# Feature 009 — scoped task memory erasure (review candidate)

This implementation extends the **existing** `SQLiteEpisodicMemory` and `TaskMemoryCoordinator` with `forget_task(..., confirmed=True)`. It performs a **single SQLite transaction** deleting one exact principal/task pair from `episodic_records` and `task_checkpoints`, then evicts the corresponding in-process working context. Repeated calls return `(0, 0)`; unrelated principals and tasks are untouched.

**Security:** callers must authenticate the principal and obtain explicit human approval before passing `confirmed=True`. A boolean is a defensive precondition, **not** proof of Owner approval; no HTTP endpoint, implicit capability, MCP dispatch or security policy grant is introduced. Scope values pass the store's existing validation. No sensitive content is emitted to an audit log.

**Privacy limits:** SQL deletion is logical removal from this active SQLite database only. SQLite WAL pages, filesystem snapshots, backups, remote Qdrant/PostgreSQL replicas, external logs and cached copies are **not** securely erased by this method. Cross-store deletion, retention policies, auditable redacted receipts and authorized API integration remain necessary before feature #9 can be COMPLETED.

Test: `cd core && uv run pytest -q tests/test_scoped_task_memory_erasure.py`. Also require full Core CI and deterministic release-lock verification. This is not a full implementation of the JAS memory versioning/lifecycle contract.
