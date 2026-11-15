# Feature #115 — local vocabulary spaced repetition (partial)

This standalone internal service extends the existing AURA application layer,
using local SQLite to store per-principal vocabulary flashcards with due times,
an SM-2-inspired 0–5 review grade progression, revision-based optimistic
concurrency control and bounded due-card queries. It supports offline
language learning without depending on paid APIs, an LLM or internet.

The primitive does not translate text, detect language, schedule background
notifications or make MCP calls. It provides **no authentication by itself**:
a future API must verify the Owner/principal, call PermissionEngine and
enforce user consent before reading/writing/deleting records. The
`confirmed=True` deletion flag is defense in depth, not an identity proof.
Never expose this storage class directly as an unauthenticated network tool.

Cards and answers are untrusted user data and remain in plaintext SQLite;
encryption-at-rest and secure deletion of SQLite journals/backups are NOT
claimed. Card IDs are opaque UUIDs, all SQL is parameterized, revisions
reject stale concurrent updates, and a per-principal 10,000-card cap
limits unbounded growth. Due-card enumeration is limited to 50 results.

Verification: `cd core && uv run pytest -q tests/test_offline_language_learning.py`,
full AURA Core Assurance, Final Release Lock. Actual UI/voice integration,
language translation, secure key management and real user acceptance remain.
Do not mark the complete feature #115 as COMPLETED.
