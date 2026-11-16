# Docker sandbox output and image argument hardening — feature #101 (partial)

The existing `DockerPythonRunner` already runs authorized untrusted drafts with `--network none`, read-only root, non-root UID, dropped capabilities, no-new-privileges and bounded CPU/memory. This PR fixes two concrete fail-open/cap violations **inside that existing runner**.

## Changes
- stdout and stderr now share a *single* `SandboxPolicy.max_output_bytes` cap protected by one threading lock, rather than each receiving the full budget.
- Output-limit status is calculated only **after** reader threads finish (or fail to finish), preventing a quickly exiting container from reporting success while oversized output remains unread.
- Strict Docker image reference pattern rejects option-looking image values beginning with `-`, whitespace, command-like newlines, unpinned images, uppercase-invalid SHA-256 digests and very long references. The image must be digest-pinned; `--pull=never` is retained.
- Missing/denied authorization still fails before any subprocess. No host execution fallback, no new capability grant or change to PermissionEngine/Gateway policy.

## Tests
`cd core && uv run pytest -q tests/test_sandbox_output_guard.py tests/test_sandbox_contract.py`
`cd core && uv run python scripts/verify_final_lock.py`

Tests fake subprocess.Popen and never run untrusted Python or Docker; cover combined dual-stream overflow, a process that returns before streams finish, normal/failed exits, invalid image arguments and denied authorization, as well as asserted isolation flags.

## Known remaining production acceptance
- This is *not* an isolated kernel attestation, escape-proof container, live Docker verification, independent human approval or OSWorld hardware certification.
- A real Docker production run must still demonstrate network isolation, image supply-chain verification, resource caps and end-to-end PermissionEngine authorization. F2.7 PR #64 remains untouched.
- Regression tests provide deterministic simulated process behavior, not real Docker/QEMU evidence. Feature #101 remains TESTING/PARTIAL_VERIFIED, not COMPLETED.
- No external dependency or licensing change (Python stdlib).
