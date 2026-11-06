# AURA Stage F — Secure OSWorld V2.1 live evaluation

Status: DRAFT; no physical Docker isolation certified by hosted CI.
The old AURA_OSWORLD_VM_FIREWALL_VERIFIED=1 flag is insufficient and not
used to approve the Stage F live runner. A signed fresh isolation receipt
is mandatory for all agent actions.

## Boundaries and prerequisites

AURA Core, Owner WebAuthn, MCP Gateway and trusted signer verification run
in Python 3.13. The pinned OSWorld version runs in a separate Python 3.12
virtual environment with bounded private JSONL subprocess transport.
No AURA Owner key, HF token or fingerprint secret enters the worker's env.
Every VM action requires independent MCP Gateway + human Owner WebAuthn.

The OSWorld worker patches the DockerProvider only in that isolated Python
3.12 interpreter, not in the upstream checkout. The container MUST use the
existing aura-osworld-v21-lab internal IPv4-only bridge with no external
network attachment and only four localhost control ports. To avoid granting DAC_OVERRIDE for
the pinned Nginx error.log, the worker overlays ONLY /var/log/nginx with a
root-owned 16 MiB tmpfs (rw,nosuid,nodev,noexec,mode=0755). No host log bind,
privileged main container, custom VM entrypoint or additional Linux capability.
The host attestor requires this exact tmpfs and rejects extra mounts.
Nginx files written to tmpfs are intentionally ephemeral and may disappear
at container exit. Collect startup stderr with the Docker monitor, and
inspect in-container logs before VM teardown if needed.

The pinned image also declares /storage as a Docker volume. To fix
QEMU's EACCES reading /storage/uefi.rom without DAC_OVERRIDE, the host
worker provisions a randomly named, local-only, per-run Docker volume.
An isolated, one-shot *preparation* container using the SAME digest-pinned
image and network_mode=none, cap_drop=ALL and no-new-privileges copies
/usr/share/OVMF/edk2-x86_64-code.fd into that empty volume as
/storage/uefi.rom, with owner-accessible mode 0644 and directory mode 0755.
The main VM uses this named volume at /storage (no writable host bind).
A stopped/failed VM removes its own ephemeral volume; a killed worker's
parent bridge independently performs run-ID-scoped cleanup. The host
attestor checks the named volume's exact local driver, run-specific labels,
mount identity and denies remote drivers or extra mounts. The /storage
volume is intentionally NOT a tmpfs: it must accommodate 32 GB sparse disks.

Docker Desktop's WSL2 Linux kernel can reject the pinned image's
iptables NAT initialization even with NET_ADMIN and an explicitly mapped
/dev/net/tun device. The worker now requests QEMU's supported user-mode
SLIRP **explicitly** using NETWORK=user, USER_PORTS=5000,8080,9222 and
HOST_PORTS=8006. Those are fixed literal environment values, overriding
untrusted provider environment settings. The guest's screenshot API (5000),
VLC (8080) and Chrome debugging endpoint (9222) are forwarded inside the
container; 8006 remains the container's own web UI and is never a guest
forwarding target. Docker publishes these four endpoints to 127.0.0.1
only. Both the worker's pre-action inspection and the independent host
attestor reject missing, duplicate or mutated QEMU network environment
values; a permissive, automatic fallback is not an attested configuration.

This targeted compatibility hotfix intentionally makes no change to the
existing Docker capability/device inventory: cap_drop=ALL,
cap_add=CHOWN,NET_ADMIN, and exactly /dev/net/tun (plus optional pinned
/dev/kvm) remain enforced, with no privileged, MKNOD, SYS_ADMIN or kernel
module loading. They are *not required by SLIRP itself* and should be
removed in a separate, tested tightening change after real Windows VM
readiness is confirmed. This is not a claim that host or guest isolation
has been physically certified: the signed host negative probes and
Owner/MCP authorization gates remain mandatory.

With those constraints, it runs QEMU
with KVM=N when hardware KVM is unavailable. The official Ubuntu disk image
mount is read-only and the worker has a random per-run cleanup label.

The auditor must run under a separately protected host identity with a
pre-existing Ed25519 PEM private key outside the AURA checkout. A pinned
public signer JSON maps independent_host_auditor to the raw 32-byte
Ed25519 public key encoded as 64 hex chars. Never commit private keys.

Docker internal networking cannot guarantee host-gateway isolation alone.
The independent auditor checks exact container identity, pinned runtime
image, live port bindings, mount flags, and performs IPv4, DNS, metadata,
IPv6 and host-gateway negative probes in the same container network namespace.
A failing check blocks signing. Receipt verifies concrete tests only; no
receipt can certify arbitrary untested paths or a compromised Docker host.

Upstream source Git revision must exactly equal
3d778a3c9a34a079316f70df023b166700445792, tag osworld-v2.1.
The Ubuntu disk must exist at:
D:\AURA\OSWorld-V2\docker_vm_data\osworld-v2-ubuntu-x86.qcow2

The matching archive osworld-v2-ubuntu-x86.qcow2.zip is pinned to
dataset revision 6e16459a2feb5a8f1ed65babcfe7a2a6205d049d.
Verify ZIP SHA256 14b08aa7ba6c023ecb91d46de8df5de32af4d1d6bd75ea925519caf9677fc8b3
before safely extracting it. The worker does not auto-download the image.

## Smoke profile without KVM or agent actions

Run from D:\AURA\JAS-real-world-test\core after the QCOW2 exists:

    uv sync --frozen --group dev
    uv run --frozen python -m pytest -q tests/test_osworld_secure_live.py
    uv run --frozen python scripts/verify_final_lock.py
    uv run --frozen python scripts/osworld_v2_lab.py --live --smoke --upstream D:\AURA\OSWorld-V2 --upstream-commit 3d778a3c9a34a079316f70df023b166700445792 --boot-timeout 900 --allow-real-vm

Expected if successful: VM_BOOT_ONLY, kvm_mode=N,
network_isolation_verified=false and benchmark_score=null. The smoke never
calls the model, loads a task, signs a receipt or grants an Owner approval.
Boot timeout bounds are 300 to 1200 seconds.

## Live profile after gated data approval and enrolled Owner credentials

A separate Owner Control Plane must share the protected ApprovalStore and
its exact policy_digest, with a pre-enrolled Windows Hello credential.
The task_###.py must be independently reviewed and its SHA256 pinned to an
operator-approved exact hash. The gated OSWorld V2.1 assets must be local.

Terminal A: Start the AURA live runner with approved task ID and hash,
gated assets, trusted signer public-key JSON, protected Owner approval
database, a fresh receipt path and approved mock-site suffix. The command
prints the FULL container ID and waits for an independent host auditor
without issuing any guest actions:

    uv run --frozen python scripts/osworld_v2_lab.py --live --upstream D:\AURA\OSWorld-V2 --upstream-commit 3d778a3c9a34a079316f70df023b166700445792 --assets D:\AURA\OSWorld-V2\cache\osworld_v2_assets_v2.1 --task-id 001 --approved-task-sha256 HASH64 --website-suffix INTERNAL_MOCK_SUFFIX --owner-db APPROVAL_DB --trusted-public-keys PUBLIC_SIGNERS_JSON --receipt FRESH_RECEIPT_PATH --attestation-wait 240 --boot-timeout 900 --allow-real-vm

Terminal B: As an independently protected OS identity with access to the
private external Ed25519 key, use the full container ID printed by Terminal
A and the same fresh receipt path:

    uv run --frozen python scripts/attest_osworld_network.py --container FULL_CONTAINER_ID --vm-image D:\AURA\OSWorld-V2\docker_vm_data\osworld-v2-ubuntu-x86.qcow2 --signer-id independent_host_auditor --private-key EXTERNAL_ED25519_PEM --trusted-public-keys PUBLIC_SIGNERS_JSON --out FRESH_RECEIPT_PATH

The host auditor can sign only if all network tests pass. Terminal A verifies
signature, freshness, Docker network, image identity and loopback bindings,
then loads the approved official task class in the Python 3.12 worker.
Every proposed typed action continues through MCP Gateway and Owner WebAuthn.
Official OSWorld V2.1 evaluation is DesktopEnv.evaluate() without parameters.

Only a finite set of mock websites and internal services can be made
reachable by an explicitly reviewed in-network policy. Do not relax the
existing pinned public HTTPS proxy by allowing blanket private CIDRs.
A signed isolation receipt never marks physical_hardware_verified=true;
Nirvana Voice, HUD and emergency-stop physical evidence remains separate.
