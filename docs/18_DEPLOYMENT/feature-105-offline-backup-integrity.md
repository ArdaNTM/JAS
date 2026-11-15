# Feature #105 — offline content-addressed backup envelope (partial)

This PR supplies a real, deterministic, **in-memory** backup packer and
verification reader under `aura_core.persistence.offline_backup`. It packages
bytes already obtained through an authenticated, PermissionEngine/MCP
Gateway-authorized path. ZIP members have stable metadata and hashes, an
explicit principal-scope digest, an inventory and per-file SHA-256. Verification
checks size limits, member completeness and integrity without restoring data.

Security and trust:
- Backups are **not encrypted, signed or independently authenticated**.
  SHA-256 detects corruption but an attacker who can modify both manifest
  and payload can forge the checksums.
- Principal-scope hash is only a caller-supplied label check. The external
  caller must authenticate the principal and authorize both backup creation
  and access to the resulting bundle.
- This module does not read/write filesystem paths, send data to cloud,
  schedule backups, rotate keys, grant Owner rights or execute restores.
- Rejects ZIP traversal, path ambiguity, symlinks, encrypted/deflated items,
  unexpected/unrecorded members, malformed JSON or sizes and scope mismatch.
- Limits: ≤50 files, ≤2 MiB each, ≤8 MiB content, ≤9 MiB bundle.
  This is not suitable for sensitive production secrets until a separately
  authorized encryption/key-management/storage adapter is reviewed.

This addresses only the **integrity packaging/validation slice** of the
approved JAS backup architecture; full feature #105 still requires durable
isolated storage, encryption, retention, restore rehearsal, RPO/RTO evidence,
and independent Owner/security review.

Tests: `cd core && uv run pytest -q tests/test_offline_backup_integrity.py`
plus full Core Assurance and Final Release Lock.
