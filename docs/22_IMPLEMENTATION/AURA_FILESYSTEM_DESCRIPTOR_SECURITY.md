# Descriptor-bound local test-data reads — feature #25 (partial)

Existing `core/src/aura_core/filesystem/safe_reader.py` provides read-only UTF-8 access to explicitly allowed repository `test-data/` paths. The initial implementation checked `lstat()` and `resolve()`, then opened an absolute path. On POSIX systems an attacker might change an intermediate directory to a symlink **after validation but before open**, escaping the permitted root.

## Protection
- On POSIX systems supporting `O_NOFOLLOW` and `O_DIRECTORY`, preserve the preflight root inode, open that directory with no-follow, verify `(st_dev, st_ino)`, and open every child directory via `dir_fd` + `O_NOFOLLOW|O_DIRECTORY`. Open final file via the last pinned dirfd and `O_NOFOLLOW`.
- A concurrent rename/symlink swap of an intermediate/final component cannot redirect the descriptor walk to an arbitrary path outside the open parent descriptor.
- Root and all opened directories and final file handles close even on failure. Files remain read-only; only regular files <=1 MiB are read and UTF-8 is strictly decoded.
- Reject lexical `..`, `.`, duplicated separators and trailing slash before any IO. Existing static symlink/reparse checks and absolute-path denials remain.
- On **Windows**, Python's portable `os.open` does not provide the equivalent descriptor-relative no-follow guarantees. We keep existing reparse/lstat validation and explicitly require a trusted native Windows handle implementation plus actual NTFS reparse race tests for full cross-platform acceptance. Do NOT mistake POSIX hardening for Windows race-proofing.

## Tests
`cd core && uv run pytest -q tests/test_safe_filesystem_reader.py tests/test_filesystem_descriptor_walk.py`
`cd core && uv run python scripts/verify_final_lock.py`

On Linux, regression tests use real temp directories, real `os.open` and an adversarial monkeypatch that swaps an intermediate directory, final file or root to a symlink at the **exact open window**. Additional tests cover UTF-8, traversal, invalid bytes and bounds. No external files are read or sent, and the existing MCP Gateway/PermissionEngine contract is unchanged.

## Remaining acceptance for #25
- No filesystem write, move, delete, backup/restore, listing or user-controlled path grant. The existing filesystem MCP only supports constrained read-only test-data, and tool calls remain governed by MCP Gateway.
- Windows reparse TOCTOU, real system sandboxing, NTFS ACLs, real Owner approval, full file manager and production tests remain outstanding.
- This is PARTIAL implementation and security mitigation only. Keep feature #25 TESTING/PARTIAL_VERIFIED, not COMPLETED. No new libraries or licensing constraints.
