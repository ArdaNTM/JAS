# F2.6 — Ubuntu Docker audit transport (INACTIVE / review candidate)

This proposal is **not** a live AURA capability. The deployed SCM service
continues to parse **deny_only**, returns **ISOLATION_BLOCKED**, and does not
instantiate the Ubuntu adapter. No receipt signer, approval path or Owner
capability is changed. Offline unit tests cannot demonstrate physical host
isolation or authorize ISOLATION_SIGNED.

## Boundaries

1. **Windows trusted broker** (audit_broker_ubuntu_transport.py):
   verifies its real SCM SID and private D: runtime, Ed25519 SSH host-key pin
   and broker-only client key, then invokes the fixed Windows OpenSSH executable
   with a fixed address **192.168.247.2**, fixed user **aura-transport**,
   no password, agent forwarding, proxying, local forwarding or client config.
   Only one exact bounded JSON request is written on stdin. No caller-selected
   remote command, hostname, mount, Docker context, Docker arguments or image.
2. **Linux forced-command worker** (core/scripts/aura_ubuntu_broker_forced_command.py):
   Python 3.12 stdlib-only, no shell interpolation; exact schema, nonce and
   freshness checks, reject duplicate/extra JSON keys. Docker CLI operations
   are generated only from the allowed inspect and pinned negative-probe
   templates. The Docker endpoint is **unix:///var/run/docker.sock**, never a
   published TCP listener. The pinned digest probe runs without privileges,
   writable root filesystem, host bind mounts or arbitrary network targets.
3. **Existing topology auditor**: the opt-in backend subclasses the existing
   DockerAuditBackend contract, so the full topology checks continue to apply.
   Neither the existing Docker Desktop boundary checker nor the legacy
   Docker Desktop backend is repointed. No new SCM route exposes the adapter.

## Explicit operation allowlist

- Inspect full 64-hex container ID, but only a *running*, labeled AURA-owned VM.
- Inspect exact AURA gateway name, internal/ingress networks and run-scoped
  storage volume names.
- Probe only fixed IPv4, IPv6, metadata, DNS and validated private
  host-gateway destinations on the already inspected container namespace.
- No Docker create/exec/build/pull/stop, host mounts, shell, forwarding,
  image selection, service installation, arbitrary environment or mutation.
- Connection refused, timeout, DNS failure, SSH unavailability or malformed
  response never counts as verified isolation.

## Blocked until separate operator security review (Phase 2)

- Current guest **auraops** is a privileged sudo/lxd operator. Never reuse it
  as the transport principal.
- Review and provision a distinct Linux **aura-transport** principal with no
  login shell, Docker group, lxd, sudo-all, or ordinary interactive access.
  Restrict one approved Ed25519 public key at sshd to one **root-owned**
  forced-command entrypoint; disable SSH port/X11/agent forwarding, PTY and
  password login. SSH forced-command behavior and privilege transition must
  be independently audited so SSH_ORIGINAL_COMMAND is preserved and validated
  before Docker socket access. **Do not copy any sudoers example from an
  untrusted agent or grant generic Docker CLI access.**
- Install reviewed, SHA-256-pinned, root-owned guest worker outside any
  AURA-agent-writable tree. Design a narrowly constrained privileged service
  helper; Docker group membership is root-equivalent. Its execution and
  credentials are **not provisioned by this PR**.
- Provision broker-only Windows Ed25519 identity and exact known_hosts
  host-key pin under protected D: ACLs, verify both Windows SCM and Linux
  principal identity from the actual OS and reject forged identity reports.
- Offline preload the exact existing Python probe OCI digest. The
  **aura-offline-test:local** diagnostic image is *not* an acceptable substitute.
- Validate real Windows/OpenSSH command-line compatibility, denial for Agent
  and AuraAuditor, replay behavior, fail-closed conditions, route/metadata/DNS/
  IPv6/host gateway probes, QEMU/UEFI/TUN boot and full topology after
  container creation. Physical SSH boundary, proxy/NAT and device proofs
  remain pending.
- Governed Owner/MCP lifecycle IPC, independent broker measurement signature,
  independently signed AuraAuditor receipt and an operator-approved policy
  migration are separate future changes. This branch MUST remain draft.

## Local verification (no live Docker required)

From the AURA Core Python 3.13 environment:

    python -m pytest -q tests/test_audit_broker_ubuntu_transport.py
    python -m pytest -q tests/test_audit_broker_f23.py tests/test_audit_broker_readiness.py
    python scripts/verify_final_lock.py

The guest worker itself targets Ubuntu's Python 3.12 and uses stdlib only.

## F2.6 P0/P1 hardening (review candidate, not deployed)

- The OpenSSH forced-command front end is **not root** and contains no Docker
  CLI calls. Only a pinned local Unix socket can reach the privileged helper.
- The separate root-owned, systemd socket-activated helper requires an exact
  Unix socket path and kernel `SO_PEERCRED` UID matching the dedicated
  `aura-transport` user. It rejects this principal when in privileged
  `docker`, `sudo`, `lxd`, `root` or `wheel` groups. The helper's
  Python script and enclosing installation directory must be root-owned and
  non-writable by less privileged accounts.
- The helper uses an operator-provisioned root-owned 0700 state directory and
  0600 SQLite database. `BEGIN IMMEDIATE` plus a UNIQUE nonce key atomically
  consumes each request nonce across processes/restarts; cleanup retains
  entries for 24 hours. Replays and storage errors fail closed before Docker.
- The wire protocol v2 binds **both** `run_id` and full `vm_id` on
  every request. Linux independently inspects the expected immutable OSWorld
  VM image, live Docker labels and single internal network; gateway, ingress
  network, and per-run volume inspect requests must match their exact labels,
  attachments and measured VM. Gateway container network probes accept only
  its exact independently inspected 64-hex ID. Host-gateway negative probes
  reject private IPs not matching the verified bridge gateway fields.
- The Windows transport's production preflight **rejects** current
  `deny_only`; it is not callable by the shipped SCM service.
  Hosted regressions mock this preflight solely to verify protocol behavior.

### Deployment remains blocked

Do not install accounts or services merely because CI passes. The required
separately reviewed operator deployment must include: a locked-down
`aura-transport` authorized key and SSH forced command; root-owned
immutable worker files; a root-owned systemd **Accept=no** Unix socket with
`SocketGroup=aura-transport` and `SocketMode=0660` at the exact pinned
path; a root helper launched only via that systemd socket with fd 3,
`LISTEN_FDS=1`, matching `LISTEN_PID`; a root-private SQLite directory;
real SCM/SSH identity/ACL negative checks; and measured OSWorld resource
ownership. Avoid generic sudo grants, Docker group membership, TCP daemon,
credential forwarding and any live `audit_only`/signed activation.
