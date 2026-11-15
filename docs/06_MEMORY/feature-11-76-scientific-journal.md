# Features #11 / #76 — scoped offline scientific observation journal

The existing `SQLiteEpisodicMemory` under JAS Core is reused as a
real local persistence engine. New
`aura_core.research.scientific_journal.ScientificJournal` stores limited
human-reviewed (but still **untrusted**) hypotheses, observations,
negative results and literature notes with a DOI-shaped source label and
per-entry SHA-256 content fingerprint. It **does not** create a new data
directory/path or expose an MCP tool. The caller supplies an already
configured/authorized memory store.

Key limitations:
- `confirm_local_persist=True` is merely local explicit confirmation;
  it is NOT an authenticated Owner/signed approval receipt.
- SQLite data are **plaintext**; SHA-256 detects corruption only, not
  authenticity against an attacker changing both content and digest.
- A DOI-shaped string is NOT verified publisher provenance.
- There is no new core privilege, network research, scheduled experiment,
  laboratory actuation, scientific discovery claim or data promotion
  into system instructions.
- Underlying episodic memory remains append-only and multi-purpose.
  This component does not provide erasure from SQLite, backups or WAL.
- Caller must authenticate exact principal/task and authorize creation
  of the store, reading and writing through PermissionEngine/MCP Gateway
  before exposing the methods.

Feature #11 (offline memory/core) and #76 (scientific discovery memory)
remain TESTING/PARTIAL. Only a scoped durable research-note slice was
implemented; complete offline AI operation, secure encryption/erasure,
reliable provenance, independent scientific validation and Owner UI are
not achieved.

Tests use real file-backed SQLite persistence, new instance reload,
cross-principal/task isolation, consent flag refusal, malformed source
data and direct database tampering rejection.

`cd core && uv run pytest -q tests/test_scientific_journal.py`,
full Core Assurance, Remote Persistence and Final Release Lock.
