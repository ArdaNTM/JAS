# Feature #27 — approved offline isolated terminal (Docker)

Implementation: core/src/aura_core/providers/docker_terminal_mcp.py.
Stacked Draft on canonical feature #26 PR #150, never PR #149.

This is a real Docker CLI execution adapter, NOT an arbitrary local
terminal. Trusted Owner-only JSON config (schema aura.terminal.docker.v1),
private 0600 on Unix, pins the executable to SHA256 and each container
image to a digest. Each command profile has fixed ID, immutable image,
fixed argv and 1–20 second execution timeout. The external request can
supply only a command ID and an existing approval receipt.

## Concrete isolation

The command runs with preloaded image only (--pull=never), no network,
no host bind mounts or Docker socket inside the container, read-only
container filesystem, zero capabilities, no-new-privileges, UID/GID 65534,
32 PIDs, 256 MiB memory, 0.5 CPU, and a fresh 16 MiB in-container
tmpfs /workspace. Docker stdout is capped at 8 KiB in memory, and no
AURA environment variables are inherited. Container name is generated
and cleanup issues docker rm -f after errors/timeouts.

The host AURA service STILL needs an independently governed Docker
daemon access boundary. Merely adding these CLI flags does not prove
the daemon's privileged socket or host is contained. Do not install
AURA into the docker group as an implicit capability; prefer the
existing reviewed root-owned narrow broker architecture, with real
permission and socket attestation. Windows terminal config fails closed
until an approved Windows/Ubuntu broker path exists.

## Core authorization

The capability terminal.sandbox.execute is HIGH, and scope is
terminal/sandbox/{command_id}. Only a consumed one-shot human approval
via existing PermissionEngine/MCP Gateway/ApprovalStore is accepted
by LocalDockerTerminalMCP. The facade and authenticated HTTP endpoint
never infer policy from bearer authentication. No model-proposed shell,
image, Docker flags, arguments, paths or host PID are accepted.
EventBus records bounded metadata, no raw output; returned output
is explicitly UNTRUSTED_CONTAINER_OUTPUT.

## Tests and exact-head review

- cd core && uv run pytest -q tests/test_docker_terminal_mcp.py
- cd core && uv run pytest -q
- cd core && uv run python scripts/verify_final_lock.py

Tests cover real OS subprocess CLI execution, pending/consumed/replayed
human approvals, direct MCP provider bypass, default deny, invalid
unpinned images/command IDs, private manifest and HTTP 401/403/422/503.
Live Docker isolation smoke is optional and requires an **already
preloaded** digest-pinned Alpine image configured by
AURA_TEST_TERMINAL_PINNED_IMAGE. It is explicitly SKIPPED without that
runtime; do not count mere CI unit PASS as physical Docker isolation
proof. Image supply-chain signatures, actual Docker daemon isolation,
unprivileged user namespaces, Windows broker/device/Owner tests and
cross-PR #64–#150 lock remain outstanding. No COMPLETED claim.
