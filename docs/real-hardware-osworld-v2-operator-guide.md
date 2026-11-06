# AURA — Real Hardware / OSWorld-V2.1 operator runbook

## Guardrails

This is an **operator-initiated** bridge, not an unattended AGI deployment.
All model-generated guest clicks/typing go through MCPGateway's stored
per-action fingerprint. The *separately privileged* Owner Control Plane
must verify a native user-presence WebAuthn assertion before any approval.
The default Owner activation receipts are distinct from OSWorld guest-input
approvals; the latter use capability \`OSWorldVM\` and operation
\`GuestAction\`, restricted to \`osworld:v2.1:disposable_vm\`.
No Host desktop, production personal files or native Windows input are used
by the OSWorld Docker provider. There is no direct model-to-VM Python execution.

## Real Windows Hello (no mock)

Run **interactively and unprivileged** on the actual Windows machine:

\`\`\`powershell
cd D:\AURA\JAS-real-world-test\core
uv sync --frozen --group dev
uv run --frozen python scripts/physical_webauthn_probe.py
\`\`\`

The WindowsClient calls the native Windows WebAuthn API, requests a temporary
**platform** credential and mandatory UV, verifies registration/assertion
through Fido2Server with an exact https://localhost origin, and tests a
fresh challenge against the old assertion. The actual Windows Hello prompt
must be manually accepted. UV can mean Windows Hello PIN, not biometrics.

The diagnostic does **not** produce an Owner activation receipt and does
not mark \`hardware_verified=true\`. To authorize AURA actions you must use
the separate \`http://localhost:8766\` Owner Control Plane, not this probe.

## Real microphone (no mock)

\`\`\`powershell
uv run --frozen python scripts/physical_microphone_probe.py --list-devices
uv run --frozen python scripts/physical_microphone_probe.py --samples 40
# If Windows default capture fails, choose a physical input ID from the list:
uv run --frozen python scripts/physical_microphone_probe.py --device 0 --samples 40
\`\`\`

This script directly uses WinMM \`waveIn*\` API to capture real PCM and
timestamps, checks non-silent audible buffers and reports buffer-arrival
p50/p95. It keeps no PCM recording. This is **not** Nirvana TTS first-audio
or in-application interruption end-to-end latency; those require additional
physical instrumentation. A broken/no microphone returns nonzero exit.

## Complete signed acceptance (no automatic private-key minting)

\`\`\`powershell
uv run --frozen python scripts/verify_physical_hardware.py \
  --evidence D:\AURA-Evidence\physical-evidence.json \
  --trusted-public-keys D:\AURA-Evidence\trusted-physical-signers.json
\`\`\`

The independent trusted lab signer, hosted under a different OS identity,
collects all six checks: Windows Hello UV, Nirvana Voice p50/p95 first-audio,
real barge-in, dual monitor/hotplug, negative coordinates and kill-switch
persistence. Every envelope must use
\`SignedHardwareEvidence\` JSON fields including strict timestamp, run ID,
nonce, metric keys, signer and Ed25519 signature. The JSON report returns
\`hardware_verified=true\` **only if** all six valid, nonexpired,
independently signed records and physical thresholds pass. The AURA process
has **no signer private key**. Never fabricate these metrics or extract
the trusted Owner keys. An operator must audit the signer/measurement device;
a signature alone does not attest physical collection.

## Official OSWorld-V2.1 Docker VM live evaluation

On a dedicated disposable Linux or WSL2 Docker+KVM host with Docker Engine,
provision the official version-matched components:

- \`xlang-ai/OSWorld-V2@osworld-v2.1\` at its *verified, pinned Git commit SHA*.
- \`xlangai/osworld_v2_tasks@osworld-v2.1\` inside the trusted checkout.
- \`xlangai/osworld_v2_assets_gated@osworld-v2.1\` into a nonempty asset dir.
- Matching \`Task-Web/OSWorld-web@osworld-v2.1\` self-hosted website and
  \`WEBSITE_HOST_SUFFIX\`; pinned official Docker Ubuntu VM provider image.
- Disposable Docker privileges, KVM support and independently checked
  network firewall so the guest cannot reach personal/private networks,
  cloud metadata or arbitrary outbound destinations.

The command runs **one** official task and requires one new Owner approval
for every action. Configure a protected persistent \`SQLiteApprovalStore\`
which is also used by the separate Owner Control Plane configured with the
exact \`owner_challenge_policy_digest\` emitted at startup.
Provide the fingerprint key as a protected environment variable, not CLI
arguments or GitHub CI secrets. In the separate Owner Control Plane
review \`/api/owner/pending\`, issue a one-use challenge and verify the actual
Windows Hello assertion before deciding the action. The agent cannot decide
its own approvals.

\`\`\`powershell
$env:AURA_OSWORLD_VM_FIREWALL_VERIFIED = "1" # ONLY after independent firewall verification
$env:AURA_APPROVAL_FINGERPRINT_KEY_HEX = "<at-least-32-byte-hex-secret>"
uv run --frozen python scripts/osworld_v2_lab.py --live \
  --upstream "D:\OSWorld-V2" \
  --upstream-commit "<40-digit-approved-osworld-v2.1-commit-sha>" \
  --assets "D:\OSWorld-V2\cache\osworld_v2_assets_v2.1" \
  --task-file "D:\OSWorld-V2\evaluation_examples\task_class\<official-task>.json" \
  --website-suffix "<operator-self-hosted-suffix>" \
  --owner-db "D:\AURA-Owner-Private\approvals.sqlite3" \
  --allow-real-vm
\`\`\`

The real OSWorld runner verifies the tag and commit SHA, source tree,
official task file, gated assets, Docker availability and separate
approval DB. It starts the official \`DesktopEnv(provider_name='docker')\`,
generates **bounded structured actions** from local Ollama/Qwen3,
requests a *new MCPGateway approval per step* and only then dispatches a
fixed guest command. A score is returned only from
\`DesktopEnv.evaluate()\` after an authorized DONE. Missing owner approval
blocks the run; exhausting the safety budget returns \`score:null\`.
It is not leaderboard verification and it doesn't run as a privileged
unattended local-owner agent.

## Release acceptance

\`\`\`powershell
uv run --frozen python -m pytest -q tests/test_real_hardware_osworld.py
uv run --frozen python -m pytest -q
uv run --frozen python scripts/verify_final_lock.py
\`\`\`

CI tests are synthetic GUARDRAIL tests, not a claim of physical observation.
Real Windows Hello prompts, microphone, voice barge-in, OSWorld VM and
network enforcement require an operator-owned device and cannot run on
hosted GitHub Actions.

## Stage E native physical probe hotfix

- For `fido2==2.2.1`, the Windows client's `get_assertion()` returns an
  `AssertionSelection`; use `get_response(0)` to supply the
  `AuthenticationResponse` to `Fido2Server.authenticate_complete()`.
  Check the signed response's authenticator-data UV flag. On Windows Hello
  PIN entry, UV means *user verification*, not necessarily biometrics.
- WinMM now enumerates devices via `waveInGetNumDevs` and
  `waveInGetDevCapsW`, tries the default mapper then explicit endpoints,
  negotiates mono/stereo 16/44.1/48 kHz PCM, and queues a prepared buffer
  *before* starting `waveInStart`. Errors report the native WinMM
  `MMRESULT` and Windows error text, with no raw PCM.
- Diagnostic failures must **not** trigger new trusted Owner receipts,
  signed evidence issuance, or automatic release-lock rewriting.
- If WinMM reports no endpoints, check *Settings > Privacy & security >
  Microphone > Let desktop apps access your microphone* and recording device
  enablement. If `WAVERR_BADFORMAT` occurs, use `--list-devices` to try
  a different endpoint; for Bluetooth headsets, switch to a capture-capable
  headset profile.
- Successful probes still report `hardware_verified: false`. AURA's
  independent physical acceptance verifier requires **all six** signed
  on-device measurements, including real Nirvana Voice latency/barge-in,
  dual-monitor, negative-coordinate HUD and persistent Kill Switch.
