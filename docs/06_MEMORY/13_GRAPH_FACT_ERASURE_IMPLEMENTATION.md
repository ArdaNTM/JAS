# Graph Fact Erasure — partial features #2 and #9

Both existing GraphRAG stores (SQLite and PostgreSQL) now expose `delete_fact(principal_id, fact_id, confirmed=True)`, a parameterized, scoped, idempotent storage operation. The SQLite implementation uses the existing transaction and lock; no MCP tool, route, policy, or automatic model permission is introduced.

`confirmed=True` is a defensive requirement, **not authentication or an Owner receipt**. The trusted application layer must obtain explicit user authorization before calling it. No sensitive deletion payload is logged.

This is **not complete right-to-be-forgotten support**. WAL, snapshots, backups, other memory stores, Qdrant indexes, graph-version history, and linked facts are not covered. CI tests exercise SQLite directly; real PostgreSQL acceptance requires a separate test server. Multi-store coordination and independent security reviews remain future work. Do not mark either feature COMPLETED.

Test: `cd core && uv run pytest -q tests/test_graph_fact_erasure.py` and full Core Assurance/Release Lock.
