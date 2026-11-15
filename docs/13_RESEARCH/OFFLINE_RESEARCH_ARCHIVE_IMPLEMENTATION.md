# Offline Research Snapshot Archive — partial features #42 and #44

`SQLiteResearchArchive` persists bounded text/html/plain/json content that an **existing authorized MCP Gateway fetch call** has already returned. Archival requires an explicit `consented=True` flag plus an `AuthorizationDecision.ALLOW` response. Neither the archive nor its tests perform network requests, browsing, credential resolution or tool execution.

Stored snapshots are scoped by the exact principal, content SHA-256 and a deterministic identity bound to principal, URL and content digest. Repeated inserts are idempotent. Retrieval remains principal-scoped and **untrusted**; no source verification, model instruction authority or reliable publisher identity is implied. Explicit `forget(..., confirmed=True)` removes one active SQLite row without granting any new Gateway permission.

**Security limits:** Boolean flags are defensive requirements, not proof of Owner approval or authentication. A trusted caller must verify the principal and consent before archiving/deleting. The SQLite file is not encrypted by this feature. Backups, WAL, external caches, Qdrant, PostgreSQL and physically secure deletion are out of scope. The URL is merely metadata from a previous provider response, not an SSRF-safe fetch target; never reuse it as authorization. Other file formats (PDF/DOCX) and a user-facing archive browser are not implemented.

Test: `cd core && uv run pytest -q tests/test_research_archive.py`; full Core CI and deterministic release-lock verifier. This is a working offline persistence primitive, not feature #42/#44 completion.
