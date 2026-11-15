# Features #34/#52 — bounded reversible text-change preview (partial)

This PR introduces a working in-memory text transaction planner:
`preview_text_transaction(files, changes, principal_id, task_id)` verifies
the *complete* batch of source buffers and exact expected SHA-256
preimages, then computes proposed changed text and a deterministic inverse
record. `preview_text_rollback` checks current proposed hashes and
exact principal/task fingerprints before reconstructing the original text
in memory. Both are **pure data operations** with no filesystem, Git,
shell, network, agent, provider or tool side effects.

Safety boundaries:
- Exact relative POSIX-style file paths, no traversal, absolute paths,
  duplicate paths, symlinks or filesystem IO. (No actual filesystem path
  can be symlink-resolved because no path is opened.)
- Max 32 input buffers, 16 patch requests, 64KiB text per file and a
  256KiB input snapshot, 4KiB per fragment, exactly one old occurrence.
- Stale version preconditions, contradictory edits, type-confused scope,
  invalid Unicode, no-op changes and changed rollback preimages fail
  closed before any output. No automatic merging of conflicts.
- The fingerprints and reversible splice offsets are local *integrity
  hints*, not independently signed authority or proof of a real rollback.
  Result flags explicitly `authorization_checked=False`,
  `filesystem_changed=False`, `rollback_executed=False`.
- Source files must already have been read via an authenticated
  PermissionEngine/MCP Gateway capability. No write or undo authority is
  granted by this API.

Features #34 (undo/history) and #52 (versioning/rollback) remain
TESTING/PARTIAL; production requires authenticated file access, atomic
rollback on disk, backup/restore, concurrency control, an audit chain,
Owner approval and end-to-end recovery evidence.

Tests: `cd core && uv run pytest -q tests/test_text_change_preview.py`,
full Core Assurance, Remote Persistence and Final Release Lock.
